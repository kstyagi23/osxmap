"""Standalone temporary SQLite/secret-store tests without configured server imports."""

import json
from pathlib import Path
import tempfile
import threading
import unittest

from .secret_store import SecretStore
from .service_settings import RevisionConflict, ServiceSettings, SettingsError
from .test_secret_store import FakeProtector


class Registry:
    ITEMS = [
        {"id": "free.public", "auth_fields": [], "limits": {"requests": 100}, "acknowledgements": [], "billing": False, "default_enabled": True},
        {"id": "paid.key", "auth_fields": ["client_id", "client_secret"], "environment": {"client_id": "CLIENT_ID", "client_secret": "CLIENT_SECRET"}, "limits": {"requests": 10}, "acknowledgements": ["billing"], "billing": True},
        {"id": "blocked.public", "auth_fields": [], "limits": {}, "acknowledgements": [], "billing": False},
    ]

    @classmethod
    def catalogue(cls):
        return json.loads(json.dumps(cls.ITEMS))

    @classmethod
    def get_product(cls, service_id):
        return next((item for item in cls.ITEMS if item["id"] == service_id), None) or (_ for _ in ()).throw(KeyError(service_id))

    @classmethod
    def effective_state(cls, service_id, settings, configured, **_):
        product = cls.get_product(service_id)
        requested = settings["enabled"] if settings["enabled"] is not None else not product["auth_fields"]
        ready = requested and service_id != "blocked.public" and (not product["auth_fields"] or configured and "billing" in settings["acknowledged"])
        return {"requested_enabled": requested, "effective_enabled": ready, "state": "ready" if ready else "disabled", "reasons": []}


class ServiceSettingsTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name)
        self.secrets = SecretStore(self.path / "secrets", protector=FakeProtector(), restrict=lambda _: None)
        self.cancelled = []
        self.settings = self.open_settings()

    def open_settings(self, **kwargs):
        settings = ServiceSettings(self.path / "settings.db", self.secrets, registry=Registry,
                                   cancel=self.cancelled.append, **kwargs)
        self.addCleanup(settings.close)
        return settings

    def service(self, snapshot, service_id):
        return next(service for service in snapshot["services"] if service["id"] == service_id)

    def test_defaults_explicit_enable_and_policy_immutable(self):
        snapshot = self.settings.snapshot()
        self.assertEqual(snapshot["revision"], 0)
        self.assertTrue(self.service(snapshot, "free.public")["effective_enabled"])
        result = self.settings.update("blocked.public", {"enabled": True}, 0)
        self.assertFalse(self.service(result, "blocked.public")["effective_enabled"])
        with self.assertRaises(SettingsError):
            self.settings.update("blocked.public", {"permission": "approved"}, 1)

    def test_secret_redaction_restart_environment_precedence_and_no_autoenable(self):
        secret = {"client_id": "saved-id", "client_secret": "saved-secret"}
        result = self.settings.replace_credentials("paid.key", secret, 0)
        self.assertNotIn("saved-secret", json.dumps(result))
        self.assertNotIn("saved-id", json.dumps(result))
        self.assertNotIn(b"saved-secret", (self.path / "settings.db").read_bytes())
        self.assertEqual(self.service(result, "paid.key")["credentials"], {"configured": True, "source": "saved"})
        self.assertFalse(self.service(result, "paid.key")["effective_enabled"])
        restarted = self.open_settings(environment={"CLIENT_ID": "environment-id"})
        self.assertEqual(restarted.resolve_credentials("paid.key"), {"client_id": "environment-id", "client_secret": "saved-secret"})
        self.assertEqual(restarted.snapshot()["revision"], 1)
        enabled = restarted.update("paid.key", {"enabled": True, "acknowledged": ["billing"]}, 1)
        self.assertTrue(self.service(enabled, "paid.key")["effective_enabled"])
        deleted = restarted.delete_credentials("paid.key", 2)
        self.assertFalse(self.service(deleted, "paid.key")["credentials"]["configured"])
        self.assertEqual(self.cancelled, ["paid.key", "paid.key", "paid.key"])

    def test_strict_validation(self):
        patches = [{"enabled": 1}, {"enabled": None}, {"priority": True}, {"priority": -1}, {"priority": 101},
                   {"acknowledged": ["fake"]}, {"acknowledged": ["billing", "billing"]},
                   {"limits": {"unknown": 1}}, {"limits": {"requests": 11}},
                   {"limits": {"requests": True}}, {"limits": {"requests": float("nan")}},
                   {"allow_overage": 1}, {"allow_overage": True}, {}]
        for patch in patches:
            with self.subTest(patch=patch), self.assertRaises(SettingsError):
                self.settings.update("paid.key", patch, 0)
        self.assertEqual(self.settings.snapshot()["revision"], 0)
        with self.assertRaises(SettingsError):
            self.settings.replace_credentials("paid.key", {"api_key": "wrong"}, 0)
        with self.assertRaises(SettingsError):
            self.settings.update("free.public", {"allow_overage": True}, 0)
        self.settings.update("paid.key", {"allow_overage": True, "acknowledged": ["billing"], "limits": {"requests": 3}, "priority": 100}, 0)

    def test_complete_environment_overrides_corrupt_saved_record(self):
        self.secrets.replace("paid.key", {"client_id": "id", "client_secret": "secret"})
        self.secrets._record_path("paid.key").write_bytes(b"corrupt")
        settings = self.open_settings(environment={"CLIENT_ID": "env-id", "CLIENT_SECRET": "env-secret"})
        self.assertEqual(settings.resolve_credentials("paid.key"),
                         {"client_id": "env-id", "client_secret": "env-secret"})

    def test_cas_across_connections_and_stale_secret_write(self):
        other = self.open_settings()
        self.settings.update("free.public", {"enabled": False}, 0)
        with self.assertRaises(RevisionConflict):
            other.replace_credentials("paid.key", {"client_id": "id", "client_secret": "secret"}, 0)
        self.assertEqual(self.secrets.read("paid.key"), {})
        self.assertEqual(other.snapshot()["revision"], 1)

    def test_concurrent_cas_has_one_winner(self):
        other = self.open_settings()
        barrier = threading.Barrier(2)
        results = []
        def write(settings):
            barrier.wait()
            try:
                settings.update("free.public", {"enabled": False}, 0)
                results.append("saved")
            except RevisionConflict:
                results.append("conflict")
        threads = [threading.Thread(target=write, args=(settings,)) for settings in (self.settings, other)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertCountEqual(results, ["saved", "conflict"])

    def test_corrupt_credentials_safe_and_cancellation_failure_rejects(self):
        self.secrets.replace("paid.key", {"client_id": "id", "client_secret": "secret"})
        self.secrets._record_path("paid.key").write_bytes(b"secret corruption")
        snapshot = self.settings.snapshot()
        self.assertNotIn("secret corruption", json.dumps(snapshot))
        self.assertEqual(self.service(snapshot, "paid.key")["credentials"]["error"], "unavailable")
        def fail(_):
            raise RuntimeError("private details")
        self.settings.cancel = fail
        with self.assertRaises(SettingsError) as error:
            self.settings.delete_credentials("paid.key", 0)
        self.assertNotIn("private", str(error.exception))
        self.assertEqual(self.settings.snapshot()["revision"], 0)

    def test_real_registry_contract_in_isolated_storage(self):
        from . import service_registry
        dependencies = {dependency: True for product in service_registry.PRODUCTS.values()
                        for dependency in product.dependencies}
        settings = ServiceSettings(self.path / "registry.db", self.secrets,
                                   registry=service_registry, dependencies=dependencies,
                                   environment={"OPENAI_API_KEY": "injected-test-only"})
        self.addCleanup(settings.close)
        snapshot = settings.snapshot()
        self.assertTrue(self.service(snapshot, "openfreemap.public")["effective_enabled"])
        self.assertFalse(self.service(snapshot, "esri.world_imagery")["effective_enabled"])
        self.assertFalse(self.service(snapshot, "openai.api")["effective_enabled"])
        self.assertEqual(self.service(snapshot, "openai.api")["credentials"],
                         {"configured": True, "source": "environment"})
        self.assertEqual(settings.resolve_credentials("openai.api"), {"api_key": "injected-test-only"})
        self.assertNotIn("injected-test-only", json.dumps(snapshot))
        product = service_registry.get_product("openweather.basic")
        self.assertTrue(product.auth_fields)
        credentials = {field: "isolated-test-value" for field in product.auth_fields}
        result = settings.replace_credentials("openweather.basic", credentials, 0)
        self.assertTrue(self.service(result, "openweather.basic")["credentials"]["configured"])


if __name__ == "__main__":
    unittest.main()
