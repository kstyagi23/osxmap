"""Offline-testable domain normalization. Linked assets are metadata, never fetched."""

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import math
import re
from urllib.parse import urlencode

from ..errors import ServiceError
from .. import web_sources as web
from .query import number, utc_time
from .transport import Request
from .quota import QuotaRule


def text(value, maximum=500):
    return value[:maximum] if isinstance(value, str) else None


def timestamp(value):
    try:
        return utc_time(value).isoformat().replace("+00:00", "Z") if value is not None else None
    except ServiceError:
        return None


def epoch(value):
    try:
        return datetime.fromtimestamp(value, timezone.utc).isoformat().replace("+00:00", "Z") if number(value, 0, 4102444800) else None
    except (ValueError, OSError):
        return None


def point(lon, lat):
    return {"type": "Point", "coordinates": [lon, lat]} if number(lon, -180, 180) and number(lat, -90, 90) else None


def inside(geometry, bbox):
    if geometry is None or bbox is None or geometry.get("type") != "Point":
        return True
    lon, lat = geometry["coordinates"]
    return bbox[0] <= lon <= bbox[2] and bbox[1] <= lat <= bbox[3]


def geometry(value):
    if value is None:
        return None
    try:
        web._geometry(value, [0])
        return value
    except ServiceError:
        return None


def feature(provider, identity, shape, properties):
    return {"type": "Feature", "id": provider + ":" + str(identity)[:100], "geometry": shape,
            "properties": {"provider_id": provider, "entity_id": str(identity)[:100], **properties}}


def rows(value, key=None):
    result = value.get(key) if key and isinstance(value, dict) else value
    if not isinstance(result, list) or len(result) > 10000 or any(not isinstance(row, dict) for row in result):
        raise ServiceError("Provider response schema is invalid or too large.", 422)
    return result


def scalar(value, minimum, maximum, scale=1, offset=0):
    return value * scale + offset if number(value, minimum, maximum) else None


def weather_query(query, provider):
    """One point and fixed products only; no upstream operators, units or auth inputs."""
    if (query.bbox is not None or query.start is not None or query.entity_id is not None or query.text is not None
            or query.pages != 1):
        raise ServiceError("Weather adapters accept one point and a fixed dataset, not viewport/time/entity/raw queries.", 400)
    if provider == "rainviewer.public":
        if query.latitude is not None or query.dataset not in {None, "radar"}:
            raise ServiceError("RainViewer supports radar metadata only.", 400)
    else:
        query.require("latitude", "longitude")
        allowed = {None, "current", "forecast"} if provider == "openweather.basic" else {None, "forecast"}
        if query.dataset not in allowed:
            raise ServiceError("Weather dataset is unsupported; billed One Call is not a basic product.", 400)


@dataclass(frozen=True)
class Adapter:
    id: str
    origin: str
    citation: str
    license: str
    coverage: str
    ttl: int = 60
    stale_age: int = 300
    hourly_limit: int = 100
    blocker: str | None = None

    @property
    def requires_credentials(self):
        return self.id == "openweather.basic"

    @property
    def quota_rules(self):
        return (QuotaRule(limit=self.hourly_limit),)

    def request(self, query, page=1, *, credentials=None):
        params, path, headers = {}, "", ()
        if self.id in {"openweather.basic", "openmeteo.weather", "openmeteo.air_quality", "rainviewer.public"}:
            weather_query(query, self.id)
            if self.id == "openweather.basic":
                key = credentials.get("api_key") if isinstance(credentials, dict) else None
                if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9]{16,128}", key):
                    raise ServiceError("OpenWeather basic requires a configured valid API key.", 409)
                path = "/data/2.5/forecast" if query.dataset == "forecast" else "/data/2.5/weather"
                params = {"lat": query.latitude, "lon": query.longitude, "appid": key, "units": "standard"}
                if query.dataset == "forecast":
                    params["cnt"] = min(40, query.limit)
            elif self.id == "openmeteo.weather":
                path, params = "/v1/forecast", {"latitude": query.latitude, "longitude": query.longitude,
                    "hourly": "temperature_2m,relative_humidity_2m,surface_pressure,wind_speed_10m,precipitation",
                    "temperature_unit": "celsius", "wind_speed_unit": "ms", "precipitation_unit": "mm",
                    "timeformat": "unixtime", "timezone": "GMT", "forecast_days": 2}
            elif self.id == "openmeteo.air_quality":
                path, params = "/v1/air-quality", {"latitude": query.latitude, "longitude": query.longitude,
                    "hourly": "pm10,pm2_5,carbon_monoxide,nitrogen_dioxide,sulphur_dioxide,ozone",
                    "timeformat": "unixtime", "timezone": "GMT", "forecast_days": 2}
            else:
                path = "/public/weather-maps.json"
        elif self.id == "adsblol.public":
            query.require("bbox")
            w, s, e, n = query.bbox
            lat, lon = (s + n) / 2, (w + e) / 2
            # One bounded circle covers the viewport; no automatic world fanout.
            radius = math.ceil(math.hypot((e - w) * 30, (n - s) * 30))
            if radius > 250:
                raise ServiceError("Aircraft viewport exceeds the 250 nautical-mile query bound.", 400)
            path = f"/v2/lat/{lat:.4f}/lon/{lon:.4f}/dist/{max(1, radius)}"
        elif self.id == "celestrak.gp":
            if query.dataset not in {"stations", "active", "weather", "gps-ops"}:
                raise ServiceError("Select an approved standard GP group.", 400)
            path, params = "/NORAD/elements/gp.php", {"GROUP": query.dataset, "FORMAT": "JSON"}
        elif self.id == "thespacedevs.ll2":
            path, params = "/2.3.0/launches/upcoming/", {"limit": query.limit, "offset": (page - 1) * query.limit}
        elif self.id == "noaa.nws":
            query.require("latitude", "longitude")
            path, params = "/alerts/active", {"point": f"{query.latitude},{query.longitude}"}
            headers = (("User-Agent", "Meridian weather alerts (local application)"), ("Accept", "application/geo+json"))
        elif self.id == "gdelt.doc2":
            query.require("text", "start", "end")
            # Restrict to literal terms rather than forwarding GDELT operators.
            if not all(c.isalnum() or c in " -" for c in query.text):
                raise ServiceError("GDELT search accepts literal words only.", 400)
            path, params = "/api/v2/doc/doc", {"query": '"' + query.text + '"', "mode": "artlist", "format": "json",
                "maxrecords": query.limit, "startdatetime": utc_time(query.start).strftime("%Y%m%d%H%M%S"),
                "enddatetime": utc_time(query.end).strftime("%Y%m%d%H%M%S")}
        elif self.id == "digitraffic.cameras":
            query.require("bbox")
            path, headers = "/api/weathercam/v1/stations", (("Digitraffic-User", "Meridian/local"),)
        elif self.id == "nasa.cmr":
            query.require("bbox", "start", "end", "dataset")
            if query.dataset not in {"HLSL30", "HLSS30"}:
                raise ServiceError("CMR discovery is restricted to HLS L30/S30 version 2.0.", 400)
            path, params = "/search/granules.umm_json", {"short_name": query.dataset, "version": "2.0",
                "bounding_box": ",".join(str(v) for v in query.bbox), "temporal": query.start + "," + query.end,
                "page_size": query.limit, "page_num": page, "sort_key": "-start_date"}
        else:
            raise ServiceError(self.blocker or "Provider adapter is unsupported.", 409)
        return Request(self.origin + path + ("?" + urlencode(params) if params else ""), self.origin, headers)

    def parse(self, value, query):
        features, records = [], []
        rejected = 0
        candidates = []
        hits = None
        if self.id == "openweather.basic":
            if not isinstance(value, dict):
                raise ServiceError("OpenWeather response schema is invalid.", 422)
            if str(value.get("cod", "200")) != "200":
                raise ServiceError("OpenWeather basic response reported failure.", 502)
            forecast = query.dataset == "forecast"
            candidates = rows(value, "list") if forecast else [value]
            if len(candidates) > 40:
                raise ServiceError("OpenWeather forecast result limit exceeded.", 422)
            location = value.get("city", {}) if forecast else value
            coord = location.get("coord", {}) if isinstance(location, dict) else {}
            shape = point(coord.get("lon"), coord.get("lat")) if isinstance(coord, dict) else None
            for row in candidates:
                valid_at = epoch(row.get("dt"))
                if valid_at is None:
                    rejected += 1
                    continue
                main = row.get("main") if isinstance(row.get("main"), dict) else {}
                wind = row.get("wind") if isinstance(row.get("wind"), dict) else {}
                rain = row.get("rain") if isinstance(row.get("rain"), dict) else {}
                duration = 10800 if forecast else 3600
                record = {"id": self.id + ":" + valid_at, "name": "OpenWeather basic " + ("forecast" if forecast else "current"),
                    "data_kind": "forecast" if forecast else "weather observation", "forecast_issued_at": None,
                    "valid_at": valid_at if forecast else None, "observed_at": None if forecast else valid_at,
                    "temperature_k": scalar(main.get("temp"), 150, 350),
                    "pressure_pa": scalar(main.get("pressure"), 100, 1200, 100),
                    "relative_humidity_fraction": scalar(main.get("humidity"), 0, 100, .01),
                    "wind_speed_m_s": scalar(wind.get("speed"), 0, 200),
                    "wind_direction_deg": scalar(wind.get("deg"), 0, 360),
                    "precipitation_m": scalar(rain.get("3h" if forecast else "1h"), 0, 2000, .001),
                    "precipitation_interval_seconds": duration, "location_kind": "upstream weather/grid point",
                    "units": {"temperature_k": "K", "pressure_pa": "Pa", "wind_speed_m_s": "m/s",
                        "relative_humidity_fraction": "1", "precipitation_m": "m"}}
                records.append(record)
                if shape:
                    features.append(feature(self.id, valid_at, shape, record))
        elif self.id in {"openmeteo.weather", "openmeteo.air_quality"}:
            if not isinstance(value, dict) or value.get("utc_offset_seconds") != 0:
                raise ServiceError("Open-Meteo requires the requested UTC schema.", 422)
            hourly, units = value.get("hourly"), value.get("hourly_units")
            if not isinstance(hourly, dict) or not isinstance(units, dict) or units.get("time") != "unixtime":
                raise ServiceError("Open-Meteo hourly schema or units are invalid.", 422)
            times = hourly.get("time")
            if not isinstance(times, list) or not 1 <= len(times) <= 48:
                raise ServiceError("Open-Meteo hourly time limit exceeded.", 422)
            if self.id == "openmeteo.weather":
                specs = {"temperature_2m": ("temperature_k", "\u00b0C", -123, 77, 1, 273.15),
                    "relative_humidity_2m": ("relative_humidity_fraction", "%", 0, 100, .01, 0),
                    "surface_pressure": ("pressure_pa", "hPa", 100, 1200, 100, 0),
                    "wind_speed_10m": ("wind_speed_m_s", "m/s", 0, 200, 1, 0),
                    "precipitation": ("precipitation_m", "mm", 0, 2000, .001, 0)}
                normalized_units = {"temperature_k": "K", "relative_humidity_fraction": "1",
                    "pressure_pa": "Pa", "wind_speed_m_s": "m/s", "precipitation_m": "m"}
            else:
                specs = {key: (key + "_kg_m3", "\u03bcg/m\u00b3", 0, 1000000, 1e-9, 0) for key in
                    ("pm10", "pm2_5", "carbon_monoxide", "nitrogen_dioxide", "sulphur_dioxide", "ozone")}
                normalized_units = {spec[0]: "kg/m^3" for spec in specs.values()}
            for key, spec in specs.items():
                series = hourly.get(key)
                if not isinstance(series, list) or len(series) != len(times) or units.get(key) != spec[1]:
                    raise ServiceError("Open-Meteo variable lengths or units do not match the fixed request.", 422)
            shape = point(value.get("longitude"), value.get("latitude"))
            previous = None
            for index, valid_time in enumerate(times):
                valid_at = epoch(valid_time)
                if valid_at is None or previous is not None and valid_time <= previous:
                    raise ServiceError("Open-Meteo valid times are invalid or unordered.", 422)
                previous = valid_time
                record = {"id": self.id + ":" + valid_at, "name": "Open-Meteo modeled " + ("weather" if self.id == "openmeteo.weather" else "air quality"),
                    "data_kind": "modeled forecast", "forecast_issued_at": None, "valid_at": valid_at,
                    "observed_at": None, "model": None, "location_kind": "upstream model grid point",
                    "units": normalized_units, "precipitation_interval_seconds": 3600 if self.id == "openmeteo.weather" else None}
                for key, (target, _, low, high, scale, offset) in specs.items():
                    record[target] = scalar(hourly[key][index], low, high, scale, offset)
                records.append(record)
                if shape:
                    features.append(feature(self.id, valid_at, shape, record))
            candidates = records
        elif self.id == "rainviewer.public":
            if not isinstance(value, dict) or not isinstance(value.get("radar"), dict):
                raise ServiceError("RainViewer radar metadata schema is invalid.", 422)
            # Do not expose/fetch dynamic hosts or tile templates, including hostile fixtures.
            generated_at = epoch(value.get("generated"))
            for category in ("past", "nowcast"):
                frames = rows(value["radar"], category)
                if len(frames) > 32:
                    raise ServiceError("RainViewer metadata frame limit exceeded.", 422)
                for row in frames:
                    valid_at = epoch(row.get("time"))
                    if valid_at is None:
                        rejected += 1
                        continue
                    records.append({"id": self.id + ":" + category + ":" + str(row["time"]),
                        "name": "RainViewer radar " + category, "data_kind": "radar composite" if category == "past" else "radar nowcast",
                        "valid_at": valid_at, "catalogue_generated_at": generated_at,
                        "forecast_issued_at": None, "observed_at": None,
                        "media_status": "metadata_only; dynamic tile origins not reviewed", "position": None})
            candidates = records
        elif self.id == "adsblol.public":
            candidates = rows(value, "ac")
            observed = value.get("now") if isinstance(value, dict) else None
            if number(observed, 10**12, 4102444800000):
                observed /= 1000
            outside = 0
            for row in candidates:
                shape = point(row.get("lon"), row.get("lat"))
                identity = row.get("hex")
                if shape is None or not isinstance(identity, str):
                    rejected += 1
                    continue
                if not inside(shape, query.bbox):
                    outside += 1
                    continue
                seen = row.get("seen_pos")
                observed_at = epoch(observed - seen) if number(observed, 0, 4102444800) and number(seen, 0, 86400) else None
                altitude = row.get("alt_baro")
                altitude = altitude * 0.3048 if number(altitude, -2000, 100000) else None
                speed = row.get("gs")
                features.append(feature(self.id, identity, shape, {"name": text(row.get("flight"), 80),
                    "observed_at": observed_at, "altitude_m": altitude, "altitude_reference": "barometric pressure altitude",
                    "speed_m_s": speed * 0.514444 if number(speed, 0, 2000) else None,
                    "heading_deg": row.get("track") if number(row.get("track"), 0, 360) else None}))
        elif self.id == "celestrak.gp":
            candidates = rows(value)
            for row in candidates:
                identity = row.get("NORAD_CAT_ID")
                orbital_epoch = row.get("EPOCH")
                if isinstance(orbital_epoch, str) and len(orbital_epoch) >= 19 and orbital_epoch[-1] != "Z" and "+" not in orbital_epoch[10:]:
                    orbital_epoch += "Z"  # Standard GP JSON epochs are UTC without a suffix.
                orbital_epoch = timestamp(orbital_epoch)
                if type(identity) is not int or not number(identity, 1, 999999999) or orbital_epoch is None:
                    rejected += 1
                    continue
                records.append({"id": self.id + ":" + str(identity), "entity_id": str(identity),
                    "name": text(row.get("OBJECT_NAME"), 100), "orbital_epoch": orbital_epoch,
                    "elements": {k: row[k] for k in ("MEAN_MOTION", "ECCENTRICITY", "INCLINATION", "RA_OF_ASC_NODE",
                        "ARG_OF_PERICENTER", "MEAN_ANOMALY", "BSTAR", "MEAN_MOTION_DOT", "MEAN_MOTION_DDOT") if number(row.get(k), -1e10, 1e10)},
                    "propagation_time": None, "position": None,
                    "propagation_status": "needs_setup", "propagation_reason": "SGP4 propagation is not installed/integrated; GP metadata only."})
        elif self.id == "thespacedevs.ll2":
            candidates = rows(value, "results")
            hits = value.get("count")
            for row in candidates:
                pad = row.get("pad") if isinstance(row.get("pad"), dict) else {}
                try:
                    lon, lat = float(pad.get("longitude")), float(pad.get("latitude"))
                except (TypeError, ValueError):
                    lon = lat = None
                shape = point(lon, lat)
                status = row.get("status") if isinstance(row.get("status"), dict) else {}
                record = {"id": self.id + ":" + str(row.get("id", ""))[:100], "name": text(row.get("name")),
                    "scheduled_at": timestamp(row.get("net")), "status": text(status.get("name")),
                    "pad_name": text(pad.get("name")), "position_kind": "launch pad, not ascent telemetry"}
                records.append(record)
                if shape:
                    features.append(feature(self.id, row.get("id", ""), shape, record))
        elif self.id == "noaa.nws":
            candidates = rows(value, "features")
            for row in candidates:
                p = row.get("properties") if isinstance(row.get("properties"), dict) else {}
                shape = geometry(row.get("geometry"))
                record = {"id": text(row.get("id")), "event": text(p.get("event")), "headline": text(p.get("headline")),
                    "severity": text(p.get("severity")), "issued_at": timestamp(p.get("sent")),
                    "valid_from": timestamp(p.get("onset")), "valid_until": timestamp(p.get("expires")),
                    "description": text(p.get("description"), 4000), "area_description": text(p.get("areaDesc"))}
                records.append(record)
                if shape:
                    features.append(feature(self.id, row.get("id", ""), shape, record))
        elif self.id == "gdelt.doc2":
            candidates = rows(value, "articles")
            for row in candidates:
                identity = hashlib.sha256(str(row.get("url", "")).encode()).hexdigest()[:24]
                records.append({"id": self.id + ":" + identity, "title": text(row.get("title")),
                    "citation_url": text(row.get("url"), 2048), "publisher_domain": text(row.get("domain"), 253),
                    "source_country": text(row.get("sourcecountry"), 100), "seen_date": text(row.get("seendate"), 32),
                    "location": None, "media_rights": "not granted by metadata access"})
        elif self.id == "digitraffic.cameras":
            candidates = rows(value, "features")
            for row in candidates:
                shape = geometry(row.get("geometry"))
                p = row.get("properties") if isinstance(row.get("properties"), dict) else {}
                if shape is None or shape.get("type") != "Point" or not inside(shape, query.bbox):
                    rejected += 1
                    continue
                presets = p.get("presets", [])
                safe_presets = []
                if isinstance(presets, list):
                    for preset in presets[:20]:
                        if isinstance(preset, dict):
                            safe_presets.append({"id": text(preset.get("id"), 100), "name": text(preset.get("name"), 100),
                                                 "direction": text(preset.get("presentationName"), 100)})
                features.append(feature(self.id, row.get("id", p.get("id", "")), shape,
                    {"name": text(p.get("name")), "updated_at": timestamp(p.get("dataUpdatedTime")),
                     "capture_time": None, "presets": safe_presets, "media_status": "catalogue_only"}))
        elif self.id == "nasa.cmr":
            candidates = rows(value, "items")
            hits = value.get("hits")
            for row in candidates:
                umm = row.get("umm") if isinstance(row.get("umm"), dict) else {}
                meta = row.get("meta") if isinstance(row.get("meta"), dict) else {}
                temporal = umm.get("TemporalExtent", {})
                interval = temporal.get("RangeDateTime", {}) if isinstance(temporal, dict) else {}
                spatial = umm.get("SpatialExtent", {})
                horizontal = spatial.get("HorizontalSpatialDomain", {}) if isinstance(spatial, dict) else {}
                source_geometry = horizontal.get("Geometry", {}) if isinstance(horizontal, dict) else {}
                polygons = []
                for polygon in source_geometry.get("GPolygons", []) if isinstance(source_geometry, dict) else []:
                    try:
                        points = polygon["Boundary"]["Points"]
                        ring = [[p["Longitude"], p["Latitude"]] for p in points]
                        if ring and ring[0] != ring[-1]:
                            ring.append(ring[0][:])
                        polygons.append([ring])
                    except (KeyError, TypeError):
                        rejected += 1
                for rectangle in source_geometry.get("BoundingRectangles", []) if isinstance(source_geometry, dict) else []:
                    try:
                        w, s, e, n = (rectangle[k] for k in ("WestBoundingCoordinate", "SouthBoundingCoordinate",
                            "EastBoundingCoordinate", "NorthBoundingCoordinate"))
                        polygons.append([[[w, s], [e, s], [e, n], [w, n], [w, s]]])
                    except (KeyError, TypeError):
                        rejected += 1
                shape = geometry({"type": "MultiPolygon", "coordinates": polygons}) if polygons else None
                if polygons and shape is None:
                    rejected += 1
                acquisition = timestamp(interval.get("BeginningDateTime"))
                if acquisition is None:
                    rejected += 1
                    continue
                identity = meta.get("concept-id", umm.get("GranuleUR", ""))
                record = {"id": self.id + ":" + str(identity)[:100], "dataset": query.dataset,
                    "name": text(umm.get("GranuleUR")), "acquired_at": acquisition,
                    "acquisition_end": timestamp(interval.get("EndingDateTime")),
                    "updated_at": timestamp(meta.get("revision-date")), "footprint": shape,
                    "rights": "HLS metadata discovery only; no linked assets downloaded"}
                records.append(record)
                if shape:
                    features.append(feature(self.id, identity, shape, record))
        else:
            raise ServiceError(self.blocker or "Provider adapter is unsupported.", 409)
        count = max(len(records), len(features))
        truncated = count > query.limit or len(candidates) >= query.limit or number(hits, 0, 10**12) and hits > count
        result = {"features": features[:query.limit], "records": records[:query.limit], "partial": bool(rejected),
                "truncated": bool(truncated), "rejected_records": rejected,
                "has_more": bool(number(hits, 0, 10**12) and hits > len(candidates))}
        if self.id == 'adsblol.public':
            result['query_diagnostics'] = {'bbox': list(query.bbox), 'provider_records': len(candidates),
                'outside_viewport': outside, 'invalid_records': rejected, 'in_viewport': len(features),
                'snapshot_at': epoch(observed)}
            result['empty_reason'] = (None if features else 'no_reports' if not candidates
                else 'outside_viewport' if outside == len(candidates) else 'no_valid_positions')
            result['truncated'] = len(features) > query.limit
        return result


ADAPTERS = {a.id: a for a in (
    Adapter("openweather.basic", "https://api.openweathermap.org", "https://openweathermap.org/current", "OpenWeather basic terms and attribution; One Call excluded", "point current weather or five-day three-hour forecast", 300, 900, 60),
    Adapter("openmeteo.weather", "https://api.open-meteo.com", "https://open-meteo.com/en/docs", "Open-Meteo attribution; free hosting non-commercial opt-in only", "point two-day hourly modeled weather", 300, 900, 60),
    Adapter("openmeteo.air_quality", "https://air-quality-api.open-meteo.com", "https://open-meteo.com/en/docs/air-quality-api", "Open-Meteo/CAMS ENSEMBLE attribution; free hosting non-commercial opt-in only", "point two-day hourly modeled air quality", 300, 900, 60),
    Adapter("rainviewer.public", "https://api.rainviewer.com", "https://www.rainviewer.com/api/weather-maps-api.html", "RainViewer attribution; personal/educational opt-in only", "radar frame metadata, no tile/media access", 300, 900, 60),
    Adapter("adsblol.public", "https://api.adsb.lol", "https://www.adsb.lol/docs/open-data/api/", "ODbL; credit adsb.lol", "receiver coverage, viewport snapshot", 12, 60, 300),
    Adapter("celestrak.gp", "https://celestrak.org", "https://celestrak.org/NORAD/documentation/gp-data-formats.php", "Standard GP/basic SSA citation; SupGP excluded", "approved orbital groups; metadata only", 7200, 14400, 2),
    Adapter("thespacedevs.ll2", "https://ll.thespacedevs.com", "https://thespacedevs.com/llapi", "TheSpaceDevs data-use terms; linked media separate", "upcoming launch metadata", 600, 3600, 15),
    Adapter("noaa.nws", "https://api.weather.gov", "https://www.weather.gov/documentation/services-web-api", "NOAA/NWS attribution", "US active alerts; not global weather", 60, 300, 100),
    Adapter("gdelt.doc2", "https://api.gdeltproject.org", "https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/", "GDELT metadata; publisher rights separate", "indexed news metadata, not observed event coordinates", 300, 1800, 60),
    Adapter("digitraffic.cameras", "https://tie.digitraffic.fi", "https://www.digitraffic.fi/en/road-traffic/", "CC BY 4.0 Fintraffic/Digitraffic", "Finland road weather camera catalogue", 300, 1800, 60),
    Adapter("nasa.cmr", "https://cmr.earthdata.nasa.gov", "https://cmr.earthdata.nasa.gov/search/site/docs/search/api.html", "NASA HLS metadata; collection rights separate", "HLS L30/S30 bounded discovery", 600, 3600, 60),
    Adapter("entur.open_data", "https://api.entur.io", "https://developer.entur.org/pages-real-time-intro", "Entur open feed; identification required", "Norway", blocker="GTFS-RT protobuf decoder and validated schedule/mode join are required; no vehicle adapter installed."),
    Adapter("translink.queensland", "https://gtfsrt.api.translink.com.au", "https://www.data.qld.gov.au/", "Queensland feed-specific open data terms", "Queensland", blocker="GTFS-RT protobuf decoder and validated Queensland schedule/mode join are required; no vehicle adapter installed."),
)}
