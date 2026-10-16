"""Explicit, bounded local-file workflows. No downloads, engines or server imports.

Source configuration is operator-owned, never a request or a permission override.
Matching recorded proof is not entitlement validation or legal approval. Completed
imports return a small in-memory selection; they do not mutate the map workspace.
The configured root must not be writable by untrusted concurrent processes;
portable path checks cannot sandbox a hostile same-user filesystem writer.
"""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path, PureWindowsPath
import re
import stat
import tempfile
import threading
from datetime import date
from uuid import uuid4

from .service_registry import get_product


SUPPORTED_WORKFLOWS = {
    "osm.extracts": "import_geojson",
    "overture.base": "import_geojson",
    "openbuildingmap.downloads": "import_geojson",
    "naturalearth.downloads": "import_geojson",
    "polyhaven.assets": "validate_asset",
}
_LICENSES = {
    "osm.extracts": {"ODbL-1.0"},
    "overture.base": {"ODbL-1.0"},
    "openbuildingmap.downloads": {"ODbL-1.0"},
    "naturalearth.downloads": {"Public-Domain"},
    "polyhaven.assets": {"CC0-1.0"},
}
_TERMINAL = {"completed", "failed", "cancelled"}
_PROOF_FIELDS = ("service_id", "provenance", "license", "proof", "reviewed_on", "allowed_operations")
_MANIFEST_FIELDS = set(_PROOF_FIELDS) | {
    "version", "attribution", "sha256", "size_bytes", "units", "axes", "pivot", "lod", "bounding_size",
}


class JobError(ValueError):
    def __init__(self, state, message):
        super().__init__(message)
        self.state = state


class _Cancelled(Exception):
    pass


def dependency_inventory():
    """Inspect module specs only; presence does not prove a working pinned codec."""
    modules = {"grib": ("eccodes", "cfgrib"), "sgp4": ("sgp4",),
               "raster": ("rasterio",), "duckdb": ("duckdb",)}
    report = {}
    for name, candidates in modules.items():
        present = []
        for module in candidates:
            try:
                if importlib.util.find_spec(module) is not None:
                    present.append(module)
            except (ImportError, ValueError, AttributeError):
                pass
        report[name] = {"state": "needs_setup", "present_modules": present,
                        "usable": False, "reason": "Pinned codec/runtime configuration not verified."}
    report["engines"] = {"state": "needs_setup", "usable": False,
                         "reason": "Local routing/processing engines are not configured or invoked."}
    return report


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def _vector(value, positive=False):
    return (isinstance(value, list) and len(value) == 3
            and all(_finite(v) and (not positive or v > 0) for v in value))


def _sha(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _relative(value):
    if not isinstance(value, str) or not value or "\\" in value or ":" in value or "\x00" in value:
        raise JobError("invalid_request", "Only configured relative local file names are supported.")
    path = Path(value)
    if path.is_absolute() or PureWindowsPath(value).is_absolute() or any(p in ("", ".", "..") for p in value.split("/")):
        raise JobError("invalid_request", "Traversal and absolute paths are not supported.")
    return path


def _checked_path(root, relative):
    # Reject junctions/reparse points as well as symlinks, including root ancestors.
    path = root / _relative(relative)
    for part in [*reversed(path.parents), path]:
        info = part.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise JobError("invalid_source", "Symlinks and reparse points are not supported.")
    if not path.resolve().is_relative_to(root.resolve()):
        raise JobError("invalid_source", "Source must remain inside the configured root.")
    return path


def _read_bounded(root, relative, limit, cancel):
    path = _checked_path(root, relative)
    before = path.stat()
    if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
        raise JobError("size_exceeded", "Configured source is not a bounded regular file.")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    with os.fdopen(descriptor, "rb") as stream:
        opened = os.fstat(stream.fileno())
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise JobError("invalid_source", "Source changed during access.")
        _checked_path(root, relative)
        chunks, length = [], 0
        while True:
            if cancel.is_set():
                raise _Cancelled()
            chunk = stream.read(min(65536, limit + 1 - length))
            if not chunk:
                break
            length += len(chunk)
            if length > limit:
                raise JobError("size_exceeded", "Source exceeds the configured byte limit.")
            chunks.append(chunk)
        after = os.fstat(stream.fileno())
        if (opened.st_size, opened.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise JobError("invalid_source", "Source changed during access.")
        _checked_path(root, relative)
    return b"".join(chunks)


def _json(data):
    def constant(_):
        raise ValueError("Non-finite JSON")

    def object_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result

    try:
        return json.loads(data, parse_constant=constant, object_pairs_hook=object_pairs)
    except (ValueError, UnicodeError, RecursionError):
        raise JobError("invalid_source", "Source is not supported strict JSON.") from None


def validate_manifest(manifest, source, service_id, max_bytes):
    """Validate an already hash-pinned manifest against trusted recorded proof."""
    if not isinstance(manifest, dict) or set(manifest) != _MANIFEST_FIELDS or type(manifest["version"]) is not int or manifest["version"] != 1:
        raise JobError("invalid_manifest", "Manifest fields/version must match the supported schema.")
    for field in _PROOF_FIELDS:
        if manifest[field] != source.get(field):
            raise JobError("permission_blocked", "Manifest differs from operator-reviewed source proof.")
    if manifest["service_id"] != service_id or manifest["license"] not in _LICENSES[service_id]:
        raise JobError("permission_blocked", "Exact source licence is not supported for this workflow.")
    for field in ("provenance", "proof", "attribution"):
        if not isinstance(manifest[field], str) or not 1 <= len(manifest[field]) <= 4096:
            raise JobError("invalid_manifest", "Manifest requires bounded provenance, proof and attribution.")
    try:
        reviewed = date.fromisoformat(manifest["reviewed_on"])
        if reviewed > date.today():
            raise ValueError()
    except (TypeError, ValueError):
        raise JobError("invalid_manifest", "Manifest requires a recorded past review date.") from None
    operations = manifest["allowed_operations"]
    if (not isinstance(operations, list) or not operations or any(not isinstance(op, str) for op in operations)
            or len(operations) != len(set(operations))
            or any(op not in ("import_geojson", "validate_asset", "display", "export", "distribute") for op in operations)):
        raise JobError("invalid_manifest", "Manifest requires explicit supported allowed operations.")
    if (not _sha(manifest["sha256"]) or type(manifest["size_bytes"]) is not int
            or not 0 < manifest["size_bytes"] <= max_bytes):
        raise JobError("invalid_manifest", "Manifest requires a bounded exact content hash and size.")
    if manifest["units"] not in ("metres", "degrees") or manifest["axes"] not in ("x-east,y-north,z-up", "x-right,y-up,z-forward"):
        raise JobError("invalid_manifest", "Units and axes must be explicit supported conventions.")
    if (not _vector(manifest["pivot"]) or not _vector(manifest["bounding_size"], positive=True)
            or any(abs(v) > 1e7 for v in manifest["pivot"] + manifest["bounding_size"])):
        raise JobError("invalid_manifest", "Pivot and bounding size require finite three-axis values.")
    lod = manifest["lod"]
    if (not isinstance(lod, list) or not 1 <= len(lod) <= 8
            or any(not isinstance(item, dict) or set(item) != {"level", "max_distance", "triangles"}
                   or type(item["level"]) is not int or item["level"] != index
                   or not _finite(item["max_distance"]) or not 0 < item["max_distance"] <= 1e7
                   or type(item["triangles"]) is not int or not 0 <= item["triangles"] <= 1000000
                   for index, item in enumerate(lod))):
        raise JobError("invalid_manifest", "Manifest requires bounded explicit LOD metadata.")
    return deepcopy(manifest)


def _geometry_bounds(geometry, cancel, budget):
    if not isinstance(geometry, dict) or set(geometry) != {"type", "coordinates"}:
        raise JobError("invalid_source", "Only explicit non-collection GeoJSON geometries are supported.")
    depths = {"Point": 0, "MultiPoint": 1, "LineString": 1, "MultiLineString": 2, "Polygon": 2, "MultiPolygon": 3}
    kind = geometry["type"]
    if kind not in depths:
        raise JobError("invalid_source", "Unsupported geometry type.")
    bounds = [180.0, 90.0, -180.0, -90.0]

    def visit(value, depth):
        if cancel.is_set():
            raise _Cancelled()
        if not isinstance(value, list) or not value:
            raise JobError("invalid_source", "Geometry must contain coordinates.")
        if depth:
            if (kind in ("LineString", "MultiLineString") and depth == 1 and len(value) < 2
                    or kind in ("Polygon", "MultiPolygon") and depth == 1
                    and (len(value) < 4 or value[0] != value[-1])):
                raise JobError("invalid_source", "Lines require two positions and polygon rings require closure.")
            for child in value:
                visit(child, depth - 1)
        else:
            budget[0] -= 1
            if budget[0] < 0:
                raise JobError("size_exceeded", "Coordinate budget exceeded.")
            if (len(value) not in (2, 3) or not all(_finite(v) for v in value)
                    or not -180 <= value[0] <= 180 or not -90 <= value[1] <= 90):
                raise JobError("invalid_source", "Coordinates must be finite WGS84 longitude/latitude.")
            bounds[0], bounds[1] = min(bounds[0], value[0]), min(bounds[1], value[1])
            bounds[2], bounds[3] = max(bounds[2], value[0]), max(bounds[3], value[1])

    visit(geometry["coordinates"], depths[kind])
    return bounds


class LocalJobManager:
    def __init__(self, root=None, *, sources=None, policy_gate=None, max_workers=2,
                 max_pending=4, max_jobs=32, max_bytes=8 * 1024 * 1024,
                 max_features=1000, max_output_bytes=2 * 1024 * 1024):
        for value, low, high in ((max_workers, 1, 4), (max_pending, 0, 16), (max_jobs, 1, 128),
                                 (max_bytes, 1, 64 * 1024 * 1024), (max_features, 1, 10000),
                                 (max_output_bytes, 1, 8 * 1024 * 1024)):
            if type(value) is not int or not low <= value <= high:
                raise ValueError("Job bounds are outside supported limits.")
        if max_jobs < max_workers + max_pending:
            raise ValueError("Job history must fit all admitted work.")
        self.root = Path(root).absolute() if root is not None else None
        self.sources = deepcopy(sources or {})
        self.policy_gate = policy_gate
        self.max_bytes, self.max_features = max_bytes, max_features
        self.max_output_bytes = max_output_bytes
        self._capacity, self._max_jobs = max_workers + max_pending, max_jobs
        self._jobs, self._lock, self._closed = {}, threading.RLock(), False
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="local-service-job")

    def _gate(self, service_id):
        try:
            product = get_product(service_id)
        except (KeyError, TypeError):
            raise JobError("permission_blocked", "Unknown reviewed service.") from None
        if product.permission_blockers:
            raise JobError("permission_blocked", "Reviewed registry blocks this product.")
        if service_id not in SUPPORTED_WORKFLOWS:
            raise JobError("needs_setup", "No supported local workflow for this product.")
        if not callable(self.policy_gate):
            raise JobError("needs_setup", "Backend policy gate is not configured.")
        decision = self.policy_gate(service_id)
        if not isinstance(decision, dict) or decision.get("effective_enabled") is not True:
            state = decision.get("state", "disabled") if isinstance(decision, dict) else "disabled"
            raise JobError(state, "Current backend policy does not permit this job.")
        if self.root is None:
            raise JobError("needs_setup", "Operator local import root is not configured.")

    def submit(self, service_id, request):
        self._gate(service_id)
        operation = SUPPORTED_WORKFLOWS[service_id]
        fields = {"operation", "source_id", "bbox"} if operation == "import_geojson" else {"operation", "source_id"}
        if not isinstance(request, dict) or set(request) != fields or request["operation"] != operation:
            raise JobError("invalid_request", "Only the exact supported job request fields are allowed.")
        source_id = request["source_id"]
        if not isinstance(source_id, str) or re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", source_id) is None:
            raise JobError("invalid_request", "A configured opaque source ID is required.")
        source = self.sources.get(source_id)
        if (not isinstance(source, dict) or source.get("service_id") != service_id
                or not _sha(source.get("manifest_sha256"))
                or any(field not in source for field in _PROOF_FIELDS)):
            raise JobError("needs_setup", "Exact source proof is not configured by the operator.")
        _relative(source.get("path"))
        _relative(source.get("manifest_path"))
        if operation == "import_geojson":
            bbox = request["bbox"]
            if (not isinstance(bbox, list) or len(bbox) != 4 or not all(_finite(v) for v in bbox)
                    or not -180 <= bbox[0] < bbox[2] <= 180 or not -90 <= bbox[1] < bbox[3] <= 90
                    or bbox[2] - bbox[0] > 10 or bbox[3] - bbox[1] > 10):
                raise JobError("invalid_request", "A non-wrapping regional extent of at most 10 by 10 degrees is required.")
        with self._lock:
            if self._closed:
                raise JobError("unavailable", "Job manager is closed.")
            if sum(j["state"] not in _TERMINAL for j in self._jobs.values()) >= self._capacity:
                raise JobError("queue_full", "Local job concurrency/queue bound reached.")
            while len(self._jobs) >= self._max_jobs:
                old = next((key for key, job in self._jobs.items() if job["state"] in _TERMINAL), None)
                if old is None:
                    raise JobError("queue_full", "Local job retention bound reached.")
                del self._jobs[old]
            job_id = uuid4().hex
            job = {"id": job_id, "service_id": service_id, "operation": operation,
                   "source_id": source_id, "state": "queued", "result": None, "error": None,
                   "cancel": threading.Event()}
            self._jobs[job_id] = job
            job["future"] = self._executor.submit(self._run, job, deepcopy(request), deepcopy(source))
            return self._snapshot(job)

    @staticmethod
    def _snapshot(job):
        return deepcopy({key: value for key, value in job.items() if key not in ("cancel", "future")})

    def _lookup(self, job_id, service_id):
        job = self._jobs.get(job_id) if isinstance(job_id, str) else None
        if job is None or service_id is not None and job["service_id"] != service_id:
            raise JobError("not_found", "Job was not found for this service.")
        return job

    def status(self, job_id, service_id=None):
        with self._lock:
            return self._snapshot(self._lookup(job_id, service_id))

    def cancel(self, job_id, service_id=None):
        with self._lock:
            job = self._lookup(job_id, service_id)
            job["cancel"].set()
            job["result"] = None
            if job["state"] in _TERMINAL:
                job.update(state="cancelled", error=None)
            else:
                # Keep admission occupied until the worker drains the queue entry.
                # Future.cancel() would allow an unbounded backlog of cancelled items.
                job["state"] = "cancelling"
            return self._snapshot(job)

    def cancel_service(self, service_id):
        with self._lock:
            for job in list(self._jobs.values()):
                if job["service_id"] == service_id:
                    self.cancel(job["id"], service_id)

    def _run(self, job, request, source):
        cancel, service_id = job["cancel"], job["service_id"]
        result, error, state = None, None, "failed"
        try:
            with self._lock:
                job["state"] = "running"
            if cancel.is_set():
                raise _Cancelled()
            self._gate(service_id)
            manifest_data = _read_bounded(self.root, source["manifest_path"], 65536, cancel)
            if hashlib.sha256(manifest_data).hexdigest() != source["manifest_sha256"]:
                raise JobError("permission_blocked", "Manifest does not match operator-reviewed content hash.")
            manifest = validate_manifest(_json(manifest_data), source, service_id, self.max_bytes)
            if request["operation"] not in manifest["allowed_operations"]:
                raise JobError("permission_blocked", "Recorded proof does not permit this operation.")
            content = _read_bounded(self.root, source["path"], self.max_bytes, cancel)
            if len(content) != manifest["size_bytes"] or hashlib.sha256(content).hexdigest() != manifest["sha256"]:
                raise JobError("invalid_source", "Content hash/size differs from reviewed manifest.")
            # Temporary staging is bounded and always removed before terminal status.
            with tempfile.TemporaryDirectory(prefix=".service-job-", dir=self.root) as staging:
                if request["operation"] == "import_geojson":
                    if manifest["units"] != "degrees" or manifest["axes"] != "x-east,y-north,z-up":
                        raise JobError("invalid_manifest", "GeoJSON requires explicit WGS84 angular coordinates.")
                    data = _json(content)
                    if (not isinstance(data, dict) or set(data) - {"type", "features", "bbox"}
                            or data.get("type") != "FeatureCollection" or not isinstance(data.get("features"), list)
                            or len(data["features"]) > 10000):
                        raise JobError("invalid_source", "A bounded WGS84 GeoJSON FeatureCollection is required.")
                    selected, excluded, budget = [], 0, [100000]
                    west, south, east, north = request["bbox"]
                    for feature in data["features"]:
                        if (not isinstance(feature, dict) or set(feature) - {"type", "id", "geometry", "properties", "bbox"}
                                or feature.get("type") != "Feature" or not isinstance(feature.get("properties"), dict)):
                            raise JobError("invalid_source", "Unsupported GeoJSON feature schema.")
                        bounds = _geometry_bounds(feature.get("geometry"), cancel, budget)
                        # No implicit clipping or import of a world-spanning intersecting feature.
                        if west <= bounds[0] <= bounds[2] <= east and south <= bounds[1] <= bounds[3] <= north:
                            selected.append(feature)
                            if len(selected) > self.max_features:
                                raise JobError("size_exceeded", "Selected feature budget exceeded.")
                        else:
                            excluded += 1
                    result = {"data": {"type": "FeatureCollection", "features": selected},
                              "bbox": request["bbox"], "partial": excluded > 0, "excluded_features": excluded,
                              "provenance": manifest, "workspace_mutated": False}
                else:
                    result = {"manifest": manifest, "content_verified": True, "renderable_verified": False,
                              "reason": "Manifest/content validated only; no model decoder or renderer invoked."}
                encoded = json.dumps(result, allow_nan=False, separators=(",", ":")).encode("utf-8")
                if len(encoded) > self.max_output_bytes:
                    raise JobError("size_exceeded", "Job output exceeds the configured byte budget.")
                with open(Path(staging) / "result.json", "xb") as stream:
                    stream.write(encoded)
                self._gate(service_id)
                if cancel.is_set():
                    raise _Cancelled()
            state = "completed"
        except _Cancelled:
            state = "cancelled"
        except JobError as exc:
            error = {"state": exc.state, "message": str(exc)}
        except Exception:
            error = {"state": "failed", "message": "Local workflow failed; check operator source configuration."}
        finally:
            with self._lock:
                if cancel.is_set():
                    state, result, error = "cancelled", None, None
                job.update(state=state, result=result if state == "completed" else None, error=error)

    def close(self):
        with self._lock:
            self._closed = True
            for job in list(self._jobs.values()):
                self.cancel(job["id"])
        self._executor.shutdown(wait=True)
