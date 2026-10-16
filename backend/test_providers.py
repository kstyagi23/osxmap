"""Offline provider regressions: python -B -m unittest backend.test_providers."""

from concurrent.futures import ThreadPoolExecutor
import gzip
import io
import json
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock
from pathlib import Path

from backend.errors import ServiceError
from backend.providers import ADAPTERS, ProviderQuery, ProviderRuntime, QuotaRule, QuotaStore, Request, HTTPSPinnedTransport
from backend.providers import transport
from backend.providers.transport import validate_origin_url


BBOX = (-1, 50, 1, 52)
AIRCRAFT = {"now": 1700000000, "ac": [{"hex": "abc123", "lat": 51, "lon": 0, "flight": "TEST1",
    "alt_baro": 10000, "gs": 100, "seen_pos": 2, "track": 90}, {"hex": "no-position"}]}


class OfflineCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=r"C:\Users\kstya\AppData\Local\Temp\kilo")
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "quota.sqlite"
        self.quota = QuotaStore(self.path)
        for name in ("getaddrinfo", "socket"):
            patch = mock.patch.object(socket, name, side_effect=AssertionError("Live networking forbidden"))
            patch.start()
            self.addCleanup(patch.stop)

    def error(self, status, callback, *args, **kwargs):
        with self.assertRaises(ServiceError) as caught:
            callback(*args, **kwargs)
        self.assertEqual(caught.exception.status, status)
        return caught.exception


class QueryTests(OfflineCase):
    def test_bounds_and_unknown_fields(self):
        for value in ({"url": "https://example.org"}, {"limit": True}, {"pages": 4}, {"bbox": [-180, -90, 180, 90]},
                      {"bbox": [1, 2, 0, 3]}, {"latitude": 50}, {"latitude": float("nan"), "longitude": 0},
                      {"entity_id": "../secret"}, {"start": "2026-01-01", "end": "2026-01-02"},
                      {"start": "2026-01-01T00:00:00Z", "end": "2026-03-01T00:00:00Z"}):
            self.error(400, ProviderQuery.from_dict, value)
        self.assertEqual(ProviderQuery.from_dict({"bbox": list(BBOX)}).bbox, BBOX)

    def test_inert_imports(self):
        code = ("import sys,socket,sqlite3; from unittest.mock import patch; "
                "p=patch.object(socket,'getaddrinfo',side_effect=AssertionError('DNS')); p.start(); "
                "q=patch.object(sqlite3,'connect',side_effect=AssertionError('DB')); q.start(); "
                "import backend.providers; assert 'backend.server' not in sys.modules; "
                "assert 'backend.config' not in sys.modules")
        result = subprocess.run([sys.executable, "-B", "-c", code], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)


class QuotaTests(OfflineCase):
    def test_atomic_concurrency_and_restart(self):
        rule = (QuotaRule(limit=5),)
        def reserve(_):
            try:
                return QuotaStore(self.path).reserve("p", "public", rule)
            except ServiceError:
                return None
        with ThreadPoolExecutor(max_workers=12) as pool:
            tokens = list(pool.map(reserve, range(20)))
        self.assertEqual(sum(t is not None for t in tokens), 5)
        restarted = QuotaStore(self.path)
        self.error(429, restarted.reserve, "p", "public", rule)
        self.assertEqual(restarted.snapshot("p")["uncertain_reservations"], 5)

    def test_multidimension_atomic_reconcile_ambiguous(self):
        rules = (QuotaRule(limit=10), QuotaRule(unit="processing_units", limit=2))
        token = self.quota.reserve("p", "account", rules, {"requests": 1, "processing_units": 2})
        self.error(429, self.quota.reserve, "p", "account", rules, {"requests": 1, "processing_units": 1})
        self.assertEqual(self.quota.snapshot("p", "account")["usage"][1]["used"], 1)
        self.quota.finish(token, actual={"requests": 1, "processing_units": 1})
        token2 = self.quota.reserve("p", "account", rules, {"requests": 1, "processing_units": 1})
        self.quota.finish(token2, ambiguous=True)
        self.assertEqual(self.quota.snapshot("p", "account")["uncertain_reservations"], 1)
        with self.assertRaises(ValueError):
            self.quota.finish(token2, actual={"requests": 0, "processing_units": 0})

    def test_window_boundary_and_clock_rollback(self):
        now = [3599]
        store = QuotaStore(self.path, clock=lambda: now[0])
        rule = (QuotaRule(limit=1),)
        store.reserve("p", "public", rule)
        now[0] = 3600
        store.reserve("p", "public", rule)
        now[0] = 1
        self.error(429, store.reserve, "p", "public", rule)
        self.assertEqual(QuotaRule(calendar="month").window(1735689600), (1735689600, 1738368000))


class FakeResponse:
    def __init__(self, raw=b"{}", status=200, headers=None):
        self.status, self.stream = status, io.BytesIO(raw)
        self.headers = {"Content-Type": "application/json", "Content-Length": str(len(raw)), **(headers or {})}
    def getheader(self, key, default=None):
        return self.headers.get(key, default)
    def read1(self, size):
        return self.stream.read(size)
    def close(self):
        pass


class FakeConnection:
    response = None
    calls = []
    def __init__(self, *args):
        self.args, self._transport_socket = args, None
    def request(self, *args, **kwargs):
        self.calls.append((args, kwargs))
    def getresponse(self):
        return self.response
    def close(self):
        pass


class TransportTests(OfflineCase):
    def test_binary_formats_only_on_reviewed_transit_origins(self):
        self.error(400, self.fetch, FakeResponse(b'feed', headers={'Content-Type': 'application/x-protobuf'}), media_types=('application/x-protobuf',))
        FakeConnection.response, FakeConnection.calls = FakeResponse(b'feed', headers={'Content-Type': 'application/x-protobuf'}), []
        addr = (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, '', ('8.8.8.8', 443))
        with mock.patch.object(transport.web, '_resolve_public', return_value=addr), mock.patch.object(transport.web, '_PinnedHTTPSConnection', FakeConnection):
            raw = HTTPSPinnedTransport().fetch(Request('https://api.entur.io/realtime/v1/vehicles', 'https://api.entur.io', media_types=('application/x-protobuf',)))
        self.assertEqual(raw, b'feed')

    def fetch(self, response, **bounds):
        FakeConnection.response, FakeConnection.calls = response, []
        addr = (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("8.8.8.8", 443))
        with mock.patch.object(transport.web, "_resolve_public", return_value=addr), mock.patch.object(transport.web, "_PinnedHTTPSConnection", FakeConnection):
            return HTTPSPinnedTransport().fetch(Request("https://api.adsb.lol/v2/a", "https://api.adsb.lol", **bounds))

    def test_exact_origin_https_and_userinfo(self):
        for url in ("http://api.adsb.lol/a", "https://api.adsb.lol:444/a", "https://user:secret@api.adsb.lol/a",
                    "https://api.adsb.lol.evil.org/a", "https://api.adsb.lol./a", "https://api.adsb.lol/a#x", "https://127.0.0.1/a"):
            err = self.error(400, validate_origin_url, url, "https://api.adsb.lol")
            self.assertNotIn("secret", str(err))

    def test_redirect_never_forward_credentials(self):
        self.error(502, self.fetch, FakeResponse(status=302, headers={"Location": "https://evil.org/?secret=x"}))
        self.assertEqual(len(FakeConnection.calls), 1)

    def test_wire_decoded_gzip_and_incomplete_bounds(self):
        raw = gzip.compress(b'{"data":"' + b"x" * 10000 + b'"}')
        self.assertEqual(len(self.fetch(FakeResponse(raw, headers={"Content-Encoding": "gzip"}))), 10011)
        self.error(413, self.fetch, FakeResponse(raw, headers={"Content-Encoding": "gzip"}), max_decompressed=100)
        self.error(413, self.fetch, FakeResponse(b"x" * 100), max_compressed=10)
        self.error(422, self.fetch, FakeResponse(raw[:-1], headers={"Content-Encoding": "gzip"}))
        self.error(422, self.fetch, FakeResponse(raw + raw, headers={"Content-Encoding": "gzip"}))
        self.error(502, self.fetch, FakeResponse(b"{}", headers={"Content-Length": "3"}))
        self.error(415, self.fetch, FakeResponse(headers={"Content-Encoding": "br"}))

    def test_mixed_public_private_dns_is_rejected(self):
        public = (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("8.8.8.8", 443))
        private = (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("127.0.0.1", 443))
        with mock.patch.object(socket, "getaddrinfo", return_value=[public, private]):
            self.error(400, transport.web._resolve_public, "api.adsb.lol", 443, time.monotonic() + 2)

    def test_retry_after(self):
        err = self.error(429, self.fetch, FakeResponse(status=429, headers={"Retry-After": "123"}))
        self.assertEqual(err.retry_after, 123)

    def test_no_arbitrary_origin_even_public(self):
        self.error(400, validate_origin_url, "https://example.org/data", "https://example.org")

    def test_post_body_bound_and_json_credential_scope(self):
        request = Request("https://api.openai.com/v1/responses", "https://api.openai.com",
            headers=(("Authorization", "Bearer fixture-secret"),), method="POST", body=b'{"model":"fixture"}')
        FakeConnection.response, FakeConnection.calls = FakeResponse(), []
        with mock.patch.object(transport.web, "_resolve_public", return_value=None), mock.patch.object(transport.web, "_PinnedHTTPSConnection", FakeConnection):
            self.assertEqual(HTTPSPinnedTransport().fetch(request), b"{}")
            args, kwargs = FakeConnection.calls[0]
            self.assertEqual(args[0], "POST")
            self.assertEqual(kwargs["headers"]["Content-Type"], "application/json")
            FakeConnection.response = FakeResponse(status=302)
            self.error(502, HTTPSPinnedTransport().fetch, request)
            self.assertEqual(len(FakeConnection.calls), 2)
        self.error(400, HTTPSPinnedTransport().fetch, Request("https://api.openai.com/v1/responses", "https://api.openai.com", method="POST", body=b"x" * (512 * 1024 + 1)))
        self.assertNotIn("fixture-secret", repr(request))

    def test_total_header_deadline(self):
        class SlowConnection(FakeConnection):
            def getresponse(self):
                time.sleep(.04)
                return FakeResponse()
        with mock.patch.object(transport.web, "_resolve_public", return_value=None), mock.patch.object(transport.web, "_PinnedHTTPSConnection", SlowConnection):
            self.error(504, HTTPSPinnedTransport().fetch, Request("https://api.adsb.lol/a", "https://api.adsb.lol", timeout=.01))


class AdapterTests(OfflineCase):
    def parse(self, provider, data, **kwargs):
        return ADAPTERS[provider].parse(data, ProviderQuery(**kwargs))

    def test_aircraft_observations_and_si(self):
        result = self.parse("adsblol.public", AIRCRAFT, bbox=BBOX)
        p = result["features"][0]["properties"]
        self.assertEqual(p["altitude_m"], 3048)
        self.assertAlmostEqual(p["speed_m_s"], 51.4444)
        self.assertEqual(p["observed_at"], "2023-11-14T22:13:18Z")
        self.assertTrue(result["partial"])
        self.error(400, ADAPTERS["adsblol.public"].request, ProviderQuery(bbox=(-15, 0, 15, 30)))

    def test_celestrak_metadata_not_fake_positions(self):
        result = self.parse("celestrak.gp", [{"NORAD_CAT_ID": 25544, "OBJECT_NAME": "ISS", "EPOCH": "2026-10-15T12:00:00",
            "MEAN_MOTION": 15.5}], dataset="stations")
        self.assertEqual(result["features"], [])
        self.assertIsNone(result["records"][0]["position"])
        self.assertEqual(result["records"][0]["propagation_status"], "needs_setup")
        self.error(400, ADAPTERS["celestrak.gp"].request, ProviderQuery(dataset="supgp"))

    def test_launches_pad_not_telemetry(self):
        result = self.parse("thespacedevs.ll2", {"count": 1, "results": [{"id": "launch1", "name": "Demo", "net": "2026-10-16T00:00:00Z",
            "pad": {"latitude": "28.5", "longitude": "-80.6"}, "status": {"name": "Go"}}]})
        self.assertEqual(result["features"][0]["geometry"]["coordinates"], [-80.6, 28.5])
        self.assertIn("not ascent", result["records"][0]["position_kind"])

    def test_nws_null_geometry_is_metadata_not_point(self):
        result = self.parse("noaa.nws", {"features": [{"id": "alert", "geometry": None,
            "properties": {"event": "Flood", "sent": "2026-10-15T00:00:00Z", "areaDesc": "Named area"}}]}, latitude=40, longitude=-100)
        self.assertEqual(result["features"], [])
        self.assertEqual(result["records"][0]["event"], "Flood")
        request = ADAPTERS["noaa.nws"].request(ProviderQuery(latitude=40, longitude=-100))
        self.assertIn("/alerts/active?point=", request.url)

    def test_gdelt_no_inferred_event_coordinates_or_images(self):
        result = self.parse("gdelt.doc2", {"articles": [{"title": "News", "url": "https://publisher.example/story", "sourcecountry": "US", "socialimage": "https://image.example/private"}]})
        self.assertEqual(result["features"], [])
        self.assertIsNone(result["records"][0]["location"])
        self.assertNotIn("socialimage", result["records"][0])
        query = ProviderQuery(text="foo OR bar", start="2026-10-01T00:00:00Z", end="2026-10-02T00:00:00Z")
        self.assertIn("%22foo+OR+bar%22", ADAPTERS["gdelt.doc2"].request(query).url)

    def test_digitraffic_catalogue_capture_unknown(self):
        result = self.parse("digitraffic.cameras", {"features": [{"id": "C1", "geometry": {"type": "Point", "coordinates": [0, 51]},
            "properties": {"name": "Road", "presets": [{"id": "P1", "imageUrl": "https://evil.example/image"}]}}]}, bbox=BBOX)
        p = result["features"][0]["properties"]
        self.assertIsNone(p["capture_time"])
        self.assertNotIn("imageUrl", str(p))

    def test_cmr_preserves_all_polygons_bounded_dataset(self):
        polygon = {"Boundary": {"Points": [{"Longitude": 0, "Latitude": 50}, {"Longitude": 1, "Latitude": 50}, {"Longitude": 1, "Latitude": 51}]}}
        data = {"hits": 200, "items": [{"meta": {"concept-id": "G1"}, "umm": {"GranuleUR": "HLS",
            "TemporalExtent": {"RangeDateTime": {"BeginningDateTime": "2026-10-15T00:00:00Z"}},
            "SpatialExtent": {"HorizontalSpatialDomain": {"Geometry": {"GPolygons": [polygon, polygon]}}}}}]}
        result = self.parse("nasa.cmr", data, dataset="HLSS30")
        self.assertEqual(len(result["features"][0]["geometry"]["coordinates"]), 2)
        self.assertTrue(result["truncated"])
        self.error(400, ADAPTERS["nasa.cmr"].request, ProviderQuery(bbox=BBOX, dataset="arbitrary", start="2026-10-01T00:00:00Z", end="2026-10-02T00:00:00Z"))

    def test_transit_setup_blockers_and_no_unsupported_adapters(self):
        runtime = ProviderRuntime(self.quota, policy_gate=lambda *_: True)
        for provider in ("entur.open_data", "translink.queensland"):
            self.assertEqual(runtime.status(provider)["state"], "needs_setup")
            self.error(409, runtime.execute, provider, ProviderQuery(bbox=BBOX))
            self.assertEqual(self.quota.snapshot(provider)["usage"], [])
        self.error(404, runtime.execute, "arbitrary.url", ProviderQuery())


class FixtureTransport:
    def __init__(self, value=AIRCRAFT):
        self.value, self.count = value, 0
        self.entered, self.release = threading.Event(), threading.Event()
        self.block = False
        self.error = None
    def fetch(self, request, cancel=None):
        self.count += 1
        self.entered.set()
        if self.block:
            while not self.release.wait(.01):
                if cancel.is_set():
                    raise ServiceError("Cancelled.", 499)
        if self.error:
            raise self.error
        return json.dumps(self.value).encode()


class RuntimeTests(OfflineCase):
    def test_policy_callbacks_never_run_under_runtime_lock_and_zero_limit_denies(self):
        fixture = FixtureTransport()
        runtime = None
        def gate(*_):
            self.assertFalse(runtime._lock._is_owned())
            return {"effective_enabled": True}
        runtime = ProviderRuntime(self.quota, transport=fixture, policy_gate=gate)
        self.addCleanup(runtime.close)
        query = ProviderQuery(bbox=BBOX)
        runtime.execute("adsblol.public", query)
        runtime.execute("adsblol.public", query)
        denied = ProviderRuntime(self.quota, transport=fixture, policy_gate=lambda *_: {"effective_enabled": True, "limits": {"requests_hour": 0}})
        self.addCleanup(denied.close)
        with self.assertRaises(ServiceError):
            denied.execute("adsblol.public", query)
        self.assertEqual(fixture.count, 1)

    def make(self, **kwargs):
        self.fixture = FixtureTransport()
        self.enabled = True
        return ProviderRuntime(self.quota, transport=self.fixture, policy_gate=lambda *_: self.enabled, **kwargs)

    def test_policy_before_transport_and_cached_return(self):
        runtime = self.make()
        query = ProviderQuery(bbox=BBOX)
        runtime.execute("adsblol.public", query)
        runtime.execute("adsblol.public", query)
        self.assertEqual(self.fixture.count, 1)
        self.enabled = False
        self.error(403, runtime.execute, "adsblol.public", query)
        self.assertEqual(self.fixture.count, 1)

    def test_singleflight_concurrency_and_durable_one_charge(self):
        runtime = self.make()
        self.fixture.block = True
        query = ProviderQuery(bbox=BBOX)
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(runtime.execute, "adsblol.public", query) for _ in range(8)]
            self.assertTrue(self.fixture.entered.wait(2))
            self.fixture.release.set()
            results = [f.result(timeout=3) for f in futures]
        self.assertEqual(self.fixture.count, 1)
        results[0]["features"].clear()
        self.assertEqual(len(results[1]["features"]), 1)
        self.assertEqual(self.quota.snapshot("adsblol.public")["usage"][0]["used"], 1)

    def test_ambiguous_failures_backoff_and_no_refund(self):
        runtime = self.make()
        self.fixture.error = ServiceError("Throttled.", 429, 60)
        self.error(429, runtime.execute, "adsblol.public", ProviderQuery(bbox=BBOX))
        self.error(429, runtime.execute, "adsblol.public", ProviderQuery(bbox=BBOX))
        self.assertEqual(self.fixture.count, 1)
        snapshot = QuotaStore(self.path).snapshot("adsblol.public")
        self.assertEqual(snapshot["usage"][0]["used"], 1)
        self.assertEqual(snapshot["uncertain_reservations"], 1)

    def test_last_waiter_cancel_aborts_and_retains_charge(self):
        runtime = self.make()
        self.fixture.block = True
        cancel = threading.Event()
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(runtime.execute, "adsblol.public", ProviderQuery(bbox=BBOX), cancel)
            self.assertTrue(self.fixture.entered.wait(2))
            cancel.set()
            self.error(499, future.result, timeout=3)
        runtime.cancel_provider("adsblol.public")
        self.fixture.release.set()
        runtime.close()
        self.assertEqual(self.quota.snapshot("adsblol.public")["usage"][0]["used"], 1)

    def test_admission_bound_and_disable_inflight(self):
        runtime = self.make(workers=1, max_waiters=1)
        self.fixture.block = True
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(runtime.execute, "adsblol.public", ProviderQuery(bbox=BBOX))
            self.assertTrue(self.fixture.entered.wait(2))
            self.error(503, runtime.execute, "adsblol.public", ProviderQuery(bbox=BBOX))
            self.enabled = False
            runtime.cancel_provider("adsblol.public")
            self.fixture.release.set()
            self.error(403, future.result, timeout=3)

    def test_maximum_stale_age(self):
        clock = [0]
        runtime = self.make(clock=lambda: clock[0])
        query = ProviderQuery(bbox=BBOX)
        runtime.execute("adsblol.public", query)
        self.fixture.error = ServiceError("Unavailable.", 502)
        clock[0] = 20
        self.assertEqual(runtime.execute("adsblol.public", query)["state"], "stale")
        clock[0] = 61
        self.error(502, runtime.execute, "adsblol.public", query)

    def test_cancel_one_shared_consumer_does_not_cancel_other(self):
        runtime = self.make()
        self.fixture.block = True
        cancel = threading.Event()
        query = ProviderQuery(bbox=BBOX)
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(runtime.execute, "adsblol.public", query, cancel)
            self.assertTrue(self.fixture.entered.wait(2))
            second = pool.submit(runtime.execute, "adsblol.public", query)
            # Observe explicit admission rather than relying on thread scheduling.
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                with runtime._lock:
                    if runtime._flights[("adsblol.public", query)].waiters == 2:
                        break
                time.sleep(.001)
            cancel.set()
            self.error(499, first.result, timeout=3)
            self.fixture.release.set()
            self.assertEqual(len(second.result(timeout=3)["features"]), 1)
        self.assertEqual(self.fixture.count, 1)

    def test_cmr_pages_and_settings_lowering(self):
        fixture = FixtureTransport({"hits": 1000, "items": []})
        runtime = ProviderRuntime(self.quota, transport=fixture, policy_gate=lambda *_: {"effective_enabled": True,
            "limits": {"max_pages": 2, "requests_hour": 2}})
        query = ProviderQuery(bbox=BBOX, dataset="HLSL30", start="2026-10-01T00:00:00Z", end="2026-10-02T00:00:00Z", pages=3)
        result = runtime.execute("nasa.cmr", query)
        self.assertEqual(fixture.count, 2)
        self.assertTrue(result["truncated"])
        runtime.cancel_provider("nasa.cmr")
        self.error(429, runtime.execute, "nasa.cmr", query)

    def test_cmr_page_failure_retains_bounded_partial_metadata(self):
        data = {"hits": 100, "items": [{"meta": {"concept-id": "G1"}, "umm": {
            "TemporalExtent": {"RangeDateTime": {"BeginningDateTime": "2026-10-01T00:00:00Z"}}}}]}
        class SecondPageFails(FixtureTransport):
            def fetch(self, request, cancel=None):
                self.count += 1
                if self.count == 2:
                    raise ServiceError("Page unavailable.", 502)
                return json.dumps(data).encode()
        fixture = SecondPageFails()
        runtime = ProviderRuntime(self.quota, transport=fixture, policy_gate=lambda *_: True)
        query = ProviderQuery(bbox=BBOX, dataset="HLSL30", start="2026-10-01T00:00:00Z", end="2026-10-02T00:00:00Z", pages=3)
        result = runtime.execute("nasa.cmr", query)
        self.assertEqual(result["state"], "partial")
        self.assertEqual(len(result["records"]), 1)
        self.assertTrue(result["errors"])
        self.assertEqual(self.quota.snapshot("nasa.cmr")["uncertain_reservations"], 1)


class WeatherTests(OfflineCase):
    def query(self, **kwargs):
        return ProviderQuery(latitude=51, longitude=0, **kwargs)

    def openweather(self):
        return {"cod": 200, "dt": 1700000000, "coord": {"lat": 51, "lon": 0},
            "main": {"temp": 280, "pressure": 1000, "humidity": 75}, "wind": {"speed": 4, "deg": 180},
            "rain": {"1h": 2}, "appid": "fixtureSECRET123456789"}

    def meteo(self, aq=False):
        if aq:
            variables = {k: [10, None] for k in ("pm10", "pm2_5", "carbon_monoxide", "nitrogen_dioxide", "sulphur_dioxide", "ozone")}
            units = {k: "\u03bcg/m\u00b3" for k in variables}
        else:
            variables = {"temperature_2m": [10, None], "relative_humidity_2m": [50, 55],
                "surface_pressure": [1000, 1001], "wind_speed_10m": [4, 5], "precipitation": [2, 0]}
            units = {"temperature_2m": "\u00b0C", "relative_humidity_2m": "%", "surface_pressure": "hPa",
                "wind_speed_10m": "m/s", "precipitation": "mm"}
        return {"latitude": 51, "longitude": 0, "utc_offset_seconds": 0, "generationtime_ms": 12,
            "hourly": {"time": [1700000000, 1700003600], **variables}, "hourly_units": {"time": "unixtime", **units}}

    def test_openweather_current_scalar_si_no_key_provenance(self):
        result = ADAPTERS["openweather.basic"].parse(self.openweather(), self.query())
        record = result["records"][0]
        self.assertEqual(record["temperature_k"], 280)
        self.assertEqual(record["pressure_pa"], 100000)
        self.assertEqual(record["relative_humidity_fraction"], .75)
        self.assertEqual(record["precipitation_m"], .002)
        self.assertIsNone(record["forecast_issued_at"])
        self.assertIsNotNone(record["observed_at"])
        self.assertNotIn("fixtureSECRET", str(result))

    def test_openweather_forecast_valid_not_issue_or_observation(self):
        value = self.openweather()
        value["rain"] = {"3h": 3}
        data = {"cod": "200", "list": [value], "city": {"coord": value["coord"]}}
        result = ADAPTERS["openweather.basic"].parse(data, self.query(dataset="forecast"))
        record = result["records"][0]
        self.assertEqual(record["precipitation_interval_seconds"], 10800)
        self.assertIsNone(record["observed_at"])
        self.assertIsNone(record["forecast_issued_at"])
        self.assertEqual(record["valid_at"], "2023-11-14T22:13:20Z")
        request = ADAPTERS["openweather.basic"].request(self.query(dataset="forecast"), credentials={"api_key": "fixtureSECRET123456789"})
        self.assertIn("/data/2.5/forecast?", request.url)
        self.assertNotIn("onecall", request.url)
        self.assertNotIn("fixtureSECRET", repr(request))

    def test_meteo_weather_si_nulls_units_and_unknown_model_issue(self):
        result = ADAPTERS["openmeteo.weather"].parse(self.meteo(), self.query())
        record = result["records"][0]
        self.assertEqual(record["temperature_k"], 283.15)
        self.assertEqual(record["pressure_pa"], 100000)
        self.assertEqual(record["wind_speed_m_s"], 4)
        self.assertIsNone(record["forecast_issued_at"])
        self.assertIsNone(record["model"])
        self.assertIsNone(result["records"][1]["temperature_k"])
        request = ADAPTERS["openmeteo.weather"].request(self.query())
        self.assertIn("forecast_days=2", request.url)
        data = self.meteo()
        data["hourly_units"]["wind_speed_10m"] = "km/h"
        self.error(422, ADAPTERS["openmeteo.weather"].parse, data, self.query())
        data = self.meteo()
        data["hourly"]["precipitation"] = [1]
        self.error(422, ADAPTERS["openmeteo.weather"].parse, data, self.query())

    def test_air_quality_mass_density_not_station_measurement(self):
        result = ADAPTERS["openmeteo.air_quality"].parse(self.meteo(aq=True), self.query())
        self.assertAlmostEqual(result["records"][0]["pm2_5_kg_m3"], 1e-8)
        self.assertEqual(result["records"][0]["data_kind"], "modeled forecast")
        self.assertIsNone(result["records"][0]["observed_at"])
        request = ADAPTERS["openmeteo.air_quality"].request(self.query())
        self.assertTrue(request.url.startswith("https://air-quality-api.open-meteo.com/v1/air-quality?"))
        data = self.meteo(aq=True)
        data["hourly"]["time"] *= 25
        self.error(422, ADAPTERS["openmeteo.air_quality"].parse, data, self.query())

    def test_rainviewer_only_metadata_no_dynamic_host_or_path(self):
        value = {"host": "https://evil.example", "generated": 1700000000,
            "radar": {"past": [{"time": 1699999400, "path": "/private/secret"}],
                "nowcast": [{"time": 1700000600, "path": "https://127.0.0.1/a"}]}}
        result = ADAPTERS["rainviewer.public"].parse(value, ProviderQuery())
        self.assertEqual(len(result["records"]), 2)
        self.assertEqual(result["features"], [])
        self.assertNotIn("evil.example", str(result))
        self.assertNotIn("/private", str(result))
        self.assertEqual(ADAPTERS["rainviewer.public"].request(ProviderQuery()).url,
            "https://api.rainviewer.com/public/weather-maps.json")

    def test_fixed_queries_reject_onecall_bulk_and_raw_controls(self):
        for provider in ("openweather.basic", "openmeteo.weather", "openmeteo.air_quality"):
            adapter = ADAPTERS[provider]
            for query in (self.query(dataset="onecall"), self.query(pages=2), self.query(text="appid=secret"),
                    self.query(bbox=BBOX), ProviderQuery(bbox=BBOX), self.query(entity_id="anything")):
                self.error(400, adapter.request, query, credentials={"api_key": "fixtureSECRET123456789"})
        self.error(400, ADAPTERS["rainviewer.public"].request, self.query())

    def test_missing_credentials_no_charge_disable_before_callback(self):
        fixture = FixtureTransport(self.openweather())
        callback = mock.Mock(return_value={})
        enabled = [True]
        runtime = ProviderRuntime(self.quota, policy_gate=lambda *_: enabled[0], transport=fixture, credentials=callback)
        self.error(409, runtime.execute, "openweather.basic", self.query())
        self.assertEqual(fixture.count, 0)
        self.assertEqual(self.quota.snapshot("openweather.basic")["usage"], [])
        callback.reset_mock()
        enabled[0] = False
        self.error(403, runtime.execute, "openweather.basic", self.query())
        callback.assert_not_called()

    def test_credential_injection_public_scope_no_cache_error_redaction(self):
        fixture = FixtureTransport(self.openweather())
        callback = mock.Mock(return_value={"api_key": "fixtureSECRET123456789", "Authorization": "ignored"})
        runtime = ProviderRuntime(self.quota, policy_gate=lambda *_: True, transport=fixture, credentials=callback)
        result = runtime.execute("openweather.basic", self.query())
        runtime.execute("openweather.basic", self.query())
        self.assertEqual(fixture.count, 2)
        self.assertEqual(runtime._cache, {})
        self.assertNotIn("fixtureSECRET", str(result))
        fixture.error = ServiceError("upstream echoed fixtureSECRET123456789", 502)
        error = self.error(502, runtime.execute, "openweather.basic", self.query())
        self.assertNotIn("fixtureSECRET", str(error))
        fixture.error, fixture.value = None, self.meteo()
        callback.reset_mock()
        runtime.execute("openmeteo.weather", self.query())
        callback.assert_not_called()

    def test_nc_optin_gate_real_registry_disable_and_quota(self):
        from backend.service_registry import effective_state, get_product
        for provider in ("openmeteo.weather", "openmeteo.air_quality", "rainviewer.public"):
            product = get_product(provider)
            settings = {"enabled": True, "acknowledged": []}
            dependencies = {key: True for key in product.dependencies}
            fixture = FixtureTransport(self.meteo(aq=provider.endswith("air_quality")) if provider != "rainviewer.public"
                else {"radar": {"past": [], "nowcast": []}})
            runtime = ProviderRuntime(self.quota, transport=fixture, policy_gate=lambda id, query:
                effective_state(id, settings, configured=False, dependencies=dependencies))
            query = ProviderQuery() if provider == "rainviewer.public" else self.query()
            self.error(403, runtime.execute, provider, query)
            self.assertEqual(fixture.count, 0)
            settings["acknowledged"] = list(product.acknowledgements)
            runtime.execute(provider, query)
            settings["enabled"] = False
            runtime.cancel_provider(provider)
            self.error(403, runtime.execute, provider, query)
        fixture = FixtureTransport(self.meteo())
        runtime = ProviderRuntime(self.quota, transport=fixture, policy_gate=lambda *_:
            {"effective_enabled": True, "limits": {"requests_hour": 1}})
        self.error(429, runtime.execute, "openmeteo.weather", self.query())

    def test_new_origins_use_real_pinned_transport_offline(self):
        for provider, query, credentials in (("openweather.basic", self.query(), {"api_key": "fixtureSECRET123456789"}),
                ("openmeteo.weather", self.query(), None), ("openmeteo.air_quality", self.query(), None),
                ("rainviewer.public", ProviderQuery(), None)):
            request = ADAPTERS[provider].request(query, credentials=credentials)
            FakeConnection.response = FakeResponse()
            with mock.patch.object(transport.web, "_resolve_public", return_value=None) as dns, mock.patch.object(transport.web, "_PinnedHTTPSConnection", FakeConnection):
                self.assertEqual(HTTPSPinnedTransport().fetch(request), b"{}")
                dns.assert_called_once()


if __name__ == "__main__":
    unittest.main()
