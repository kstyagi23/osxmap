"""Offline isolated checks: python -B -m unittest backend.test_orbits."""

import copy
from datetime import datetime, timedelta, timezone
import math
import socket
import subprocess
import sys
import unittest
from unittest.mock import patch

from backend.providers import orbits


TIME = "2000-01-01T12:00:00Z"
RECORD = {"id": "celestrak.gp:5", "entity_id": "5", "name": "VANGUARD 1",
          "orbital_epoch": TIME, "ingested_at": "2000-01-01T12:00:01Z",
          "source": {"provider_id": "celestrak.gp", "citation": "CelesTrak"},
          "elements": {"MEAN_MOTION": 10.82419157, "ECCENTRICITY": 0.1859667,
                       "INCLINATION": 34.2682, "RA_OF_ASC_NODE": 348.7242,
                       "ARG_OF_PERICENTER": 331.7664, "MEAN_ANOMALY": 19.3264,
                       "BSTAR": 0.000028098, "MEAN_MOTION_DOT": 0.00000023,
                       "MEAN_MOTION_DDOT": 0.0}}


class Satellite:
    def __init__(self, positions=None, code=0):
        self.positions = iter(positions or [(7000, 0, 0)])
        self.code = code
        self.calls = []

    def sgp4(self, jd, fraction):
        self.calls.append((jd, fraction))
        return self.code, next(self.positions), (0, 0, 0)


def teme_at(longitude, latitude, height, time):
    """Fixture ECEF inverse rotation, separate from implementation's GMST formula."""
    time = orbits._utc(time)
    days = (time - datetime(2000, 1, 1, 12, tzinfo=timezone.utc)).total_seconds() / 86400
    theta = math.radians((280.460618375 + 360.98564736629 * days) % 360)
    phi, lam = math.radians(latitude), math.radians(longitude)
    e2 = 0.0066943799901413165
    n = 6378137 / math.sqrt(1 - e2 * math.sin(phi) ** 2)
    x = (n + height) * math.cos(phi) * math.cos(lam)
    y = (n + height) * math.cos(phi) * math.sin(lam)
    z = (n * (1 - e2) + height) * math.sin(phi)
    return ((math.cos(theta) * x - math.sin(theta) * y) / 1000,
            (math.sin(theta) * x + math.cos(theta) * y) / 1000, z / 1000)


class OrbitTests(unittest.TestCase):
    def setUp(self):
        for name in ("socket", "getaddrinfo"):
            blocker = patch.object(socket, name, side_effect=AssertionError("Network forbidden"))
            blocker.start()
            self.addCleanup(blocker.stop)

    def test_import_is_inert_even_without_sgp4(self):
        code = """import builtins, socket, sqlite3, sys
from unittest.mock import patch
original = builtins.__import__
def blocked(name, *args, **kwargs):
    if name.startswith('sgp4'):
        raise AssertionError('SGP4 imported eagerly')
    return original(name, *args, **kwargs)
with patch.object(builtins, '__import__', blocked), patch.object(socket, 'socket', side_effect=AssertionError('network')), patch.object(sqlite3, 'connect', side_effect=AssertionError('database')):
    import backend.providers.orbits
assert 'backend.config' not in sys.modules
assert 'backend.server' not in sys.modules
assert 'sgp4' not in sys.modules
"""
        result = subprocess.run([sys.executable, "-B", "-c", code], capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_missing_dependency_reports_setup_without_positions(self):
        with patch.object(orbits, "available", return_value=False):
            result = orbits.propagate_omm([RECORD], [TIME])
        self.assertEqual(result["state"], "needs_setup")
        self.assertTrue(result["setup_blockers"])
        self.assertEqual(result["features"], [])
        self.assertEqual(result["records"][0]["source"], RECORD["source"])
        self.assertIsNone(result["records"][0]["position"])

    def test_available_uses_lazy_import_and_honest_missing_result(self):
        original = __import__
        def missing(name, *args, **kwargs):
            if name.startswith("sgp4"):
                raise ImportError("optional dependency absent")
            return original(name, *args, **kwargs)
        with patch("builtins.__import__", side_effect=missing):
            self.assertFalse(orbits.available())

    def test_j2000_gmst_si_height_and_provenance(self):
        before = copy.deepcopy(RECORD)
        satellite = Satellite()
        result = orbits.propagate_omm([RECORD], [TIME], lambda omm: satellite)
        feature = result["features"][0]
        lon, lat, height = feature["geometry"]["coordinates"]
        self.assertAlmostEqual(lon, 79.539381625, places=8)
        self.assertAlmostEqual(lat, 0)
        self.assertAlmostEqual(height, 621863, places=6)
        self.assertEqual(satellite.calls, [(2451544.5, 0.5)])
        self.assertEqual(feature["geometry"]["type"], "Point")
        self.assertEqual(feature["properties"]["altitude_m"], height)
        self.assertEqual(feature["properties"]["predicted_at"], TIME)
        self.assertEqual(feature["properties"]["ingested_at"], RECORD["ingested_at"])
        self.assertEqual(feature["properties"]["source"], RECORD["source"])
        self.assertEqual(feature["properties"]["altitude_reference"], "WGS84 ellipsoid")
        self.assertNotIn("observed_at", feature["properties"])
        self.assertEqual(result["provenance"]["visual_exaggeration"], 1)
        self.assertEqual(result["tracks"], [])
        self.assertEqual(RECORD, before)

    def test_wgs84_equatorial_oblique_and_polar_fixtures(self):
        for lon, lat, height in ((0, 0, 400000), (120, 45, 750000), (-70, -80, 36000000), (0, 90, 500000)):
            with self.subTest(latitude=lat):
                result = orbits.propagate_omm([RECORD], [TIME], lambda omm: Satellite([teme_at(lon, lat, height, TIME)]))
                point = result["features"][0]["geometry"]["coordinates"]
                self.assertAlmostEqual(point[0], lon, places=7)
                self.assertAlmostEqual(point[1], lat, places=7)
                self.assertAlmostEqual(point[2], height, places=4)

    def test_track_dateline_split_and_metadata(self):
        times = [TIME, "2000-01-01T12:01:00Z"]
        positions = [teme_at(179, 10, 400000, times[0]), teme_at(-179, 12, 420000, times[1])]
        result = orbits.propagate_omm([RECORD], times, lambda omm: Satellite(positions))
        track = result["tracks"][0]
        self.assertEqual(track["geometry"]["type"], "MultiLineString")
        segments = track["geometry"]["coordinates"]
        self.assertEqual(segments[0][-1][0], 180)
        self.assertEqual(segments[1][0][0], -180)
        self.assertAlmostEqual(segments[0][-1][1], 11, places=6)
        self.assertAlmostEqual(segments[0][-1][2], 410000, places=3)
        self.assertEqual(track["properties"]["predicted_at"], times)
        self.assertTrue(track["properties"]["dateline_seams_interpolated"])
        self.assertEqual(len(result["features"]), 2)
        reverse = orbits._track([[-179, 0, 1], [179, 0, 1]])
        self.assertEqual(reverse["coordinates"][0][-1][0], -180)

    def test_normal_track(self):
        self.assertEqual(orbits._track([[1, 2, 3], [2, 3, 4]])["type"], "LineString")

    def test_request_bounds_and_time_validation(self):
        invalid = [[], [TIME] * 181, [TIME, TIME], ["2000-01-01T12:00:00"], ["bad"],
                   [TIME, "2000-01-01T14:00:00.000001Z"], [TIME, "2000-01-01T11:59:00Z"]]
        for times in invalid:
            with self.subTest(times=times[:2]), self.assertRaises(ValueError):
                orbits.propagate_omm([RECORD], times, lambda omm: Satellite())
        with self.assertRaises(ValueError):
            orbits.propagate_omm([RECORD] * 101, [TIME], lambda omm: Satellite())
        times = [datetime(2000, 1, 1, 12, tzinfo=timezone.utc) + timedelta(seconds=i * 7200 / 179) for i in range(180)]
        result = orbits.propagate_omm([RECORD], times, lambda omm: Satellite([(7000, 0, 0)] * 180))
        self.assertEqual(len(result["features"]), 180)

    def test_bad_elements_and_epochs_rejected_before_factory(self):
        variants = []
        for key in RECORD["elements"]:
            row = copy.deepcopy(RECORD)
            del row["elements"][key]
            variants.append(row)
        for key, value in (("MEAN_MOTION", 0), ("MEAN_MOTION", float("nan")), ("BSTAR", True),
                           ("ECCENTRICITY", 1), ("INCLINATION", 181), ("MEAN_ANOMALY", -1),
                           ("RA_OF_ASC_NODE", 360), ("MEAN_MOTION_DOT", 2)):
            row = copy.deepcopy(RECORD)
            row["elements"][key] = value
            variants.append(row)
        for key, value in (("orbital_epoch", "bad"), ("orbital_epoch", "1999-12-17T11:59:59Z"),
                           ("orbital_epoch", "2000-01-01T12:00:01Z"), ("entity_id", True)):
            variants.append({**RECORD, key: value})
        for record in variants:
            with self.subTest(record=record):
                factory = unittest.mock.Mock(side_effect=AssertionError("Must not initialize"))
                result = orbits.propagate_omm([record], [TIME], factory)
                factory.assert_not_called()
                self.assertEqual(result["state"], "error")
                self.assertEqual(result["records"][0]["propagation_status"], "unknown")
                self.assertEqual(result["features"], [])

    def test_per_satellite_errors_atomic_no_failed_track_or_altitude(self):
        times = [TIME, "2000-01-01T12:01:00Z"]
        bad = {**RECORD, "entity_id": "6", "id": "celestrak.gp:6"}
        def factory(omm):
            return Satellite([(7000, 0, 0), (float("inf"), 0, 0)] if omm["NORAD_CAT_ID"] == 6 else [(7000, 0, 0)] * 2)
        result = orbits.propagate_omm([bad, RECORD], times, factory)
        self.assertEqual(result["state"], "partial")
        self.assertEqual(len(result["features"]), 2)
        self.assertEqual(len(result["tracks"]), 1)
        self.assertEqual(len(result["errors"]), 1)
        self.assertEqual(result["errors"][0]["entity_id"], "6")
        self.assertIsNone(result["records"][0]["position"])
        for satellite in (Satellite(code=6), Satellite([(0, 0, 0)]), Satellite([(6300, 0, 0)])):
            result = orbits.propagate_omm([RECORD], [TIME], lambda omm: satellite)
            self.assertEqual(result["features"], [])
            self.assertEqual(len(result["errors"]), 1)

    def test_library_exception_is_bounded_not_leaked(self):
        def broken(omm):
            raise RuntimeError("secret payload")
        result = orbits.propagate_omm([RECORD], [TIME], broken)
        self.assertNotIn("secret payload", str(result))

    @unittest.skipUnless(orbits.available(), "Optional sgp4 library not installed; real numerical validation skipped")
    def test_known_vallado_vanguard_sgp4_example(self):
        # Published SGP4 verification case 00005 at its element epoch, WGS72.
        record = {**RECORD, "orbital_epoch": "2000-06-27T18:50:19.733568Z",
                  "elements": {**RECORD["elements"], "RA_OF_ASC_NODE": 331.5174,
                               "ECCENTRICITY": 0.1849677}}
        time = orbits._utc(record["orbital_epoch"])
        satellite = orbits._satellite(orbits._elements(record, [time]))
        error, position, velocity = satellite.sgp4(*orbits._julian(time))
        self.assertEqual(error, 0)
        for actual, expected in zip(position, (7022.46529266, -1400.08296755, 0.03995155)):
            self.assertAlmostEqual(actual, expected, places=5)
        for actual, expected in zip(velocity, (1.893841015, 6.405893759, 4.534807250)):
            self.assertAlmostEqual(actual, expected, places=6)
        result = orbits.propagate_omm([record], [time])
        self.assertEqual(result["state"], "ready")
        self.assertGreater(result["features"][0]["geometry"]["coordinates"][2], 600000)


if __name__ == "__main__":
    unittest.main()
