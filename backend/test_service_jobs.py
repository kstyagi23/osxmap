import hashlib
import importlib
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from . import service_jobs
from .service_jobs import JobError, LocalJobManager, dependency_inventory, validate_manifest


class LocalJobTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.content = {"type": "FeatureCollection", "features": [
            {"type": "Feature", "properties": {"name": "fixture"},
             "geometry": {"type": "Point", "coordinates": [1, 1]}},
            {"type": "Feature", "properties": {},
             "geometry": {"type": "Point", "coordinates": [30, 30]}},
        ]}
        self.sources = {}
        self.managers = []
        self.addCleanup(self.cleanup_managers)
        self.configure()

    def cleanup_managers(self):
        for manager in self.managers:
            manager.close()

    def configure(self, service_id="osm.extracts", raw=None, manifest_changes=None):
        raw = json.dumps(self.content).encode() if raw is None else raw
        (self.root / "data.bin").write_bytes(raw)
        operation = service_jobs.SUPPORTED_WORKFLOWS[service_id]
        license_id = next(iter(service_jobs._LICENSES[service_id]))
        manifest = {
            "version": 1, "service_id": service_id, "provenance": "Official source fixture, regional extract",
            "license": license_id, "proof": "operator-reviewed fixture record #123",
            "reviewed_on": "2026-10-01", "allowed_operations": [operation, "display"],
            "attribution": "Fixture attribution", "sha256": hashlib.sha256(raw).hexdigest(),
            "size_bytes": len(raw), "units": "degrees" if operation == "import_geojson" else "metres",
            "axes": "x-east,y-north,z-up", "pivot": [0, 0, 0], "bounding_size": [1, 1, 1],
            "lod": [{"level": 0, "max_distance": 1000, "triangles": 0}],
        }
        manifest.update(manifest_changes or {})
        encoded = json.dumps(manifest).encode()
        (self.root / "manifest.json").write_bytes(encoded)
        source = {key: manifest[key] for key in service_jobs._PROOF_FIELDS}
        source.update(path="data.bin", manifest_path="manifest.json", manifest_sha256=hashlib.sha256(encoded).hexdigest())
        self.sources["reviewed-fixture"] = source
        self.manifest = manifest

    def manager(self, **kwargs):
        values = {"sources": self.sources, "policy_gate": lambda _: {"effective_enabled": True}}
        values.update(kwargs)
        manager = LocalJobManager(self.root, **values)
        self.managers.append(manager)
        return manager

    @staticmethod
    def request(operation="import_geojson"):
        request = {"operation": operation, "source_id": "reviewed-fixture"}
        if operation == "import_geojson":
            request["bbox"] = [0, 0, 2, 2]
        return request

    def finish(self, manager, request=None, service_id="osm.extracts"):
        job = manager.submit(service_id, self.request() if request is None else request)
        manager._jobs[job["id"]]["future"].result(timeout=5)
        result = manager.status(job["id"], service_id)
        self.assertFalse(list(self.root.glob(".service-job-*")))
        return result

    def test_reviewed_regional_imports_and_detached_status(self):
        for service_id in ("osm.extracts", "overture.base", "openbuildingmap.downloads", "naturalearth.downloads"):
            with self.subTest(service_id=service_id):
                self.configure(service_id)
                manager = self.manager()
                result = self.finish(manager, service_id=service_id)
                self.assertEqual(result["state"], "completed")
                self.assertEqual(len(result["result"]["data"]["features"]), 1)
                self.assertEqual(result["result"]["excluded_features"], 1)
                self.assertTrue(result["result"]["partial"])
                self.assertFalse(result["result"]["workspace_mutated"])
                result["result"]["provenance"]["license"] = "forged"
                self.assertEqual(manager.status(result["id"])["result"]["provenance"]["license"], self.manifest["license"])
                with self.assertRaises(JobError):
                    manager.status(result["id"], "polyhaven.assets")

    def test_asset_content_not_claimed_renderable_or_legal_approval(self):
        self.configure("polyhaven.assets", raw=b"fixture model bytes")
        result = self.finish(self.manager(), self.request("validate_asset"), "polyhaven.assets")
        self.assertEqual(result["state"], "completed")
        self.assertTrue(result["result"]["content_verified"])
        self.assertFalse(result["result"]["renderable_verified"])
        self.assertNotIn("legal_approval", result["result"])

    def test_permission_and_setup_fail_closed(self):
        manager = self.manager()
        for product, expected in (("openbuildingmap.hosted", "permission_blocked"),
                                  ("sketchfab.assets", "permission_blocked"),
                                  ("noaa.gfs", "needs_setup"), ("unknown", "permission_blocked")):
            with self.subTest(product=product), self.assertRaises(JobError) as raised:
                manager.submit(product, self.request())
            self.assertEqual(raised.exception.state, expected)
        for kwargs in ({"policy_gate": None}, {"sources": {}},
                       {"policy_gate": lambda _: {"effective_enabled": False, "state": "disabled"}}):
            with self.subTest(kwargs=kwargs), self.assertRaises(JobError):
                self.manager(**kwargs).submit("osm.extracts", self.request())
        unset = LocalJobManager(policy_gate=lambda _: {"effective_enabled": True})
        self.addCleanup(unset.close)
        with self.assertRaises(JobError) as raised:
            unset.submit("osm.extracts", self.request())
        self.assertEqual(raised.exception.state, "needs_setup")

    def test_no_request_paths_commands_permissions_or_whole_world(self):
        manager = self.manager()
        for extra in ("path", "url", "command", "args", "permission", "manifest", "allowed_operations"):
            with self.subTest(extra=extra), self.assertRaises(JobError):
                manager.submit("osm.extracts", {**self.request(), extra: "forged"})
        for bbox in ([-180, -90, 180, 90], [170, 0, -170, 1], [0, 0, 11, 1],
                     [True, 0, 2, 2], [0, 0, float("nan"), 1], [0, 0, 0, 1]):
            with self.subTest(bbox=bbox), self.assertRaises(JobError):
                manager.submit("osm.extracts", {**self.request(), "bbox": bbox})
        with self.assertRaises(JobError):
            manager.submit("osm.extracts", {**self.request(), "source_id": "../data"})

    def test_source_paths_reject_traversal_and_absolute(self):
        for path in ("../outside", "a/../data.bin", str(self.root / "data.bin"),
                     "C:/data.bin", "a\\data.bin", "a//data.bin", "./data.bin", "file:stream"):
            with self.subTest(path=path):
                sources = {"reviewed-fixture": {**self.sources["reviewed-fixture"], "path": path}}
                with self.assertRaises(JobError):
                    self.manager(sources=sources).submit("osm.extracts", self.request())

    def test_symlink_and_reparse_rejected(self):
        target = self.root / "real.bin"
        (self.root / "data.bin").rename(target)
        try:
            (self.root / "data.bin").symlink_to(target)
        except OSError:
            # Windows may lack symlink privilege; exercise its junction/reparse rejection.
            info = target.stat()
            class ReparseInfo:
                st_mode = info.st_mode
                st_file_attributes = 0x400
            with patch.object(Path, "lstat", return_value=ReparseInfo()), self.assertRaises(JobError):
                service_jobs._checked_path(self.root, "real.bin")
            return
        result = self.finish(self.manager())
        self.assertEqual(result["error"]["state"], "invalid_source")

    def test_content_and_manifest_hashes(self):
        manager = self.manager()
        (self.root / "data.bin").write_bytes(b"tampered")
        result = self.finish(manager)
        self.assertEqual(result["error"]["state"], "invalid_source")
        self.configure()
        manager = self.manager()
        (self.root / "manifest.json").write_bytes(b"{}")
        result = self.finish(manager)
        self.assertEqual(result["error"]["state"], "permission_blocked")

    def test_exact_manifest_fields_proof_and_metadata(self):
        for changes in ({"proof": "forged"}, {"license": "MIT"}, {"extra": "field"},
                        {"units": "unknown"}, {"axes": "unknown"}, {"pivot": [0, float("nan"), 0]},
                        {"bounding_size": [1, 0, 1]}, {"lod": []}, {"reviewed_on": "2999-01-01"},
                        {"sha256": "x"}, {"size_bytes": True}, {"version": True}):
            with self.subTest(changes=changes), self.assertRaises(JobError):
                validate_manifest({**self.manifest, **changes}, self.sources["reviewed-fixture"], "osm.extracts", 8000)
        self.configure(manifest_changes={"allowed_operations": ["display"]})
        result = self.finish(self.manager())
        self.assertEqual(result["error"]["state"], "permission_blocked")

    def test_malformed_geojson_and_json_rejected(self):
        for raw in (b'{"type":"FeatureCollection","features":[],"crs":{}}',
                    b'{"type":"FeatureCollection","type":"FeatureCollection","features":[]}',
                    b'{"type":"FeatureCollection","features":[NaN]}', b'not json',
                    json.dumps({"type": "FeatureCollection", "features": [
                        {"type": "Feature", "properties": {}, "geometry": {"type": "Point", "coordinates": [181, 0]}}
                    ]}).encode()):
            with self.subTest(raw=raw):
                self.configure(raw=raw)
                result = self.finish(self.manager())
                self.assertEqual(result["state"], "failed")
                self.assertEqual(result["error"]["state"], "invalid_source")

    def test_byte_feature_coordinate_and_output_bounds(self):
        result = self.finish(self.manager(max_bytes=10))
        self.assertEqual(result["state"], "failed")
        self.configure()
        result = self.finish(self.manager(max_output_bytes=10))
        self.assertEqual(result["error"]["state"], "size_exceeded")
        self.content["features"][1]["geometry"]["coordinates"] = [1, 1]
        self.configure()
        result = self.finish(self.manager(max_features=1))
        self.assertEqual(result["error"]["state"], "size_exceeded")
        with self.assertRaises(JobError):
            service_jobs._geometry_bounds({"type": "LineString", "coordinates": [[1, 1], [1, 1]]}, threading.Event(), [1])

    def test_concurrency_queue_cancel_and_cleanup(self):
        started, release = threading.Event(), threading.Event()
        read = service_jobs._read_bounded

        def blocking(*args):
            started.set()
            if not release.wait(5):
                raise RuntimeError("fixture timeout")
            return read(*args)

        manager = self.manager(max_workers=1, max_pending=1)
        with patch.object(service_jobs, "_read_bounded", side_effect=blocking):
            first = manager.submit("osm.extracts", self.request())
            self.assertTrue(started.wait(5))
            second = manager.submit("osm.extracts", self.request())
            self.assertEqual(second["state"], "queued")
            with self.assertRaises(JobError) as raised:
                manager.submit("osm.extracts", self.request())
            self.assertEqual(raised.exception.state, "queue_full")
            manager.cancel(second["id"])
            manager.cancel(first["id"])
            with self.assertRaises(JobError):
                manager.submit("osm.extracts", self.request())
            release.set()
            manager._jobs[first["id"]]["future"].result(timeout=5)
            manager._jobs[second["id"]]["future"].result(timeout=5)
        self.assertEqual(manager.status(first["id"])["state"], "cancelled")
        self.assertEqual(manager.status(second["id"])["state"], "cancelled")
        self.assertFalse(list(self.root.glob(".service-job-*")))

    def test_cancel_service_purges_results_and_rechecks_policy(self):
        manager = self.manager()
        job = self.finish(manager)
        manager.cancel_service("osm.extracts")
        self.assertEqual(manager.status(job["id"])["state"], "cancelled")
        self.assertIsNone(manager.status(job["id"])["result"])
        calls = []

        def gate(_):
            calls.append(1)
            return {"effective_enabled": len(calls) < 3, "state": "disabled"}

        result = self.finish(self.manager(policy_gate=gate))
        self.assertEqual(result["state"], "failed")
        self.assertEqual(result["error"]["state"], "disabled")
        self.assertIsNone(result["result"])

    def test_history_bounds_closed_manager_and_safe_error(self):
        manager = self.manager(max_workers=1, max_pending=0, max_jobs=1)
        old = self.finish(manager)
        self.finish(manager)
        with self.assertRaises(JobError):
            manager.status(old["id"])
        (self.root / "data.bin").unlink()
        result = self.finish(manager)
        self.assertEqual(result["state"], "failed")
        self.assertNotIn(str(self.root), json.dumps(result))
        manager.close()
        with self.assertRaises(JobError):
            manager.submit("osm.extracts", self.request())

    def test_no_import_side_effects_and_dependency_report(self):
        with patch("socket.socket", side_effect=AssertionError("network forbidden")), \
                patch("builtins.open", side_effect=AssertionError("file read forbidden")):
            spec = importlib.util.spec_from_file_location("backend._isolated_service_jobs", service_jobs.__file__)
            isolated = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(isolated)
        with patch.object(service_jobs.importlib.util, "find_spec", return_value=None):
            report = dependency_inventory()
        self.assertEqual(set(report), {"grib", "sgp4", "raster", "duckdb", "engines"})
        self.assertTrue(all(item["state"] == "needs_setup" and item["usable"] is False for item in report.values()))


if __name__ == "__main__":
    unittest.main()
