"""Offline authenticated discovery fixtures: python -B -m unittest backend.test_authenticated."""

from concurrent.futures import ThreadPoolExecutor
import json
import socket
import threading
import unittest
from unittest import mock
from urllib.parse import parse_qs

from backend.errors import ServiceError
from backend.providers.authenticated import AuthenticatedProviders, CDSE_HUB, CDSE_IDENTITY, CDSE_ORIGIN, STANDALONE_HUB, ARCGIS_ORIGIN
from backend.providers.query import ProviderQuery
from backend.providers.transport import HTTPSPinnedTransport, Request


def query(**changes):
    values = dict(bbox=(-1, 50, 1, 52), start="2026-01-01T00:00:00Z", end="2026-01-02T00:00:00Z", dataset="sentinel-2-l2a", limit=2)
    values.update(changes)
    return ProviderQuery(**values)


def catalogue():
    return {"type": "FeatureCollection", "features": [{"type": "Feature", "id": "S2A_fixture", "collection": "sentinel-2-l2a",
        "geometry": {"type": "Polygon", "coordinates": [[[-1, 50], [1, 50], [1, 52], [-1, 50]]]},
        "properties": {"datetime": "2026-01-01T12:00:00Z", "eo:cloud_cover": 10, "secret": "ignored-fixture-secret"},
        "assets": {"data": {"href": "https://unreviewed.invalid/image?token=ignored-fixture-secret"}}}],
        "links": []}


class FakeTransport:
    def __init__(self):
        self.calls = []
        self.token = {"access_token": "fixture-backend-token", "token_type": "Bearer", "expires_in": 300}
        self.catalogue = catalogue()

    def fetch(self, request, cancel=None):
        self.calls.append(request)
        if request.url.endswith("/token"):
            value = self.token
        elif request.origin == ARCGIS_ORIGIN:
            value = {"version": 8, "layers": [{}], "sources": {"secret": "ignored-fixture-secret"}}
        else:
            value = self.catalogue
        return json.dumps(value).encode("utf-8")


class AuthenticatedTests(unittest.TestCase):
    def setUp(self):
        for name in ("getaddrinfo", "socket", "create_connection"):
            patch = mock.patch.object(socket, name, side_effect=AssertionError("External networking forbidden"))
            patch.start()
            self.addCleanup(patch.stop)
        self.transport = FakeTransport()
        self.now = [1000]
        self.resolved = []
        self.credentials = {"cdse.processing": {"client_id": "fixture-cdse-client", "client_secret": "fixture-cdse-secret"},
                            "sentinel_hub.standalone": {"client_id": "fixture-independent-client", "client_secret": "fixture-independent-secret"},
                            "arcgis.basemaps": {"public_token": "fixture-scoped-static-token"}}
        self.enabled = True
        self.provider = AuthenticatedProviders(transport=self.transport, resolve_credentials=self.resolve,
                    policy_gate=lambda *_: {"effective_enabled": self.enabled}, clock=lambda: self.now[0])

    def resolve(self, identity):
        self.resolved.append(identity)
        return self.credentials.get(identity, {})

    def error(self, status, call, *args, **kwargs):
        with self.assertRaises(ServiceError) as caught:
            call(*args, **kwargs)
        self.assertEqual(caught.exception.status, status)
        return caught.exception

    def test_fixed_cdse_oauth_form_and_no_token_export(self):
        result = self.provider.request_token("cdse.processing")
        request = self.transport.calls[0]
        self.assertIsInstance(request, Request)
        self.assertEqual(request.url, CDSE_IDENTITY + "/auth/realms/CDSE/protocol/openid-connect/token")
        self.assertEqual(request.origin, CDSE_IDENTITY)
        self.assertEqual(request.method, "POST")
        self.assertEqual(dict(request.headers)["Content-Type"], "application/x-www-form-urlencoded")
        self.assertEqual(parse_qs(request.body.decode()), {"grant_type": ["client_credentials"], "client_id": ["fixture-cdse-client"], "client_secret": ["fixture-cdse-secret"]})
        for value in (repr(request), repr(self.provider), repr(self.provider._tokens), json.dumps(result)):
            self.assertNotIn("fixture-cdse-secret", value)
            self.assertNotIn("fixture-backend-token", value)
        self.assertFalse(result["entitlement_verified"])

    def test_cache_refresh_expiry_rotation_and_invalidation(self):
        self.provider.request_token("cdse.processing")
        self.now[0] = 1269
        self.provider.request_token("cdse.processing")
        self.assertEqual(len(self.transport.calls), 1)
        self.now[0] = 1270
        self.provider.request_token("cdse.processing")
        self.assertEqual(len(self.transport.calls), 2)
        self.credentials["cdse.processing"]["client_secret"] = "fixture-replaced-secret"
        self.provider.request_token("cdse.processing")
        self.assertEqual(len(self.transport.calls), 3)
        self.provider.invalidate("cdse.processing")
        self.provider.request_token("cdse.processing")
        self.assertEqual(len(self.transport.calls), 4)
        self.credentials["cdse.processing"] = {}
        self.error(409, self.provider.request_token, "cdse.processing")

    def test_concurrent_refresh_is_single_flight(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: self.provider.request_token("cdse.processing"), range(16)))
        self.assertEqual(len(results), 16)
        self.assertEqual(len(self.transport.calls), 1)

    def test_resolver_is_outside_cache_lock_and_invalidation_race_retries(self):
        calls = []
        def resolve(identity):
            self.assertTrue(self.provider._lock.acquire(blocking=False))
            self.provider._lock.release()
            calls.append(identity)
            if len(calls) == 1:
                old = dict(self.credentials[identity])
                self.credentials[identity]["client_secret"] = "fixture-new-secret"
                self.provider.invalidate(identity)
                return old
            return self.credentials[identity]
        self.provider._resolve = resolve
        self.provider.request_token("cdse.processing")
        self.assertEqual(len(calls), 2)
        self.assertIn(b"fixture-new-secret", self.transport.calls[0].body)

    def test_catalogue_links_are_not_followed_and_only_next_marks_truncation(self):
        self.transport.catalogue["links"] = [{"rel": "self", "href": "https://unreviewed.invalid"}]
        self.assertFalse(self.provider.catalogue_query("cdse.catalogue", query())["truncated"])
        self.transport.catalogue["links"] = [{"rel": "next", "href": "https://unreviewed.invalid?token=fixture"}]
        self.assertTrue(self.provider.catalogue_query("cdse.catalogue", query())["truncated"])
        self.assertEqual(len(self.transport.calls), 2)

    def test_cancellation_prevents_requests_and_cache_publication(self):
        cancel = threading.Event()
        cancel.set()
        self.error(499, self.provider.request_token, "cdse.processing", cancel=cancel)
        self.assertEqual(self.transport.calls, [])
        cancel.clear()
        original = self.transport.fetch
        def fetch(request, cancel=None):
            result = original(request, cancel)
            cancel.set()
            return result
        self.transport.fetch = fetch
        self.error(499, self.provider.request_token, "cdse.processing", cancel=cancel)
        self.assertEqual(self.provider._tokens, {})

    def test_lock_wait_is_cancellable(self):
        cancel = threading.Event()
        self.provider._lock.acquire()
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(self.provider.request_token, "cdse.processing", cancel=cancel)
                cancel.set()
                self.error(499, future.result, timeout=2)
        finally:
            self.provider._lock.release()
        self.assertEqual(self.transport.calls, [])

    def test_standalone_requires_independent_credentials_and_origin(self):
        self.provider.catalogue_query("cdse.processing", query())
        self.credentials["sentinel_hub.standalone"] = {}
        self.error(409, self.provider.catalogue_query, "sentinel_hub.standalone", query())
        self.assertEqual(len(self.transport.calls), 2)
        self.credentials["sentinel_hub.standalone"] = {"client_id": "standalone-only", "client_secret": "standalone-secret"}
        self.provider.catalogue_query("sentinel_hub.standalone", query())
        self.assertEqual(self.transport.calls[-2].origin, STANDALONE_HUB)
        self.assertEqual(self.transport.calls[-1].url, STANDALONE_HUB + "/api/v1/catalog/1.0.0/search")
        self.assertIn(b"standalone-secret", self.transport.calls[-2].body)
        self.assertNotIn(b"fixture-cdse", self.transport.calls[-2].body)

    def test_public_core_catalogue_has_no_credential_resolution(self):
        result = self.provider.catalogue_query("cdse.catalogue", query())
        self.assertEqual(self.resolved, [])
        request = self.transport.calls[0]
        self.assertEqual(request.url, CDSE_ORIGIN + "/v1/search")
        self.assertNotIn("Authorization", dict(request.headers))
        body = json.loads(request.body)
        self.assertEqual(body["bbox"], [-1, 50, 1, 52])
        self.assertEqual(body["collections"], ["sentinel-2-l2a"])
        self.assertEqual(body["limit"], 2)
        self.assertIn("/", body["datetime"])
        self.assertEqual(len(result["features"]), 1)
        self.assertEqual(result["records"][0]["cloud_cover_percent"], 10)
        self.assertFalse(result["records"][0]["imagery_available"])
        self.assertNotIn("ignored-fixture-secret", json.dumps(result))
        self.assertNotIn("unreviewed.invalid", json.dumps(result))

    def test_authenticated_catalogue_fixed_bearer_header(self):
        self.provider.catalogue_query("cdse.processing", query())
        request = self.transport.calls[-1]
        self.assertEqual(request.url, CDSE_HUB + "/api/v1/catalog/1.0.0/search")
        self.assertEqual(dict(request.headers)["Authorization"], "Bearer fixture-backend-token")
        self.assertNotIn("fixture-backend-token", request.url)
        self.assertNotIn("fixture-backend-token", repr(request))
        self.assertLessEqual(request.max_decompressed, 1024 * 1024)

    def test_query_bounds_hls_and_unknown_inputs_fail_before_transport(self):
        for changes in ({"dataset": "hls"}, {"dataset": "HLSL30"}, {"pages": 2}, {"text": "raw"}, {"bbox": None}, {"start": None, "end": None}):
            self.error(400, self.provider.catalogue_query, "cdse.catalogue", query(**changes))
        self.error(400, ProviderQuery.from_dict, {"url": "https://evil.invalid"})
        self.error(400, ProviderQuery.from_dict, {"bbox": [-180, -90, 180, 90]})
        self.error(400, ProviderQuery.from_dict, {"start": "2026-01-01", "end": "2026-01-02"})
        self.assertEqual(self.transport.calls, [])

    def test_policy_gate_is_required_even_for_cached_tokens(self):
        self.provider.request_token("cdse.processing")
        self.enabled = False
        self.error(403, self.provider.request_token, "cdse.processing")
        self.error(403, self.provider.catalogue_query, "cdse.catalogue", query())
        self.assertEqual(len(self.transport.calls), 1)

    def test_bad_oauth_responses_are_not_cached_or_echoed(self):
        for token in ({"access_token": "fixture-secret", "token_type": "Bearer", "expires_in": True},
                      {"access_token": "fixture-secret\r\n", "token_type": "Bearer", "expires_in": 300},
                      {"access_token": "fixture-secret", "token_type": "Basic", "expires_in": 300},
                      {"access_token": "fixture-secret", "token_type": {}, "expires_in": 300},
                      {"access_token": "fixture-secret", "token_type": "Bearer", "expires_in": 0}):
            self.transport.token = token
            error = self.error(422, self.provider.request_token, "cdse.processing")
            self.assertNotIn("fixture-secret", str(error))
            self.assertEqual(self.provider._tokens, {})

    def test_transport_errors_are_redacted(self):
        self.transport.fetch = mock.Mock(side_effect=ServiceError("fixture-cdse-secret fixture-backend-token", 429))
        error = self.error(429, self.provider.request_token, "cdse.processing")
        self.assertNotIn("fixture", str(error))
        self.assertIsNone(error.__cause__)

    def test_bad_catalogue_geometry_schema_time_and_size_fail_closed(self):
        for change in (lambda v: v["features"][0].update(collection="hls"),
                       lambda v: v["features"][0].update(geometry={"type": "Point", "coordinates": [0, 51]}),
                       lambda v: v["features"][0]["geometry"]["coordinates"][0].append([False, 50]),
                       lambda v: v["features"][0]["properties"].update(datetime="2025-01-01T00:00:00Z"),
                       lambda v: v.update(features=v["features"] * 3)):
            self.transport.catalogue = catalogue()
            change(self.transport.catalogue)
            self.error(422, self.provider.catalogue_query, "cdse.catalogue", query())
        self.transport.fetch = mock.Mock(return_value=b" " * (1024 * 1024 + 1))
        self.error(413, self.provider.catalogue_query, "cdse.catalogue", query())

    def test_arcgis_static_style_metadata_not_legacy_imagery_or_urls(self):
        result = self.provider.arcgis_style_metadata()
        request = self.transport.calls[0]
        self.assertEqual(request.origin, ARCGIS_ORIGIN)
        self.assertEqual(request.url, ARCGIS_ORIGIN + "/arcgis/rest/services/styles/v2/styles/arcgis/imagery")
        self.assertEqual(dict(request.headers)["Authorization"], "Bearer fixture-scoped-static-token")
        self.assertNotIn("?", request.url)
        self.assertFalse(result["imagery_available"])
        self.assertFalse(result["entitlement_verified"])
        self.assertNotIn("sources", result)
        self.assertNotIn("fixture", json.dumps(result))
        self.error(409, self.provider.capabilities, "esri.world_imagery")

    def test_current_real_transport_fails_closed_without_origin_review(self):
        self.provider._transport = HTTPSPinnedTransport()
        self.error(400, self.provider.catalogue_query, "cdse.processing", query())

    def test_capabilities_do_not_claim_implemented_processing_or_entitlements(self):
        for product in ("cdse.catalogue", "cdse.processing", "sentinel_hub.standalone", "arcgis.basemaps"):
            value = self.provider.capabilities(product)
            self.assertFalse(value["imagery_bytes"])
            self.assertFalse(value["live_imagery"])
            self.assertFalse(value["entitlement_verified"])
            self.assertTrue(value["blockers"])


if __name__ == "__main__":
    unittest.main()
