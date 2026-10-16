"""Optional offline SGP4 predictions; importing this module does not load sgp4.

propagate_omm accepts normalized CelesTrak adapter records and explicit UTC times
(ISO strings or aware datetimes). satellite_factory(omm) may inject an object
with sgp4(jd, fraction) -> (error, TEME position km, velocity km/s).
No current clock, network, dependency installation, or observed position is used.
"""

from datetime import datetime, timezone
import math


MAX_SATELLITES = 100
MAX_SAMPLES = 180
MAX_WINDOW_SECONDS = 7200
MAX_ELEMENT_AGE_SECONDS = 14 * 86400
_FIELDS = ("MEAN_MOTION", "ECCENTRICITY", "INCLINATION", "RA_OF_ASC_NODE",
           "ARG_OF_PERICENTER", "MEAN_ANOMALY", "BSTAR", "MEAN_MOTION_DOT", "MEAN_MOTION_DDOT")
_A = 6378137.0
_E2 = (1 / 298.257223563) * (2 - 1 / 298.257223563)


def available():
    """Return whether the optional SGP4 API can be imported, without installing it."""
    try:
        from sgp4.api import Satrec, WGS72
    except ImportError:
        return False
    return callable(getattr(Satrec, "sgp4", None)) and WGS72 is not None


def _utc(value, omm=False):
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not isinstance(value, datetime):
        raise ValueError("Timestamp must be an ISO datetime or aware datetime.")
    if value.tzinfo is None or value.utcoffset() is None:
        if not omm:
            raise ValueError("Prediction times must specify a UTC offset.")
        value = value.replace(tzinfo=timezone.utc)  # CelesTrak OMM epochs are UTC.
    return value.astimezone(timezone.utc)


def _iso(value):
    return value.isoformat().replace("+00:00", "Z")


def _julian(value):
    midnight = value.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight.toordinal() + 1721424.5, (value - midnight).total_seconds() / 86400


def _satellite(omm):
    from sgp4.api import Satrec, WGS72
    epoch = _utc(omm["EPOCH"], omm=True)
    jd, fraction = _julian(epoch)
    xpdotp = 1440 / (2 * math.pi)
    satellite = Satrec()
    satellite.sgp4init(WGS72, "i", int(omm["NORAD_CAT_ID"]), jd - 2433281.5 + fraction,
                       omm["BSTAR"], omm["MEAN_MOTION_DOT"] / (xpdotp * 1440),
                       omm["MEAN_MOTION_DDOT"] / (xpdotp * 1440 * 1440),
                       omm["ECCENTRICITY"], math.radians(omm["ARG_OF_PERICENTER"]),
                       math.radians(omm["INCLINATION"]), math.radians(omm["MEAN_ANOMALY"]),
                       omm["MEAN_MOTION"] / xpdotp, math.radians(omm["RA_OF_ASC_NODE"]))
    return satellite


def _coordinates(position, jd, fraction):
    if not isinstance(position, (list, tuple)) or len(position) != 3:
        raise ValueError("Invalid TEME position.")
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in position):
        raise ValueError("Nonfinite TEME position.")
    # Vallado GMST rotation, UTC approximates UT1; no polar-motion correction.
    t = ((jd - 2451545.0) + fraction) / 36525
    gmst = math.radians((67310.54841 + (876600 * 3600 + 8640184.812866) * t
                         + 0.093104 * t * t - 6.2e-6 * t * t * t) / 240 % 360)
    c, s = math.cos(gmst), math.sin(gmst)
    x = (c * position[0] + s * position[1]) * 1000
    y = (-s * position[0] + c * position[1]) * 1000
    z = position[2] * 1000
    p = math.hypot(x, y)
    if math.hypot(p, z) < _A * 0.5:
        raise ValueError("Position is not a valid orbital location.")
    lon = math.atan2(y, x)
    lat = math.atan2(z, p * (1 - _E2))
    for _ in range(15):
        n = _A / math.sqrt(1 - _E2 * math.sin(lat) ** 2)
        next_lat = math.atan2(z + _E2 * n * math.sin(lat), p)
        if abs(next_lat - lat) < 1e-13:
            lat = next_lat
            break
        lat = next_lat
    n = _A / math.sqrt(1 - _E2 * math.sin(lat) ** 2)
    height = p * math.cos(lat) + z * math.sin(lat) - n * (1 - _E2 * math.sin(lat) ** 2)
    if not all(math.isfinite(v) for v in (lon, lat, height)) or height < 0:
        raise ValueError("Predicted ellipsoid height is invalid or below the surface.")
    return [math.degrees(lon), math.degrees(lat), height]


def _track(points):
    segments = [[points[0]]]
    for previous, current in zip(points, points[1:]):
        if abs(current[0] - previous[0]) > 180:
            adjusted = current[0] + (360 if current[0] < previous[0] else -360)
            edge = 180 if adjusted > previous[0] else -180
            ratio = (edge - previous[0]) / (adjusted - previous[0])
            seam = [edge, previous[1] + ratio * (current[1] - previous[1]),
                    previous[2] + ratio * (current[2] - previous[2])]
            segments[-1].append(seam)
            segments.append([[-edge, seam[1], seam[2]], current])
        else:
            segments[-1].append(current)
    return ({"type": "LineString", "coordinates": segments[0]} if len(segments) == 1
            else {"type": "MultiLineString", "coordinates": segments})


def _elements(record, times):
    identity = record.get("entity_id")
    if isinstance(identity, bool) or not isinstance(identity, (str, int)) or not str(identity).isascii() or not str(identity).isdigit():
        raise ValueError("Missing or invalid NORAD entity_id.")
    if not 1 <= int(identity) <= 999999999:
        raise ValueError("NORAD entity_id is out of range.")
    elements = record.get("elements")
    if not isinstance(elements, dict):
        raise ValueError("Missing OMM elements.")
    omm = {}
    for key in _FIELDS:
        value = elements.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError("Missing or invalid OMM field: " + key)
        omm[key] = value
    if not 0 < omm["MEAN_MOTION"] <= 20 or not 0 <= omm["ECCENTRICITY"] < 1:
        raise ValueError("Invalid mean motion or eccentricity.")
    for key in ("INCLINATION", "RA_OF_ASC_NODE", "ARG_OF_PERICENTER", "MEAN_ANOMALY"):
        maximum = 180 if key == "INCLINATION" else 360
        if not 0 <= omm[key] < maximum and not (key == "INCLINATION" and omm[key] == 180):
            raise ValueError("Invalid OMM angle: " + key)
    if any(abs(omm[key]) > 1 for key in ("BSTAR", "MEAN_MOTION_DOT", "MEAN_MOTION_DDOT")):
        raise ValueError("OMM drag or derivative is out of supported range.")
    epoch = _utc(record.get("orbital_epoch"), omm=True)
    if times[0] < epoch or (times[-1] - epoch).total_seconds() > MAX_ELEMENT_AGE_SECONDS:
        raise ValueError("Element epoch is future or older than the 14-day maximum at prediction time.")
    omm.update(EPOCH=_iso(epoch), NORAD_CAT_ID=int(identity))
    return omm


def propagate_omm(records, times, satellite_factory=None):
    """Return {features, tracks, records, errors, provenance, state, setup_blockers}.

    Inputs: <=100 normalized records, 1..180 strictly increasing UTC timestamps
    spanning <=2 hours. Invalid request bounds raise ValueError. Satellite errors
    are atomic and isolated: no invented/partial position or track is returned.
    Source records remain intact in records, with prediction fields added to copies.
    """
    if not isinstance(records, (list, tuple)) or len(records) > MAX_SATELLITES:
        raise ValueError("Expected at most 100 satellite records.")
    if not isinstance(times, (list, tuple)) or not 1 <= len(times) <= MAX_SAMPLES:
        raise ValueError("Expected 1..180 fixed prediction times.")
    times = [_utc(value) for value in times]
    if any(b <= a for a, b in zip(times, times[1:])) or (times[-1] - times[0]).total_seconds() > MAX_WINDOW_SECONDS:
        raise ValueError("Prediction times must increase within a two-hour window.")
    result = {"features": [], "tracks": [], "records": [], "errors": [], "setup_blockers": [],
              "state": "ready", "provenance": {
                  "provider_id": "celestrak.gp", "method": "SGP4", "position_status": "predicted",
                  "input_frame": "TEME", "earth_fixed_frame": "ECEF (GMST approximation)",
                  "datum": "WGS84 ellipsoid", "altitude_reference": "WGS84 ellipsoid",
                  "altitude_units": "m", "visual_exaggeration": 1,
                  "accuracy_note": "Modeled, not observed; UTC approximates UT1, polar motion omitted; no sea-level datum.",
                  "max_element_age_seconds": MAX_ELEMENT_AGE_SECONDS,
                  "predicted_at": [_iso(t) for t in times]}}
    if satellite_factory is None:
        if not available():
            result["state"] = "needs_setup"
            result["setup_blockers"] = ["Optional sgp4 library is not installed; no propagation performed."]
            for record in records:
                result["records"].append({**(record if isinstance(record, dict) else {}),
                                          "position": None, "propagation_status": "needs_setup",
                                          "propagation_reason": result["setup_blockers"][0]})
            return result
        satellite_factory = _satellite
    for index, record in enumerate(records):
        output = dict(record) if isinstance(record, dict) else {}
        identity = str(output.get("entity_id", index))[:100]
        try:
            if not isinstance(record, dict):
                raise ValueError("Satellite record must be an object.")
            omm = _elements(record, times)
            satellite = satellite_factory(omm)
            points = []
            for time in times:
                jd, fraction = _julian(time)
                code, position, _velocity = satellite.sgp4(jd, fraction)
                if type(code) is not int or code != 0:
                    raise ValueError("SGP4 returned error code " + str(code)[:30])
                points.append(_coordinates(position, jd, fraction))
            properties = {"provider_id": "celestrak.gp", "entity_id": identity, "name": record.get("name"),
                          "source": record.get("source"), "ingested_at": record.get("ingested_at"),
                          "orbital_epoch": omm["EPOCH"], "element_epoch": omm["EPOCH"],
                          "position_status": "predicted", "propagation_method": "SGP4",
                          "altitude_reference": "WGS84 ellipsoid", "altitude_units": "m"}
            prefix = str(record.get("id", "celestrak.gp:" + identity))[:200]
            for time, point in zip(times, points):
                result["features"].append({"type": "Feature", "id": prefix + ":" + _iso(time),
                    "geometry": {"type": "Point", "coordinates": point},
                    "properties": {**properties, "predicted_at": _iso(time), "altitude_m": point[2]}})
            if len(points) > 1:
                geometry = _track(points)
                result["tracks"].append({"type": "Feature", "id": prefix + ":track", "geometry": geometry,
                    "properties": {**properties, "predicted_at": [_iso(t) for t in times],
                                   "dateline_seams_interpolated": geometry["type"] == "MultiLineString"}})
            output.update(position=None, propagation_status="predicted", propagation_reason=None,
                          element_epoch=omm["EPOCH"], predicted_at=[_iso(t) for t in times])
        except Exception as error:
            # Untrusted factory/library exception text may contain arbitrary data.
            reason = str(error)[:240] if isinstance(error, ValueError) else "Satellite propagation failed (" + type(error).__name__ + ")."
            output.update(position=None, propagation_status="unknown", propagation_reason=reason)
            result["errors"].append({"entity_id": identity, "record_index": index, "reason": reason})
        result["records"].append(output)
    if result["errors"]:
        result["state"] = "partial" if result["features"] else "error"
    return result
