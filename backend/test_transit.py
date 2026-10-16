"""Offline GTFS-RT regressions: python -B -m unittest backend.test_transit."""

from pathlib import Path
import socket
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import zipfile

from backend.errors import ServiceError
from backend.providers.query import ProviderQuery
from backend.providers import transit
from backend.providers.transit import ScheduleLookup, TransitAdapter, load_schedule


NOW = 1700000100
PROVIDER = "entur.open_data"


class Message:
    """Presence-aware fixture: absent protobuf scalars must not become zero values."""

    def __init__(self, **fields):
        self.__dict__.update(fields)

    def HasField(self, name):
        return name in self.__dict__


def vehicle(entity="e1", vehicle_id="v1", timestamp=1700000000, **position):
    fields = {"trip": Message(route_id="r1", trip_id="t1"), "vehicle": Message(id=vehicle_id),
        "position": Message(latitude=-27.5, longitude=153.0, **position)}
    if timestamp is not None:
        fields["timestamp"] = timestamp
    return Message(id=entity, vehicle=Message(**fields))


def feed(*entities, timestamp=1700000000, incrementality=None):
    header = {"gtfs_realtime_version": "2.0"}
    if timestamp is not None:
        header["timestamp"] = timestamp
    if incrementality is not None:
        header["incrementality"] = incrementality
    return Message(header=Message(**header), entity=list(entities))


class TransitTests(unittest.TestCase):
    def setUp(self):
        for name in ("socket", "getaddrinfo"):
            patch = mock.patch.object(socket, name, side_effect=AssertionError("Network forbidden"))
            patch.start()
            self.addCleanup(patch.stop)
        self.schedule = ScheduleLookup(PROVIDER, {"r1": {"route_type": 3, "route_short_name": "100"}}, {"t1": "r1"})

    def adapter(self, value, **kwargs):
        kwargs.setdefault("schedule", self.schedule)
        kwargs.setdefault("clock", lambda: NOW)
        return TransitAdapter(PROVIDER, decoder=lambda raw: value, **kwargs)

    def parse(self, value, query=None, **kwargs):
        return self.adapter(value, **kwargs).parse(b"fixture", query or ProviderQuery())

    def error(self, status, callback, *args, **kwargs):
        with self.assertRaises(ServiceError) as caught:
            callback(*args, **kwargs)
        self.assertEqual(caught.exception.status, status)
        return caught.exception

    def test_real_point_route_join_units_and_age(self):
        result = self.parse(feed(vehicle(speed=0.0, bearing=90.0)))
        feature = result["features"][0]
        properties = feature["properties"]
        self.assertEqual(feature["geometry"], {"type": "Point", "coordinates": [153.0, -27.5]})
        self.assertEqual(properties["observed_at"], "2023-11-14T22:13:20Z")
        self.assertEqual(properties["age_seconds"], 100)
        self.assertEqual((properties["mode"], properties["route_type"], properties["speed_m_s"]), ("bus", 3, 0))
        self.assertEqual(result["state"], "fresh")
        self.assertFalse(result["partial"])

    def test_no_schedule_does_not_invent_mode_or_timestamp(self):
        result = self.parse(feed(vehicle(timestamp=None)), schedule=None)
        p = result["features"][0]["properties"]
        for key in ("mode", "route_type", "observed_at", "age_seconds", "speed_m_s"):
            self.assertIsNone(p[key])
        self.assertEqual(p["schedule_join"], "not_configured")
        self.assertEqual(result["state"], "partial")

    def test_coordinate_presence_zero_and_invalid(self):
        zero = vehicle()
        zero.vehicle.position = Message(latitude=0.0, longitude=0.0)
        self.assertEqual(self.parse(feed(zero))["features"][0]["geometry"]["coordinates"], [0, 0])
        for position in (Message(latitude=1), Message(longitude=1), Message(latitude=float("nan"), longitude=1),
                         Message(latitude=91, longitude=1), Message(latitude=1, longitude=181)):
            entity = vehicle()
            entity.vehicle.position = position
            result = self.parse(feed(entity))
            self.assertEqual(result["features"], [])
            self.assertEqual(result["rejected_records"], 1)
            self.assertTrue(result["partial"])

    def test_stale_header_and_observation_future_unknown(self):
        result = self.parse(feed(vehicle(timestamp=NOW - 121), timestamp=NOW))
        self.assertEqual(result["state"], "stale")
        self.assertTrue(result["features"][0]["properties"]["stale"])
        self.assertEqual(self.parse(feed(vehicle(timestamp=NOW), timestamp=NOW - 121))["state"], "stale")
        for timestamp in (None, 0, NOW + 10):
            result = self.parse(feed(vehicle(timestamp=timestamp), timestamp=NOW))
            self.assertEqual(result["state"], "partial")
        p = self.parse(feed(vehicle(timestamp=NOW + 10)))["features"][0]["properties"]
        self.assertEqual(p["timestamp_status"], "future")
        self.assertEqual(p["age_seconds"], -10)

    def test_dedup_newest_and_stable_vehicle_identity(self):
        older, newer = vehicle("old", timestamp=NOW - 50), vehicle("new", timestamp=NOW)
        newer.vehicle.trip = Message(route_id="r1", trip_id="other")
        a = self.parse(feed(older, newer))
        b = self.parse(feed(newer, older))
        self.assertEqual(len(a["features"]), 1)
        self.assertEqual(a["features"], b["features"])
        self.assertEqual(a["features"][0]["id"], self.parse(feed(older))["features"][0]["id"])
        self.assertEqual(a["features"][0]["properties"]["entity_id"], "new")

    def test_source_scoping_and_no_truncated_id_collision(self):
        a, b = vehicle(vehicle_id="a" * 200 + "1"), vehicle(vehicle_id="a" * 200 + "2")
        result = self.parse(feed(a, b))
        self.assertEqual(len({f["id"] for f in result["features"]}), 2)
        qld = TransitAdapter("translink.queensland", decoder=lambda raw: feed(a), clock=lambda: NOW)
        self.assertNotEqual(qld.parse(b"x", ProviderQuery())["features"][0]["id"], result["features"][0]["id"])

    def test_route_join_conflict_unknown_type_and_trip_lookup(self):
        entity = vehicle()
        entity.vehicle.trip = Message(trip_id="t1")
        self.assertEqual(self.parse(feed(entity))["features"][0]["properties"]["mode"], "bus")
        entity.vehicle.trip = Message(route_id="wrong", trip_id="t1")
        p = self.parse(feed(entity))["features"][0]["properties"]
        self.assertEqual(p["schedule_join"], "conflicting_route")
        self.assertIsNone(p["mode"])
        lookup = ScheduleLookup(PROVIDER, {"r1": {"route_type": 999}})
        result = self.parse(feed(vehicle()), schedule=lookup)
        self.assertIsNone(result["features"][0]["properties"]["mode"])
        self.assertTrue(result["partial"])

    def test_trip_delays_dedup_presence_no_position_or_invented_time(self):
        stop = Message(stop_id="s1", stop_sequence=1, arrival=Message(delay=0, time=NOW + 1000), departure=Message(delay=-30))
        update = Message(trip=Message(trip_id="t1"), stop_time_update=[stop, stop], delay=-20)
        result = self.parse(feed(Message(id="u1", trip_update=update)), ProviderQuery(dataset="trips"))
        self.assertEqual(result["features"], [])
        p = result["records"][0]
        self.assertIsNone(p["position"])
        self.assertIsNone(p["observed_at"])
        self.assertEqual(p["delay_seconds"], -20)
        self.assertEqual(len(p["stop_updates"]), 1)
        self.assertEqual(p["stop_updates"][0]["arrival_delay_seconds"], 0)
        self.assertEqual(p["stop_updates"][0]["departure_delay_seconds"], -30)
        self.assertNotIn("time", p["stop_updates"][0])

    def test_trip_instances_have_stable_distinct_identity(self):
        def trip(date, entity_id):
            return Message(id=entity_id, trip_update=Message(trip=Message(trip_id="t1", start_date=date), stop_time_update=[], timestamp=NOW))
        a = self.parse(feed(trip("20261016", "a"), trip("20261017", "b")), ProviderQuery(dataset="trips"))
        self.assertEqual(len(a["records"]), 2)
        b = self.parse(feed(trip("20261016", "different")), ProviderQuery(dataset="trips"))
        self.assertEqual(a["records"][0]["id"], b["records"][0]["id"])

    def test_caps_apply_before_decoder_and_to_entities_stops_results(self):
        decoder = mock.Mock()
        adapter = TransitAdapter(PROVIDER, decoder=decoder, max_bytes=2)
        self.error(413, adapter.parse, b"xxx", ProviderQuery())
        decoder.assert_not_called()
        self.error(413, self.parse, feed(vehicle(), vehicle()), max_entities=1)
        update = Message(trip=Message(trip_id="t1"), stop_time_update=[Message()] * (transit.MAX_STOP_UPDATES + 1))
        self.error(413, self.parse, feed(Message(id="x", trip_update=update)), ProviderQuery(dataset="trips"))
        result = self.parse(feed(vehicle(vehicle_id="a"), vehicle(vehicle_id="b")), ProviderQuery(limit=1))
        self.assertTrue(result["truncated"])
        self.assertTrue(result["partial"])

    def test_fixed_requests_and_no_arbitrary_controls(self):
        for provider in transit.FEEDS:
            adapter = TransitAdapter(provider, decoder=lambda raw: feed())
            for dataset in ("vehicles", "trips"):
                request = adapter.request(ProviderQuery(dataset=dataset))
                self.assertEqual(request.origin, transit.FEEDS[provider][0])
                self.assertTrue(request.url.startswith(request.origin + transit.FEEDS[provider][1]))
                self.assertEqual(request.max_decompressed, transit.MAX_BYTES)
                self.assertEqual(adapter.format, "protobuf")
                self.assertIn("application/x-protobuf", request.media_types)
                self.assertIn(("Accept", "application/x-protobuf"), request.headers)
                if provider == PROVIDER:
                    self.assertIn(("ET-Client-Name", "Meridian-local-transit"), request.headers)
            for query in (ProviderQuery(dataset="arbitrary"), ProviderQuery(pages=2), ProviderQuery(text="route_id=x"),
                          ProviderQuery(latitude=0, longitude=0)):
                self.error(400, adapter.request, query)
        self.error(404, TransitAdapter, "mbta.gtfs_rt")
        self.error(400, ProviderQuery.from_dict, {"schedule_path": "secret.csv"})

    def test_bbox_filter_and_partial_differential_deleted(self):
        self.assertEqual(self.parse(feed(vehicle()), ProviderQuery(bbox=(0, 0, 1, 1)))["features"], [])
        result = self.parse(feed(vehicle(), Message(id="gone", is_deleted=True), incrementality=1))
        self.assertTrue(result["partial"])
        self.assertEqual(len(result["features"]), 1)

    def test_missing_decoder_setup_and_parse_errors_are_safe(self):
        with mock.patch.object(transit.importlib, "import_module", side_effect=ModuleNotFoundError("fixture")):
            adapter = TransitAdapter(PROVIDER)
            self.assertEqual(adapter.status()["state"], "needs_setup")
            self.error(409, adapter.request, ProviderQuery())
            self.error(409, adapter.parse, b"x", ProviderQuery())
        adapter = TransitAdapter(PROVIDER, decoder=mock.Mock(side_effect=ValueError("secret")))
        self.assertNotIn("secret", str(self.error(422, adapter.parse, b"x", ProviderQuery())))
        self.error(422, self.parse, Message(entity=[]))
        self.error(422, self.adapter(feed()).parse, {}, ProviderQuery())

    def test_default_decoder_import_is_lazy_and_protobuf_is_checked(self):
        proto_feed = feed(vehicle())
        proto_feed.ParseFromString = mock.Mock()
        proto_feed.IsInitialized = lambda: True
        module = Message(FeedMessage=lambda: proto_feed)
        with mock.patch.object(transit.importlib, "import_module", return_value=module) as imported:
            adapter = TransitAdapter(PROVIDER, schedule=self.schedule, clock=lambda: NOW)
            imported.assert_not_called()
            self.assertEqual(len(adapter.parse(b"raw", ProviderQuery())["features"]), 1)
            imported.assert_called_once_with("google.transit.gtfs_realtime_pb2")
            proto_feed.ParseFromString.assert_called_once_with(b"raw")
            proto_feed.IsInitialized = lambda: False
            self.error(422, adapter.parse, b"x", ProviderQuery())

    def test_runtime_raw_bridge_and_pinned_transport_without_network(self):
        from backend.providers import ProviderRuntime, QuotaStore
        from backend.providers import transport
        from backend.test_providers import FakeConnection, FakeResponse

        decoder = mock.Mock(return_value=feed(vehicle()))
        adapter = TransitAdapter(PROVIDER, schedule=self.schedule, decoder=decoder, clock=lambda: NOW)
        FakeConnection.response = FakeResponse(b"protobuf-fixture", headers={"Content-Type": "application/x-protobuf"})
        FakeConnection.calls = []
        with tempfile.TemporaryDirectory() as root:
            quota = QuotaStore(Path(root) / "quota.sqlite")
            runtime = ProviderRuntime(quota, policy_gate=lambda *_: True, adapters={PROVIDER: adapter})
            try:
                with mock.patch.object(transport.web, "_resolve_public", return_value=None), mock.patch.object(transport.web, "_PinnedHTTPSConnection", FakeConnection):
                    result = runtime.execute(PROVIDER, ProviderQuery())
                self.assertEqual(result["features"][0]["geometry"]["coordinates"], [153.0, -27.5])
                decoder.assert_called_once_with(b"protobuf-fixture")
                self.assertEqual(FakeConnection.calls[0][1]["headers"]["ET-Client-Name"], "Meridian-local-transit")
                self.assertEqual(quota.snapshot(PROVIDER)["usage"][0]["used"], 1)
            finally:
                runtime.close()

    def test_import_inert_without_protobuf_config_or_network(self):
        code = ("import sys,socket,importlib; from unittest.mock import patch; "
                "p=patch.object(socket,'socket',side_effect=AssertionError('network'));p.start(); "
                "import backend.providers.transit; "
                "assert 'google.transit.gtfs_realtime_pb2' not in sys.modules; "
                "assert 'backend.config' not in sys.modules; assert 'backend.server' not in sys.modules")
        run = subprocess.run([sys.executable, "-B", "-c", code], capture_output=True, text=True, timeout=10)
        self.assertEqual(run.returncode, 0, run.stderr)


class ScheduleTests(unittest.TestCase):
    error = TransitTests.error

    def setUp(self):
        TransitTests.setUp(self)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def csv(self, raw):
        path = self.root / "routes.csv"
        path.write_bytes(raw)
        return path

    def archive(self, entries, compression=zipfile.ZIP_STORED):
        path = self.root / "schedule.zip"
        with zipfile.ZipFile(path, "w", compression=compression) as archive:
            for name, raw in entries:
                if isinstance(name, str):
                    info = zipfile.ZipInfo(name)
                    # Windows ZipInfo normalizes backslashes; preserve hostile wire names.
                    info.filename = name
                    info.compress_type = compression
                    name = info
                archive.writestr(name, raw)
        return path

    def test_routes_csv_and_gtfs_zip_immutable_scoped(self):
        raw = b"route_id,route_type,route_short_name\nr1,3,100\nr2,4,Ferry\n"
        lookup = load_schedule(self.csv(raw), PROVIDER)
        self.assertEqual(lookup.resolve("r2", None)[1]["route_type"], 4)
        with self.assertRaises(TypeError):
            lookup.routes["r2"]["route_type"] = 3
        with self.assertRaises(AttributeError):
            lookup.provider_id = "translink.queensland"
        path = self.archive([("routes.txt", raw), ("trips.txt", b"route_id,trip_id\nr1,t1\n"), ("stops.txt", b"unused")])
        lookup = load_schedule(path, PROVIDER)
        self.assertEqual(lookup.resolve(None, "t1")[0], "r1")
        with self.assertRaises(ValueError):
            TransitAdapter("translink.queensland", schedule=lookup)

    def test_zip_slip_symlink_duplicate_and_bomb_rejected_without_extracting(self):
        routes = ("routes.txt", b"route_id,route_type\nr1,3\n")
        for name in ("../outside.txt", "/absolute", "C:/secret", "nested\\evil"):
            with self.subTest(name=name):
                self.error(422, load_schedule, self.archive([routes, (name, b"x")]), PROVIDER)
        symlink = zipfile.ZipInfo("link")
        symlink.create_system = 3
        symlink.external_attr = (stat.S_IFLNK | 0o777) << 16
        self.error(422, load_schedule, self.archive([routes, (symlink, b"target")]), PROVIDER)
        with self.assertWarns(UserWarning):
            path = self.archive([routes, routes])
        self.error(422, load_schedule, path, PROVIDER)
        self.error(413, load_schedule, self.archive([routes, ("bomb.txt", b"0" * 100000)], zipfile.ZIP_DEFLATED), PROVIDER)
        self.assertFalse((self.root / "routes.txt").exists())

    def test_zip_entry_total_and_csv_row_caps(self):
        path = self.archive([(f"{i}.txt", b"x") for i in range(65)])
        self.error(413, load_schedule, path, PROVIDER)
        with mock.patch.object(transit, "MAX_ROUTES", 1):
            self.error(413, load_schedule, self.csv(b"route_id,route_type\na,3\nb,4\n"), PROVIDER)
        with mock.patch.object(transit, "MAX_SCHEDULE_BYTES", 10):
            self.error(413, load_schedule, self.csv(b"route_id,route_type\na,3\n"), PROVIDER)

    def test_invalid_local_schedules_and_no_path_disclosure(self):
        for raw in (b"route_id\na\n", b"route_id,route_type\na,nope\n", b"route_id,route_type\na,3\na,4\n",
                    b"route_id,route_type\n,3\n", b"route_id,route_type\na,3,extra\n", b"\xff"):
            self.error(422, load_schedule, self.csv(raw), PROVIDER)
        self.error(422, load_schedule, self.archive([("other.txt", b"x")]), PROVIDER)
        self.error(422, load_schedule, self.archive([("routes.txt", b"route_id,route_type\nr1,3\n"),
            ("trips.txt", b"route_id,trip_id\nmissing,t1\n")]), PROVIDER)
        error = self.error(409, load_schedule, self.root / "private-missing.csv", PROVIDER)
        self.assertNotIn("private", str(error))
        self.error(409, load_schedule, "https://example.org/routes.csv", PROVIDER)


if __name__ == "__main__":
    unittest.main()
