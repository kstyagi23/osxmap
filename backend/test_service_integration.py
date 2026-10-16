"""Server service boundaries with temporary storage and no HTTP listener.

Run through backend.test_isolated so imports cannot read .env or use networks.
"""

import copy
import json
import io
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest import mock
from urllib.parse import urlparse

from backend import server, service_registry
from backend.openai_client import OpenAIChatClient
from backend.providers.quota import QuotaStore
from backend.providers.runtime import ProviderRuntime
from backend.secret_store import SecretStore
from backend.service_broker import LocalBroker
from backend.service_settings import ServiceSettings
from backend.test_secret_store import FakeProtector


class Handler:
    service_route = server.ApiHandler.service_route
    handle_error = server.ApiHandler.handle_error

    def __init__(self, headers, body):
        self.headers = headers
        self.body = copy.deepcopy(body)
        self.response = None

    def read_json_body(self):
        return self.body

    def send_json(self, status, body, headers=None):
        self.response = (status, body, headers or {})


class ServiceIntegrationTests(unittest.TestCase):
    def test_settings_html_serves_standalone_with_exact_custom_port_configuration(self):
        handler = object.__new__(server.ApiHandler)
        handler.path = '/settings.html'
        handler.headers = {'Host': '127.0.0.1:9898'}
        handler.wfile = io.BytesIO()
        handler.responses = []
        handler.send_response = lambda status: handler.responses.append(status)
        handler.send_header = lambda *args: None
        handler.end_headers = lambda: None
        with mock.patch.object(server, 'SETTINGS_BROKER', LocalBroker(9898)):
            server.ApiHandler.do_GET(handler)
        self.assertEqual(handler.responses, [200])
        html = handler.wfile.getvalue().decode('utf-8')
        self.assertIn('window.MONUMENT_API_URL="http://127.0.0.1:9898"', html)
        self.assertIn('settings-entry.js', html)
        self.assertNotIn('maplibre', html)

    def test_cdse_discovery_admission_is_fixed_quota_and_refuses_disabled_policy(self):
        status, snapshot, headers = self.request('GET', '/api/settings/services')
        trusted = {**self.headers, 'Cookie': headers['Set-Cookie'].split(';', 1)[0], 'X-Meridian-CSRF': snapshot['csrfToken']}
        query = {'bbox': [10, 10, 11, 11], 'dataset': 'sentinel-2-l2a', 'start': '2026-10-01T00:00:00Z', 'end': '2026-10-02T00:00:00Z'}
        self.transport.fetch.return_value = b'{"type":"FeatureCollection","features":[]}'
        status, body, _ = self.request('POST', '/api/services/cdse.catalogue/query', query, trusted)
        self.assertEqual(status, 200)
        request = self.transport.fetch.call_args.args[0]
        self.assertEqual(request.origin, 'https://stac.dataspace.copernicus.eu')
        self.assertEqual(self.runtime.quota.snapshot('cdse.catalogue', 'public')['usage'][0]['used'], 1)
        self.settings.update('cdse.catalogue', {'enabled': False}, 0)
        status, _, _ = self.request('POST', '/api/services/cdse.catalogue/query', query, trusted)
        self.assertEqual(status, 403)
        self.assertEqual(self.transport.fetch.call_count, 1)

    def test_predictions_validate_before_network_and_report_missing_optional_codec(self):
        status, snapshot, headers = self.request('GET', '/api/settings/services')
        trusted = {**self.headers, 'Cookie': headers['Set-Cookie'].split(';', 1)[0], 'X-Meridian-CSRF': snapshot['csrfToken']}
        with mock.patch('backend.providers.orbits.available', return_value=False):
            status, _, _ = self.request('POST', '/api/services/celestrak.gp/predictions', {'query': {'dataset': 'stations'}, 'times': ['2026-10-16T08:00:00Z']}, trusted)
            self.assertEqual(status, 409)
            status, _, _ = self.request('POST', '/api/services/celestrak.gp/predictions', {'query': {'dataset': 'stations'}, 'times': []}, trusted)
            self.assertEqual(status, 400)
        self.transport.assert_not_called()

    def test_job_routes_bind_product_and_cancel_without_browser_paths(self):
        jobs = mock.Mock()
        jobs.submit.return_value = {"id": "abc123", "service_id": "osm.extracts", "state": "queued"}
        jobs.status.return_value = {"id": "abc123", "service_id": "osm.extracts", "state": "ready"}
        jobs.cancel.return_value = {"id": "abc123", "service_id": "osm.extracts", "state": "cancelled"}
        status, snapshot, headers = self.request("GET", "/api/settings/services")
        trusted = {**self.headers, "Cookie": headers["Set-Cookie"].split(";", 1)[0], "X-Meridian-CSRF": snapshot["csrfToken"]}
        with mock.patch.object(server, "SERVICE_JOBS", jobs):
            status, _, _ = self.request("POST", "/api/services/osm.extracts/jobs", {"operation": "import_geojson", "source_id": "configured", "bbox": [1, 1, 2, 2]}, trusted)
            self.assertEqual(status, 202)
            status, _, _ = self.request("GET", "/api/services/osm.extracts/jobs/abc123")
            self.assertEqual(status, 200)
            status, _, _ = self.request("GET", "/api/services/naturalearth.downloads/jobs/abc123")
            self.assertEqual(status, 404)
            status, _, _ = self.request("DELETE", "/api/services/osm.extracts/jobs/abc123", {}, trusted)
            self.assertEqual(status, 200)
            jobs.cancel.assert_called_once_with("abc123")

    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="meridian-service-integration-")
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name)
        self.secrets = SecretStore(self.path / "secrets", protector=FakeProtector(), restrict=lambda _: None)
        dependencies = {dependency: True for product in service_registry.PRODUCTS.values() for dependency in product.dependencies}
        self.settings = ServiceSettings(self.path / "settings.db", self.secrets, registry=service_registry,
                                        environment={"OPENAI_API_KEY": "environment-test-secret"}, dependencies=dependencies)
        self.addCleanup(self.settings.close)
        self.transport = mock.Mock(side_effect=AssertionError("No unmocked provider transport"))
        self.runtime = ProviderRuntime(QuotaStore(self.path / "quota.db"),
                                      policy_gate=lambda product, query: server.service_state(product), transport=self.transport)
        self.addCleanup(self.runtime.close)
        self.settings.cancel = self.runtime.cancel_provider
        self.broker = LocalBroker(8787)
        for patch in (mock.patch.object(server, "SERVICE_SETTINGS", self.settings),
                      mock.patch.object(server, "PROVIDER_RUNTIME", self.runtime),
                      mock.patch.object(server, "SETTINGS_BROKER", self.broker)):
            patch.start()
            self.addCleanup(patch.stop)
        self.headers = {"Host": "127.0.0.1:8787", "Origin": "http://127.0.0.1:8787", "Content-Type": "application/json"}

    def request(self, method, path, body=None, headers=None):
        handler = Handler(dict(self.headers if headers is None else headers), body or {})
        try:
            handler.service_route(method, urlparse(path))
        except Exception as error:
            handler.handle_error(error)
        self.assertIsNotNone(handler.response)
        return handler.response

    def login(self):
        status, snapshot, headers = self.request("GET", "/api/settings/services")
        self.assertEqual(status, 200)
        self.headers.update({"Cookie": headers["Set-Cookie"].split(";", 1)[0], "X-Meridian-CSRF": snapshot["csrfToken"]})
        return snapshot

    def state(self, product):
        return next(item for item in self.settings.snapshot()["services"] if item["id"] == product)

    def test_catalogue_and_settings_get_session_and_redacted_snapshot(self):
        status, catalogue, _ = self.request("GET", "/api/services")
        self.assertEqual(status, 200)
        self.assertNotIn("revision", catalogue)
        reviewed = {item["id"]: item for item in service_registry.catalogue()}
        self.assertEqual({item["id"] for item in catalogue["services"]}, set(reviewed))
        for item in catalogue["services"]:
            # Connected implementation status is derived by the server, not policy.
            self.assertEqual({key: value for key, value in item.items() if key not in {"implementation_status", "setup_steps", "blockers", "live_tested"}},
                             {key: value for key, value in reviewed[item["id"]].items() if key != "implementation_status"})
        status, snapshot, headers = self.request("GET", "/api/settings/services")
        self.assertEqual(status, 200)
        self.assertEqual(snapshot["revision"], 0)
        self.assertTrue(snapshot["csrfToken"])
        cookie = headers["Set-Cookie"]
        for flag in ("HttpOnly", "SameSite=Strict", "Path=/api/"):
            self.assertIn(flag, cookie)
        self.assertNotIn("environment-test-secret", json.dumps(snapshot))
        self.headers["Cookie"] = cookie.split(";", 1)[0]
        self.assertEqual(self.request("GET", "/api/settings/services")[1]["csrfToken"], snapshot["csrfToken"])

    def test_untrusted_reads_and_mutations_never_disclose_revision_or_credentials(self):
        self.login()
        self.settings.update("openfreemap.public", {"enabled": False}, 0)
        changes = ({"Host": "attacker.test:8787"}, {"Origin": "http://attacker.test"},
                   {"Origin": "null"}, {"Sec-Fetch-Site": "cross-site"})
        for change in changes:
            for method, path in (("GET", "/api/settings/services"), ("PUT", "/api/settings/services/openfreemap.public")):
                with self.subTest(change=change, method=method):
                    status, body, headers = self.request(method, path, {"revision": 0, "enabled": True}, {**self.headers, **change})
                    self.assertEqual(status, 403)
                    self.assertEqual(set(body), {"error"})
                    self.assertNotIn("revision", body["error"].lower())
                    self.assertNotIn("environment-test-secret", json.dumps(body))
                    self.assertNotIn("Set-Cookie", headers)
        self.assertEqual(self.settings.snapshot()["revision"], 1)

    def test_mutation_requires_bound_csrf_origin_and_json_before_reading_body(self):
        self.login()
        other_token, _ = self.broker.session({"Host": "127.0.0.1:8787"})
        for change, expected in (({"X-Meridian-CSRF": "wrong"}, 403), ({"X-Meridian-CSRF": other_token}, 403),
                                 ({"Cookie": ""}, 403), ({"Origin": ""}, 403), ({"Content-Type": "text/plain"}, 415)):
            handler = Handler({**self.headers, **change}, {})
            with self.subTest(change=change), mock.patch.object(handler, "read_json_body", side_effect=AssertionError("Untrusted body read")):
                try:
                    handler.service_route("PUT", urlparse("/api/settings/services/openfreemap.public"))
                except Exception as error:
                    handler.handle_error(error)
                self.assertEqual(handler.response[0], expected)
        self.assertEqual(self.settings.snapshot()["revision"], 0)

    def test_trusted_update_and_stale_revision_preserve_settings_and_secrets(self):
        self.login()
        status, result, _ = self.request("PUT", "/api/settings/services/openfreemap.public", {"revision": 0, "enabled": False})
        self.assertEqual(status, 200)
        self.assertEqual(result["revision"], 1)
        self.assertFalse(self.state("openfreemap.public")["effective_enabled"])
        operations = (("PUT", "/api/settings/services/openfreemap.public", {"enabled": True}),
                      ("PUT", "/api/settings/services/openai.api/credentials", {"credentials": {"api_key": "stale-test-secret"}}),
                      ("DELETE", "/api/settings/services/openai.api/credentials", {}),
                      ("POST", "/api/settings/services/openfreemap.public/test", {"query": {"bbox": [0, 0, 1, 1]}}))
        for method, path, body in operations:
            with self.subTest(method=method, path=path):
                status, result, _ = self.request(method, path, {"revision": 0, **body})
                self.assertEqual(status, 409)
                self.assertEqual(set(result), {"error"})
                self.assertNotIn("stale-test-secret", json.dumps(result))
        self.assertEqual(self.secrets.read("openai.api"), {})
        self.assertEqual(self.settings.snapshot()["revision"], 1)

    def test_credential_replace_delete_are_write_only_and_revisioned(self):
        self.login()
        status, result, _ = self.request("PUT", "/api/settings/services/openai.api/credentials",
                                        {"revision": 0, "credentials": {"api_key": "saved-test-secret"}})
        self.assertEqual(status, 200)
        self.assertEqual(result["revision"], 1)
        self.assertNotIn("saved-test-secret", json.dumps(result))
        self.assertEqual(self.secrets.read("openai.api"), {"api_key": "saved-test-secret"})
        self.assertEqual(self.state("openai.api")["credentials"]["source"], "environment")
        status, result, _ = self.request("DELETE", "/api/settings/services/openai.api/credentials", {"revision": 1})
        self.assertEqual(status, 200)
        self.assertEqual(result["revision"], 2)
        self.assertEqual(self.secrets.read("openai.api"), {})

    def test_unknown_query_keys_and_url_queries_rejected_before_dispatch(self):
        self.login()
        for path in ("/api/services?url=https://example.org", "/api/settings/services?revision=0"):
            with self.subTest(path=path):
                self.assertEqual(self.request("GET", path)[0], 400)
        for body in ({"url": "https://example.org"}, {"bbox": [0, 0, 1, 1], "api_key": "query-test-secret"},
                     {"bbox": [0, 0, 1, 1], "revision": 0}):
            with self.subTest(body=body):
                status, result, _ = self.request("POST", "/api/services/adsblol.public/query", body)
                self.assertEqual(status, 400)
                self.assertNotIn("query-test-secret", json.dumps(result))
        self.transport.fetch.assert_not_called()

    def test_explicit_connection_test_requires_current_revision_and_bounded_query(self):
        self.login()
        with mock.patch.object(self.runtime, "execute", return_value={"features": [], "live_tested": True}) as execute:
            for body in ({"revision": 0}, {"revision": 0, "query": {"url": "https://example.org"}},
                         {"revision": 0, "query": {"bbox": [0, 0, 1, 1]}, "url": "https://example.org"}):
                with self.subTest(body=body):
                    self.assertEqual(self.request("POST", "/api/settings/services/adsblol.public/test", body)[0], 400)
            execute.assert_not_called()
            status, result, _ = self.request("POST", "/api/settings/services/adsblol.public/test",
                                            {"revision": 0, "query": {"bbox": [0, 0, 1, 1]}})
            self.assertEqual(status, 200)
            self.assertTrue(result["live_tested"])
            self.assertEqual(execute.call_args.args[0], "adsblol.public")
            self.assertEqual(execute.call_args.args[1].bbox, (0, 0, 1, 1))
        self.assertEqual(self.settings.snapshot()["revision"], 0)

    def test_first_migration_denies_legacy_services_and_environment_openai(self):
        self.login()
        for product in ("overpass.public", "esri.world_imagery", "mapzen.terrarium", "serpapi.free", "serpapi.paid", "openai.api"):
            with self.subTest(product=product):
                self.assertFalse(self.state(product)["effective_enabled"])
                with self.assertRaises(server.ServiceError) as raised:
                    server.require_service(product)
                self.assertEqual(raised.exception.status, 403)
        for revision, product in enumerate(("overpass.public", "esri.world_imagery", "mapzen.terrarium", "serpapi.paid")):
            status, _, _ = self.request("PUT", "/api/settings/services/" + product,
                                        {"revision": revision, "enabled": True, "acknowledged": list(service_registry.get_product(product).acknowledgements)})
            self.assertEqual(status, 200)
            self.assertEqual(self.state(product)["state"], "permission_blocked")
        self.assertEqual(self.state("openai.api")["credentials"], {"configured": True, "source": "environment"})

    def test_serp_policy_denies_cached_response_and_pinned_transport(self):
        cache = server.Cache(Path(":memory:"))
        self.addCleanup(cache.close)
        params = {"engine": "google", "q": "fixture"}
        cache.put_provider_response("serpapi", server.serp_request_key(params), params, {"organic_results": []})
        with mock.patch.object(server, "CACHE", cache), mock.patch("backend.providers.transport.HTTPSPinnedTransport.fetch") as fetch:
            for call in (lambda: server.fetch_serp_response(params),
                         lambda: server.fetch_serp_json("https://serpapi.com/search.json?api_key=never-send-test-secret")):
                with self.assertRaises(server.ServiceError) as raised:
                    call()
                self.assertEqual(raised.exception.status, 403)
            fetch.assert_not_called()
        self.assertEqual(self.runtime.quota.snapshot("serpapi.paid", "local")["usage"], [])

    def test_user_disable_gates_even_existing_runtime_cache(self):
        from backend.providers.query import ProviderQuery
        query = ProviderQuery.from_dict({"bbox": [0, 0, 1, 1]})
        self.assertTrue(self.state("adsblol.public")["effective_enabled"])
        self.runtime._cache[("adsblol.public", query)] = (self.runtime.clock(), {"features": [], "cached": False})
        self.assertTrue(self.runtime.execute("adsblol.public", query)["cached"])
        self.settings.update("adsblol.public", {"enabled": False}, 0)
        # Even a retained/stale cache entry cannot bypass the read-time gate.
        self.runtime._cache[("adsblol.public", query)] = (self.runtime.clock(), {"features": []})
        with self.assertRaises(server.ServiceError) as raised:
            self.runtime.execute("adsblol.public", query)
        self.assertEqual(raised.exception.status, 403)
        self.transport.fetch.assert_not_called()

    def test_openai_environment_requires_opt_in_then_pins_transport_and_honors_disable(self):
        config = replace(server.CONFIG, openai_api_key="", openai_base_url="https://api.openai.com/v1", model_name="fixture-model")
        client = OpenAIChatClient(config, policy_gate=lambda: server.require_service("openai.api"),
                                  credentials=lambda: self.settings.resolve_credentials("openai.api"))
        with mock.patch("backend.providers.transport.HTTPSPinnedTransport.fetch", return_value=b'{"choices":[{"message":{"content":"fixture"}}]}') as fetch:
            self.assertFalse(client.available)
            with self.assertRaises(server.ServiceError):
                client.complete([], [])
            fetch.assert_not_called()
            self.settings.update("openai.api", {"enabled": True, "acknowledged": list(service_registry.get_product("openai.api").acknowledgements)}, 0)
            self.assertTrue(client.available)
            self.assertEqual(client.complete([], []), {"content": "fixture"})
            request = fetch.call_args.args[0]
            self.assertEqual(request.origin, "https://api.openai.com")
            self.assertEqual(request.url, "https://api.openai.com/v1/chat/completions")
            self.assertEqual(request.method, "POST")
            self.assertEqual(dict(request.headers)["Authorization"], "Bearer environment-test-secret")
            self.assertEqual(request.max_decompressed, 2_000_000)
            self.assertNotIn("environment-test-secret", repr(request))
            self.settings.update("openai.api", {"enabled": False}, 1)
            self.assertFalse(client.available)
            with self.assertRaises(server.ServiceError):
                client.complete([], [])
            self.assertEqual(fetch.call_count, 1)

    def test_lazy_foundation_injected_dependencies_use_only_temporary_storage(self):
        from backend.providers import adapters
        factory = mock.Mock(return_value=self.settings)
        with mock.patch.object(server, "SERVICE_SETTINGS", None), mock.patch.object(server, "PROVIDER_RUNTIME", None), \
             mock.patch.object(server, "CONFIG", replace(server.CONFIG, database_path=self.path / "unused.db", openai_base_url="https://unreviewed.example/v1")), \
             mock.patch.dict("os.environ", {"OPENAI_API_KEY": "injected-only"}, clear=True), \
             mock.patch("backend.secret_store.SecretStore", return_value=self.secrets), \
             mock.patch("backend.service_settings.ServiceSettings", factory), \
             mock.patch("backend.providers.runtime.ProviderRuntime", return_value=self.runtime), \
             mock.patch("backend.providers.quota.QuotaStore", return_value=self.runtime.quota):
            self.assertEqual(server.service_foundation(), (self.settings, self.runtime))
            self.assertEqual(server.service_foundation(), (self.settings, self.runtime))
        factory.assert_called_once()
        self.assertEqual(factory.call_args.args[0], self.path / "services.db")
        options = factory.call_args.kwargs
        self.assertIs(options["registry"], service_registry)
        self.assertEqual(options["environment"], {"OPENAI_API_KEY": "injected-only"})
        self.assertFalse(options["dependencies"]["adapter:openai.api"])
        for product, adapter in adapters.ADAPTERS.items():
            if not adapter.blocker:
                self.assertTrue(options["dependencies"]["adapter:" + product])


if __name__ == "__main__":
    unittest.main()
