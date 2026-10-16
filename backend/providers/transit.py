"""Fixed Entur/Queensland GTFS-RT readers; no network or optional imports at import time.

Schedule paths and decoder injection are backend configuration, never query fields.
Decoders return a protobuf FeedMessage (fixtures may implement the same presence API).
"""

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import importlib
import io
from pathlib import Path, PurePosixPath
import stat
import time
from types import MappingProxyType
import zipfile

from ..errors import ServiceError
from .query import ProviderQuery, number
from .transport import Request


FEEDS = MappingProxyType({
    "entur.open_data": ("https://api.entur.io", "/realtime/v1/gtfs-rt/", "Norway", "Entur open data"),
    "translink.queensland": ("https://gtfsrt.api.translink.com.au", "/api/realtime/SEQ/", "South East Queensland", "Translink Queensland"),
})
MAX_BYTES = 4 * 1024 * 1024
MAX_ENTITIES = 10000
MAX_STOP_UPDATES = 20000
MAX_SCHEDULE_BYTES = 32 * 1024 * 1024
MAX_ROUTES = 10000
MAX_TRIPS = 100000
ROUTE_MODES = MappingProxyType({0: "tram", 1: "subway", 2: "rail", 3: "bus", 4: "ferry",
    5: "cable_tram", 6: "aerial_lift", 7: "funicular", 11: "trolleybus", 12: "monorail"})


def _provider(provider_id):
    if provider_id not in FEEDS:
        raise ServiceError("Unsupported transit provider.", 404)
    return FEEDS[provider_id]


def _present(message, field):
    return message is not None and message.HasField(field)


def _value(message, field):
    return getattr(message, field) if _present(message, field) else None


def _text(value):
    return value if isinstance(value, str) and 0 < len(value) <= 1024 and not any(ord(c) < 32 for c in value) else None


def _stamp(value):
    if type(value) is int and 0 < value <= 4102444800:
        return datetime.fromtimestamp(value, timezone.utc).isoformat().replace("+00:00", "Z")
    return None


def _identity(provider, kind, *parts):
    # Length-prefixed components avoid separator and truncation collisions.
    raw = "".join(f"{len(str(p or ''))}:{p or ''}" for p in parts)
    return provider + ":" + kind + ":" + hashlib.sha256(raw.encode()).hexdigest()


@dataclass(frozen=True, init=False)
class ScheduleLookup:
    """Immutable source-scoped, bounded lookup supplied by the local schedule loader."""

    provider_id: str
    routes: object
    trips: object

    def __init__(self, provider_id, routes, trips=None):
        _provider(provider_id)
        trips = {} if trips is None else trips
        if not isinstance(routes, dict) or not isinstance(trips, dict) or len(routes) > MAX_ROUTES or len(trips) > MAX_TRIPS:
            raise ServiceError("Schedule lookup exceeds its bounds.", 413)
        clean = {}
        for route_id, row in routes.items():
            if (not _text(route_id) or not isinstance(row, dict) or set(row) - {"route_type", "route_short_name", "route_long_name"}
                    or type(row.get("route_type")) is not int or not 0 <= row["route_type"] <= 9999
                    or any(v and not _text(v) for k, v in row.items() if k != "route_type")):
                raise ServiceError("Invalid schedule route metadata.", 422)
            clean[route_id] = MappingProxyType(dict(row))
        if any(not _text(k) or not _text(v) or v not in clean for k, v in trips.items()):
            raise ServiceError("Invalid schedule trip join.", 422)
        object.__setattr__(self, "provider_id", provider_id)
        object.__setattr__(self, "routes", MappingProxyType(clean))
        object.__setattr__(self, "trips", MappingProxyType(dict(trips)))

    def resolve(self, route_id, trip_id):
        joined = self.trips.get(trip_id)
        if route_id and joined and route_id != joined:
            return route_id, None, "conflicting_route"
        route_id = route_id or joined
        row = self.routes.get(route_id)
        return route_id, row, "joined" if row is not None else "unmatched"


def _csv_rows(raw, required, maximum):
    try:
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline=""), strict=True)
        if not reader.fieldnames or len(reader.fieldnames) > 64 or len(set(reader.fieldnames)) != len(reader.fieldnames) or not required <= set(reader.fieldnames):
            raise ValueError
        rows = []
        for row in reader:
            if len(rows) >= maximum:
                raise ServiceError("Schedule row limit exceeded.", 413)
            if None in row or any(v is None or len(v) > 1024 for v in row.values()):
                raise ValueError
            rows.append(row)
        return rows
    except (UnicodeError, csv.Error, ValueError):
        raise ServiceError("Invalid local schedule CSV.", 422) from None


def load_schedule(configured_path, provider_id):
    """Read an operator-selected routes CSV or GTFS zip; never extract or fetch assets.

    CSV must contain route_id/route_type; zip must contain root routes.txt and may
    contain root trips.txt. Other safe GTFS entries are validated but not read.
    """
    _provider(provider_id)
    if (not isinstance(configured_path, (str, Path)) or not str(configured_path)
            or "://" in str(configured_path) or str(configured_path).startswith(("\\\\", "//"))):
        raise ServiceError("A backend-configured local schedule path is required.", 409)
    try:
        path = Path(configured_path)
        if path.suffix.lower() not in {".csv", ".zip"} or not path.is_file():
            raise ServiceError("Configure a local routes CSV or GTFS zip.", 409)
        if path.stat().st_size > MAX_SCHEDULE_BYTES:
            raise ServiceError("Schedule file byte limit exceeded.", 413)
        with path.open("rb") as stream:
            raw = stream.read(MAX_SCHEDULE_BYTES + 1)
        if len(raw) > MAX_SCHEDULE_BYTES:
            raise ServiceError("Schedule file byte limit exceeded.", 413)
        trip_rows = []
        if path.suffix.lower() == ".zip":
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                entries = archive.infolist()
                if len(entries) > 64:
                    raise ServiceError("Schedule zip entry limit exceeded.", 413)
                seen, total = set(), 0
                for entry in entries:
                    name = entry.orig_filename
                    parts = PurePosixPath(name).parts
                    mode = entry.external_attr >> 16
                    if (not name or name.startswith("/") or "\\" in name or ":" in name or ".." in parts
                            or any(ord(c) < 32 for c in name)
                            or name in seen or stat.S_ISLNK(mode) or entry.flag_bits & 1
                            or entry.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}):
                        raise ServiceError("Unsafe schedule zip entry.", 422)
                    seen.add(name)
                    total += entry.file_size
                    if total > MAX_SCHEDULE_BYTES or entry.file_size > MAX_SCHEDULE_BYTES or entry.file_size > max(1, entry.compress_size) * 100:
                        raise ServiceError("Schedule zip expansion limit exceeded.", 413)
                if "routes.txt" not in seen:
                    raise ServiceError("GTFS zip requires root routes.txt.", 422)
                def read_entry(name):
                    with archive.open(name) as stream:
                        data = stream.read(MAX_SCHEDULE_BYTES + 1)
                    if len(data) > MAX_SCHEDULE_BYTES:
                        raise ServiceError("Schedule entry byte limit exceeded.", 413)
                    return data
                route_rows = _csv_rows(read_entry("routes.txt"), {"route_id", "route_type"}, MAX_ROUTES)
                if "trips.txt" in seen:
                    trip_rows = _csv_rows(read_entry("trips.txt"), {"trip_id", "route_id"}, MAX_TRIPS)
        else:
            route_rows = _csv_rows(raw, {"route_id", "route_type"}, MAX_ROUTES)
        routes, trips = {}, {}
        for row in route_rows:
            route_id = row["route_id"]
            if route_id in routes or not row["route_type"].isascii() or not row["route_type"].isdigit():
                raise ServiceError("Invalid or duplicate schedule route.", 422)
            routes[route_id] = {"route_type": int(row["route_type"]),
                "route_short_name": row.get("route_short_name") or None,
                "route_long_name": row.get("route_long_name") or None}
        for row in trip_rows:
            if row["trip_id"] in trips:
                raise ServiceError("Duplicate schedule trip.", 422)
            trips[row["trip_id"]] = row["route_id"]
        return ScheduleLookup(provider_id, routes, trips)
    except (OSError, zipfile.BadZipFile, RuntimeError, EOFError, ValueError):
        raise ServiceError("Local schedule could not be loaded.", 422) from None


class TransitAdapter:
    format = "protobuf"
    requires_credentials = False
    ttl = 15
    stale_age = 60
    hourly_limit = 120  # Local ceiling, not a claim about provider entitlement.

    def __init__(self, provider_id, *, schedule=None, decoder=None, clock=time.time, max_bytes=MAX_BYTES,
                 max_entities=MAX_ENTITIES, stale_after=120, client_name="Meridian-local-transit"):
        self.origin, self._path, self.coverage, self.citation = _provider(provider_id)
        if (schedule is not None and (not isinstance(schedule, ScheduleLookup) or schedule.provider_id != provider_id)
                or decoder is not None and not callable(decoder) or not callable(clock)
                or type(max_bytes) is not int or not 1 <= max_bytes <= MAX_BYTES
                or type(max_entities) is not int or not 1 <= max_entities <= MAX_ENTITIES
                or type(stale_after) is not int or not 1 <= stale_after <= 3600
                or not _text(client_name) or len(client_name) > 128):
            raise ValueError("Invalid transit adapter configuration")
        self.id, self.schedule, self.decoder, self.clock = provider_id, schedule, decoder, clock
        self.license = "NLOD 2.0" if provider_id == "entur.open_data" else "CC BY 4.0; agency terms apply"
        self.max_bytes, self.max_entities, self.stale_after, self.client_name = max_bytes, max_entities, stale_after, client_name

    def _decoder(self):
        if self.decoder is not None:
            return self.decoder
        try:
            module = importlib.import_module("google.transit.gtfs_realtime_pb2")
        except ImportError:
            raise ServiceError("GTFS realtime protobuf decoder is not configured; optional google.transit.gtfs_realtime_pb2 is missing.", 409) from None
        def decode(raw):
            feed = module.FeedMessage()
            feed.ParseFromString(raw)
            return feed
        return decode

    @property
    def blocker(self):
        try:
            self._decoder()
        except ServiceError as error:
            return str(error)
        return None

    def status(self):
        blocker = self.blocker
        return {"provider_id": self.id, "state": "needs_setup" if blocker else "ready", "reason": blocker,
            "schedule_configured": self.schedule is not None, "coverage": self.coverage, "live_tested": False}

    def request(self, query, page=1, *, credentials=None):
        self._query(query)
        if page != 1:
            raise ServiceError("Transit feeds do not support pagination.", 400)
        self._decoder()  # Setup blockers must precede network and quota reservation.
        vehicles = query.dataset in {None, "vehicles"}
        if self.id == "entur.open_data":
            suffix = "vehicle-positions" if vehicles else "trip-updates"
            headers = (("ET-Client-Name", self.client_name),)
        else:
            suffix = "VehiclePositions" if vehicles else "TripUpdates"
            headers = ()
        return Request(self.origin + self._path + suffix, self.origin,
            headers + (("Accept", "application/x-protobuf"),), max_compressed=self.max_bytes,
            max_decompressed=self.max_bytes, media_types=("application/protobuf", "application/x-protobuf",
                "application/vnd.google.protobuf", "application/octet-stream"))

    @staticmethod
    def _query(query):
        if (not isinstance(query, ProviderQuery) or query.dataset not in {None, "vehicles", "trips"}
                or query.pages != 1 or query.start is not None or query.latitude is not None or query.text is not None):
            raise ServiceError("Transit accepts a viewport/entity filter and fixed vehicles or trips dataset only.", 400)

    def parse(self, raw, query):
        self._query(query)
        if not isinstance(raw, bytes):
            raise ServiceError("GTFS realtime requires bytes.", 422)
        if len(raw) > self.max_bytes:
            raise ServiceError("GTFS realtime byte limit exceeded.", 413)
        decoder = self._decoder()
        try:
            return self._parse_feed(decoder(raw), query)
        except ServiceError:
            raise
        except Exception:
            raise ServiceError("Invalid GTFS realtime feed.", 422) from None

    def _parse_feed(self, feed, query):
        if hasattr(feed, "IsInitialized") and not feed.IsInitialized():
            raise ServiceError("Incomplete GTFS realtime feed.", 422)
        if not _present(feed, "header") or _value(feed.header, "gtfs_realtime_version") not in {"1.0", "2.0"}:
            raise ServiceError("Invalid GTFS realtime header.", 422)
        if len(feed.entity) > self.max_entities:
            raise ServiceError("GTFS realtime entity limit exceeded.", 413)
        now = self.clock()
        if not number(now, 0, 4102444800):
            raise ValueError("Invalid transit clock")
        header_ts = _value(feed.header, "timestamp")
        header_stamp = _stamp(header_ts)
        partial = not header_stamp or header_ts > now or _value(feed.header, "incrementality") == 1
        rejected, stop_count, stale = 0, 0, bool(header_stamp and now - header_ts > self.stale_after)
        items = {}
        vehicles = query.dataset in {None, "vehicles"}
        for entity in feed.entity:
            if _value(entity, "is_deleted") is True:
                partial = True
                continue
            field = "vehicle" if vehicles else "trip_update"
            if not _present(entity, field):
                continue
            message = getattr(entity, field)
            trip = _value(message, "trip")
            route_id, trip_id = _text(_value(trip, "route_id")), _text(_value(trip, "trip_id"))
            start_date, start_time = _text(_value(trip, "start_date")), _text(_value(trip, "start_time"))
            vehicle = _value(message, "vehicle")
            vehicle_id = _text(_value(vehicle, "id"))
            entity_id = _text(_value(entity, "id"))
            if not (vehicle_id if vehicles else trip_id) and not trip_id and not entity_id:
                rejected += 1
                continue
            resolved, route, join = (self.schedule.resolve(route_id, trip_id) if self.schedule else (route_id, None, "not_configured"))
            ts = _value(message, "timestamp")
            observed = _stamp(ts)
            age = now - ts if observed else None
            record_stale = age is not None and age > self.stale_after
            partial |= observed is None or age is not None and age < 0 or join != "joined"
            stale |= record_stale
            identity = (_identity(self.id, "vehicle", vehicle_id) if vehicles and vehicle_id else
                _identity(self.id, field, trip_id, start_date, start_time) if trip_id else _identity(self.id, field, entity_id))
            properties = {"provider_id": self.id, "entity_id": entity_id, "vehicle_id": vehicle_id,
                "data_kind": "transit vehicle observation" if vehicles else "transit trip update",
                "route_id": resolved, "trip_id": trip_id, "start_date": start_date, "start_time": start_time,
                "route_type": route["route_type"] if route else None,
                "mode": ROUTE_MODES.get(route["route_type"]) if route else None,
                "route_short_name": route.get("route_short_name") if route else None,
                "route_long_name": route.get("route_long_name") if route else None,
                "schedule_join": join, "observed_at": observed, "age_seconds": age,
                "stale": record_stale, "timestamp_status": "unknown" if not observed else "future" if age < 0 else "observed"}
            if route and properties["mode"] is None:
                partial = True
            shape = None
            if vehicles:
                position = _value(message, "position")
                lat, lon = _value(position, "latitude"), _value(position, "longitude")
                if not number(lat, -90, 90) or not number(lon, -180, 180):
                    rejected += 1
                    continue
                shape = {"type": "Point", "coordinates": [lon, lat]}
                speed, bearing = _value(position, "speed"), _value(position, "bearing")
                properties.update(position_kind="vehicle observation", speed_m_s=speed if number(speed, 0, 1000) else None,
                    bearing_deg=bearing if number(bearing, 0, 360) else None)
                if query.bbox and not (query.bbox[0] <= lon <= query.bbox[2] and query.bbox[1] <= lat <= query.bbox[3]):
                    continue
            else:
                stop_count += len(message.stop_time_update)
                if stop_count > MAX_STOP_UPDATES:
                    raise ServiceError("GTFS realtime stop update limit exceeded.", 413)
                stops = {}
                for stop in message.stop_time_update:
                    stop_id, sequence = _text(_value(stop, "stop_id")), _value(stop, "stop_sequence")
                    if not stop_id and sequence is None:
                        partial = True
                        continue
                    delays = {"stop_id": stop_id, "stop_sequence": sequence}
                    for kind in ("arrival", "departure"):
                        event = _value(stop, kind)
                        delay = _value(event, "delay")
                        delays[kind + "_delay_seconds"] = delay if type(delay) is int else None
                        delays[kind + "_scheduled_relationship"] = _value(stop, "schedule_relationship")
                    stops[(stop_id, sequence)] = delays
                properties.update(position=None, delay_seconds=_value(message, "delay"), stop_updates=list(stops.values()))
                if query.bbox:
                    # Trip updates have no measured position; a viewport cannot locate them.
                    partial = True
            if query.entity_id and query.entity_id not in {vehicle_id, trip_id, entity_id, resolved}:
                continue
            candidate = {"type": "Feature", "id": identity, "geometry": shape, "properties": properties} if vehicles else {"id": identity, **properties}
            prior = items.get(identity)
            if prior is None or (ts if observed else -1) > prior[0]:
                items[identity] = (ts if observed else -1, candidate)
        values = [row[1] for row in items.values()]
        truncated = len(values) > query.limit
        partial = bool(partial or rejected or truncated or stale)
        return {"provider_id": self.id, "state": "stale" if stale else "partial" if partial else "fresh",
            "features": values[:query.limit] if vehicles else [], "records": [] if vehicles else values[:query.limit],
            "partial": partial, "truncated": truncated, "rejected_records": rejected, "has_more": False,
            "stale": stale, "feed_timestamp": header_stamp, "feed_age_seconds": now - header_ts if header_stamp else None,
            "coverage": self.coverage, "errors": [], "provenance": {"source": self.id, "citation": self.citation,
                "license": self.license,
                "crs": "EPSG:4326", "schedule": "operator-configured local lookup" if self.schedule else "not configured",
                "allowed_operations": ["display"], "live_tested": False}}
