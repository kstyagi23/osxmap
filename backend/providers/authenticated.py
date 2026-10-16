"""Backend-only authenticated discovery, with fixed endpoints and no token export.

Transport and protected credential resolution are injected by the broker. This
module does not register adapters, enable products, persist tokens or fetch assets.
OAuth form POST/origins require separate pinned-transport review before deployment.
"""

from dataclasses import dataclass, field
import hashlib
import json
import re
import threading
import time
from urllib.parse import urlencode

from ..errors import ServiceError
from .query import ProviderQuery, number, utc_time
from .transport import Request


CDSE_ORIGIN = "https://stac.dataspace.copernicus.eu"
CDSE_IDENTITY = "https://identity.dataspace.copernicus.eu"
CDSE_HUB = "https://sh.dataspace.copernicus.eu"
STANDALONE_HUB = "https://services.sentinel-hub.com"
ARCGIS_ORIGIN = "https://basemapstyles-api.arcgis.com"
_OAUTH = {
    "cdse.processing": (CDSE_IDENTITY, "/auth/realms/CDSE/protocol/openid-connect/token", CDSE_HUB),
    "sentinel_hub.standalone": (STANDALONE_HUB, "/auth/realms/main/protocol/openid-connect/token", STANDALONE_HUB),
}
_CATALOGUES = {
    "cdse.catalogue": (CDSE_ORIGIN, "/v1/search"),
    "cdse.processing": (CDSE_HUB, "/api/v1/catalog/1.0.0/search"),
    "sentinel_hub.standalone": (STANDALONE_HUB, "/api/v1/catalog/1.0.0/search"),
}
_COLLECTION = "sentinel-2-l2a"
_MAX_JSON = 1024 * 1024
_IDENTIFIER = re.compile(r"[A-Za-z0-9_.:-]{1,160}\Z")


@dataclass(repr=False)
class _Token:
    value: str = field(repr=False)
    fingerprint: bytes = field(repr=False)
    deadline: float


def _cancelled(cancel):
    if cancel is not None and cancel.is_set():
        raise ServiceError("Provider request cancelled.", 499)


def _json(raw, maximum):
    if not isinstance(raw, bytes) or not 1 <= len(raw) <= maximum:
        raise ServiceError("Provider response byte bound exceeded.", 413)
    try:
        value = json.loads(raw)
    except (ValueError, UnicodeError, RecursionError):
        raise ServiceError("Provider JSON response is invalid.", 422) from None
    if not isinstance(value, dict):
        raise ServiceError("Provider response schema is invalid.", 422)
    return value


def _footprint(value):
    """Copy only bounded WGS84 polygon coordinates, never arbitrary GeoJSON fields."""
    try:
        kind = value["type"]
        polygons = [value["coordinates"]] if kind == "Polygon" else value["coordinates"]
        if kind not in {"Polygon", "MultiPolygon"} or not isinstance(polygons, list) or not 1 <= len(polygons) <= 32:
            raise ValueError
        count, output = 0, []
        for polygon in polygons:
            if not isinstance(polygon, list) or not 1 <= len(polygon) <= 32:
                raise ValueError
            rings = []
            for ring in polygon:
                if not isinstance(ring, list) or not 4 <= len(ring) <= 2048 or ring[0] != ring[-1]:
                    raise ValueError
                count += len(ring)
                if count > 2048:
                    raise ValueError
                points = []
                for point in ring:
                    if (not isinstance(point, list) or len(point) != 2 or not number(point[0], -180, 180)
                            or not number(point[1], -90, 90)):
                        raise ValueError
                    points.append(list(point))
                rings.append(points)
            output.append(rings)
        return {"type": kind, "coordinates": output[0] if kind == "Polygon" else output}
    except (KeyError, TypeError, ValueError, IndexError):
        raise ServiceError("Catalogue granule footprint is invalid.", 422) from None


class AuthenticatedProviders:
    """Executable discovery foundation, not evidence of account entitlement.

    ``policy_gate(id, query)`` must return an authoritative effective-enabled
    decision. ``resolve_credentials(id)`` resolves write-only DPAPI-backed broker
    records; no raw credentials may be supplied in query data. Token requests
    return status metadata only. Invalidate after every credential/policy change.
    """

    def __init__(self, *, transport, resolve_credentials, policy_gate, clock=time.monotonic):
        self._transport = transport
        self._resolve = resolve_credentials
        self._gate = policy_gate
        self._clock = clock
        self._lock = threading.Lock()
        self._tokens = {}
        self._generation = 0

    def capabilities(self, product_id):
        if product_id not in {*_CATALOGUES, "arcgis.basemaps"}:
            raise ServiceError("Authenticated product is unsupported.", 409)
        return {"provider_id": product_id, "capabilities": ["style_metadata"] if product_id == "arcgis.basemaps" else ["granule_discovery", "granule_footprints"],
                "imagery_bytes": False, "live_imagery": False, "entitlement_verified": False,
                "blockers": ["Not registered in provider runtime; broker policy and quota admission required.",
                             "Fixed origins require pinned transport allowlist review.",
                             "OAuth requires reviewed form-encoded POST transport support." if product_id in _OAUTH else
                             "Static ArcGIS token must have exact product scope." if product_id == "arcgis.basemaps" else
                             "HLS and non-Sentinel collections require independent endpoint/collection review.",
                             "Processing/raster bytes are not implemented; JSON metadata is not imagery."]}

    def _authorize(self, product_id, query):
        try:
            decision = self._gate(product_id, query)
        except Exception:
            raise ServiceError("Provider policy resolution failed.", 403) from None
        if not isinstance(decision, dict) or decision.get("effective_enabled") is not True:
            raise ServiceError("Provider operation is not enabled by broker policy.", 403)

    def _credentials(self, product_id, fields):
        try:
            values = self._resolve(product_id)
            if not isinstance(values, dict) or any(
                    not isinstance(values.get(key), str) or not 1 <= len(values[key]) <= 900
                    or not values[key].strip()
                    or any(ord(c) < 32 or ord(c) == 127 for c in values[key]) for key in fields):
                raise ValueError
            return {key: values[key] for key in fields}
        except Exception:
            raise ServiceError("Required protected provider credentials are unavailable.", 409) from None

    def _fetch(self, request, cancel):
        _cancelled(cancel)
        try:
            raw = self._transport.fetch(request, cancel=cancel)
        except Exception as error:
            _cancelled(cancel)
            status = error.status if isinstance(error, ServiceError) and error.status in {400, 403, 409, 413, 415, 422, 429, 499, 502, 503, 504} else 502
            raise ServiceError("Authenticated provider request failed.", status) from None
        _cancelled(cancel)
        return raw

    def invalidate(self, product_id=None):
        with self._lock:
            self._generation += 1
            if product_id is None:
                self._tokens.clear()
            else:
                self._tokens.pop(product_id, None)

    def _token(self, product_id, cancel):
        if product_id not in _OAUTH:
            raise ServiceError("Product does not support this OAuth flow.", 409)
        _cancelled(cancel)
        # Broker callbacks must stay outside the cache lock: Settings mutations
        # can hold their own lock while invalidating this cache.
        while True:
            while not self._lock.acquire(timeout=0.05):
                _cancelled(cancel)
            generation = self._generation
            self._lock.release()
            credentials = self._credentials(product_id, ("client_id", "client_secret"))
            fingerprint = hashlib.sha256(json.dumps(credentials, sort_keys=True).encode("utf-8")).digest()
            while not self._lock.acquire(timeout=0.05):
                _cancelled(cancel)
            if generation == self._generation:
                break
            self._lock.release()
            _cancelled(cancel)
        try:
            _cancelled(cancel)
            cached = self._tokens.get(product_id)
            if cached is not None and cached.fingerprint == fingerprint and self._clock() < cached.deadline:
                return cached.value
            self._tokens.pop(product_id, None)
            origin, path, _ = _OAUTH[product_id]
            body = urlencode({"grant_type": "client_credentials", **credentials}).encode("ascii")
            started = self._clock()
            value = _json(self._fetch(Request(origin + path, origin,
                headers=(("Content-Type", "application/x-www-form-urlencoded"), ("Accept", "application/json")),
                method="POST", body=body, max_compressed=16384, max_decompressed=16384), cancel), 16384)
            token, ttl = value.get("access_token"), value.get("expires_in")
            if (not isinstance(value.get("token_type"), str) or value["token_type"].lower() != "bearer" or not isinstance(token, str)
                    or not re.fullmatch(r"[A-Za-z0-9._~+/-]{1,900}=*", token) or len(token) > 900
                    or not number(ttl, 1, 86400)):
                raise ServiceError("OAuth token response is invalid.", 422)
            deadline = started + ttl - min(30, ttl / 10)
            _cancelled(cancel)
            if self._clock() >= deadline:
                raise ServiceError("OAuth token expired during acquisition.", 502)
            self._tokens[product_id] = _Token(token, fingerprint, deadline)
            return token
        finally:
            self._lock.release()

    def request_token(self, product_id, *, cancel=None):
        """Acquire/reacquire client_credentials; never return an access token."""
        self._authorize(product_id, None)
        self._token(product_id, cancel)
        self._authorize(product_id, None)
        _cancelled(cancel)
        return {"provider_id": product_id, "state": "token_available", "entitlement_verified": False}

    def catalogue_query(self, product_id, query, *, cancel=None):
        if product_id not in _CATALOGUES or not isinstance(query, ProviderQuery):
            raise ServiceError("Catalogue product or typed query is unsupported.", 400)
        query.require("bbox", "start", "end", "dataset")
        if (query.dataset != _COLLECTION or query.pages != 1 or query.latitude is not None
                or query.entity_id is not None or query.text is not None):
            raise ServiceError("Catalogue requires a bounded Sentinel-2 L2A viewport/time query; HLS is not reviewed.", 400)
        _cancelled(cancel)
        self._authorize(product_id, query)
        origin, path = _CATALOGUES[product_id]
        headers = (("Content-Type", "application/json"),)
        if product_id in _OAUTH:
            headers += (("Authorization", "Bearer " + self._token(product_id, cancel)),)
        start, end = utc_time(query.start), utc_time(query.end)
        body = json.dumps({"bbox": list(query.bbox), "datetime": start.isoformat() + "/" + end.isoformat(),
                           "collections": [_COLLECTION], "limit": query.limit}, separators=(",", ":")).encode("ascii")
        value = _json(self._fetch(Request(origin + path, origin, headers=headers, method="POST", body=body,
                     max_compressed=_MAX_JSON, max_decompressed=_MAX_JSON), cancel), _MAX_JSON)
        items = value.get("features")
        if value.get("type") != "FeatureCollection" or not isinstance(items, list) or len(items) > query.limit:
            raise ServiceError("Catalogue feature count/schema is invalid.", 422)
        features, records = [], []
        for item in items:
            _cancelled(cancel)
            if not isinstance(item, dict) or item.get("type") != "Feature" or item.get("collection") != _COLLECTION:
                raise ServiceError("Catalogue collection/schema is invalid.", 422)
            identity, props = item.get("id"), item.get("properties")
            if not isinstance(identity, str) or not _IDENTIFIER.fullmatch(identity) or not isinstance(props, dict):
                raise ServiceError("Catalogue granule metadata is invalid.", 422)
            observed = utc_time(props.get("datetime"))
            if not start <= observed <= end:
                raise ServiceError("Catalogue observation is outside requested time bounds.", 422)
            shape = _footprint(item.get("geometry"))
            polygons = [shape["coordinates"]] if shape["type"] == "Polygon" else shape["coordinates"]
            points = [point for polygon in polygons for ring in polygon for point in ring]
            w, s, e, n = query.bbox
            if max(p[0] for p in points) < w or min(p[0] for p in points) > e or max(p[1] for p in points) < s or min(p[1] for p in points) > n:
                raise ServiceError("Catalogue footprint is outside requested viewport.", 422)
            metadata = {"provider_id": product_id, "entity_id": identity, "collection": _COLLECTION,
                        "observed_at": observed.isoformat().replace("+00:00", "Z"), "source": origin + path,
                        "data_kind": "granule_metadata", "imagery_available": False}
            cloud = props.get("eo:cloud_cover")
            if number(cloud, 0, 100):
                metadata["cloud_cover_percent"] = cloud
            records.append(dict(metadata))
            features.append({"type": "Feature", "id": product_id + ":" + identity, "geometry": shape, "properties": dict(metadata)})
        self._authorize(product_id, query)
        _cancelled(cancel)
        links = value.get("links", [])
        if not isinstance(links, list) or len(links) > 100 or any(not isinstance(link, dict) for link in links):
            raise ServiceError("Catalogue pagination metadata is invalid.", 422)
        return {"provider_id": product_id, "state": "ready", "features": features, "records": records,
                "truncated": len(items) == query.limit or any(link.get("rel") == "next" for link in links), "partial": False,
                "provenance": {"source": origin + path, "crs": "EPSG:4326", "data_kind": "granule_metadata",
                               "linked_media": "not fetched or returned", "entitlement_verified": False}}

    def arcgis_style_metadata(self, *, cancel=None):
        """Static scoped token, fixed Location Platform product; not legacy tiles."""
        product_id = "arcgis.basemaps"
        _cancelled(cancel)
        self._authorize(product_id, None)
        token = self._credentials(product_id, ("public_token",))["public_token"]
        if not re.fullmatch(r"[A-Za-z0-9._~+/-]{1,900}=*", token):
            raise ServiceError("ArcGIS scoped static token is invalid.", 409)
        url = ARCGIS_ORIGIN + "/arcgis/rest/services/styles/v2/styles/arcgis/imagery"
        value = _json(self._fetch(Request(url, ARCGIS_ORIGIN, headers=(("Authorization", "Bearer " + token),),
                          max_compressed=_MAX_JSON, max_decompressed=_MAX_JSON), cancel), _MAX_JSON)
        if value.get("version") != 8 or not isinstance(value.get("layers"), list) or len(value["layers"]) > 256 or "error" in value:
            raise ServiceError("ArcGIS style metadata is invalid.", 422)
        self._authorize(product_id, None)
        _cancelled(cancel)
        return {"provider_id": product_id, "state": "ready", "style_id": "arcgis/imagery", "style_version": 8,
                "layer_count": len(value["layers"]), "source": url, "imagery_available": False,
                "entitlement_verified": False, "linked_media": "not fetched or returned"}
