"""Standalone revisioned settings. Reviewed policy remains owned by the registry."""

import json
import math
from pathlib import Path
import sqlite3
import threading

from .secret_store import SecretStoreError


class SettingsError(ValueError):
    pass


class RevisionConflict(SettingsError):
    pass


class ServiceSettings:
    VERSION = 1
    FIELDS = frozenset({"enabled", "acknowledged", "limits", "priority", "allow_overage"})

    def __init__(self, path, secret_store, *, registry=None, environment=None,
                 cancel=None, renderer="maplibre", dependencies=None):
        if registry is None:
            from . import service_registry as registry
        self.registry = registry
        self.secret_store = secret_store
        # The caller supplies already-resolved process/backend/root environment values.
        # This module never loads config, .env files, or process environment itself.
        self.environment = dict(environment or {})
        self.cancel = cancel
        self.renderer = renderer
        self.dependencies = dependencies
        self._lock = threading.RLock()
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self._db.execute("PRAGMA busy_timeout=5000")
        self._db.execute("CREATE TABLE IF NOT EXISTS service_settings_meta (singleton INTEGER PRIMARY KEY CHECK(singleton=1), version INTEGER NOT NULL, revision INTEGER NOT NULL)")
        self._db.execute("INSERT OR IGNORE INTO service_settings_meta VALUES (1, 1, 0)")
        self._db.execute("CREATE TABLE IF NOT EXISTS service_settings (id TEXT PRIMARY KEY, settings TEXT NOT NULL)")
        if self._db.execute("SELECT version FROM service_settings_meta WHERE singleton=1").fetchone()[0] != self.VERSION:
            self._db.close()
            raise SettingsError("Unsupported settings storage version")

    def close(self):
        with self._lock:
            self._db.close()

    def _product(self, service_id):
        try:
            return self.registry.get_product(service_id)
        except (KeyError, TypeError, ValueError):
            raise SettingsError("Unknown service") from None

    def _metadata(self, service_id):
        self._product(service_id)
        for item in self.registry.catalogue():
            if item["id"] == service_id:
                item = dict(item)
                item["limits"] = {name: value for name, value in dict(item.get("limits", {})).items()
                                  if type(value) in (int, float)}
                return item
        raise SettingsError("Unknown service")

    def _defaults(self, metadata):
        return {"enabled": metadata.get("default_enabled", False) is True, "acknowledged": [], "limits": dict(metadata.get("limits", {})),
                "priority": 0, "allow_overage": False}

    def _settings(self, service_id, metadata):
        value = self._defaults(metadata)
        row = self._db.execute("SELECT settings FROM service_settings WHERE id=?", (service_id,)).fetchone()
        if row:
            try:
                stored = json.loads(row[0])
                self._validate(stored, metadata)
                value.update(stored)
            except (ValueError, TypeError):
                raise SettingsError("Stored service settings are corrupt") from None
        return value

    def _validate(self, patch, metadata):
        if not isinstance(patch, dict) or not patch or not set(patch) <= self.FIELDS:
            raise SettingsError("Unknown or empty settings fields")
        if "enabled" in patch and type(patch["enabled"]) is not bool:
            raise SettingsError("Enabled must be a boolean")
        if "acknowledged" in patch:
            values = patch["acknowledged"]
            allowed = metadata.get("acknowledgements", [])
            if not isinstance(values, list) or len(values) > 16 or any(not isinstance(value, str) or value not in allowed for value in values) or len(set(values)) != len(values):
                raise SettingsError("Invalid acknowledgements")
        if "priority" in patch and (type(patch["priority"]) is not int or not 0 <= patch["priority"] <= 100):
            raise SettingsError("Priority must be an integer from 0 to 100")
        if "allow_overage" in patch:
            if type(patch["allow_overage"]) is not bool or (patch["allow_overage"] and not metadata.get("billing", False)):
                raise SettingsError("Invalid overage setting")
        if "limits" in patch:
            limits = patch["limits"]
            if not isinstance(limits, dict) or not set(limits) <= set(metadata.get("limits", {})):
                raise SettingsError("Unknown product limits")
            for name, value in limits.items():
                if type(value) not in (int, float) or not math.isfinite(value) or value < 0 or value > metadata["limits"][name]:
                    raise SettingsError("Product limits must not exceed reviewed ceilings")

    def _environment_credentials(self, service_id, metadata):
        fields = metadata.get("auth_fields", [])
        direct = self.environment.get(service_id, {})
        names = metadata.get("environment", {})
        values = {}
        for field in fields:
            value = direct.get(field) if isinstance(direct, dict) else None
            if not value:
                value = self.environment.get(names.get(field, ""))
            if isinstance(value, str) and value.strip():
                values[field] = value
        return values

    def resolve_credentials(self, service_id):
        """Backend-only. Never include the returned values in an HTTP response."""
        with self._lock:
            metadata = self._metadata(service_id)
            environment = self._environment_credentials(service_id, metadata)
            fields = metadata.get("auth_fields", [])
            if fields and all(environment.get(field) for field in fields):
                return environment
            saved = self.secret_store.read(service_id)
            values = {field: value for field, value in saved.items() if field in metadata.get("auth_fields", [])}
            values.update(environment)
            return values

    def _credential_state(self, service_id, metadata):
        environment = self._environment_credentials(service_id, metadata)
        error = None
        try:
            values = self.secret_store.read(service_id)
        except SecretStoreError:
            values = {}
            error = "unavailable"
        saved = bool(values)
        values.update(environment)
        required = metadata.get("auth_fields", [])
        configured = bool(required) and all(values.get(field) for field in required)
        state = {"configured": configured, "source": "environment" if environment else "saved" if saved else "none"}
        if error:
            state["error"] = error
        return state

    def _snapshot(self):
        revision = self._db.execute("SELECT revision FROM service_settings_meta WHERE singleton=1").fetchone()[0]
        services = []
        for metadata in self.registry.catalogue():
            service_id = metadata["id"]
            metadata = dict(metadata)
            metadata["limits"] = {name: value for name, value in dict(metadata.get("limits", {})).items()
                                  if type(value) in (int, float)}
            settings = self._settings(service_id, metadata)
            credentials = self._credential_state(service_id, metadata)
            state = self.registry.effective_state(service_id, settings, credentials["configured"],
                                                  renderer=self.renderer, dependencies=self.dependencies)
            services.append({"id": service_id, **settings, **state, "credentials": credentials})
        return {"version": self.VERSION, "revision": revision, "services": services}

    def snapshot(self):
        with self._lock:
            self._db.execute("BEGIN")
            try:
                result = self._snapshot()
                self._db.execute("COMMIT")
                return result
            except Exception:
                self._db.execute("ROLLBACK")
                raise

    def _mutate(self, service_id, expected_revision, operation):
        if type(expected_revision) is not int or expected_revision < 0:
            raise SettingsError("A valid revision is required")
        with self._lock:
            metadata = self._metadata(service_id)
            self._db.execute("BEGIN IMMEDIATE")
            try:
                revision = self._db.execute("SELECT revision FROM service_settings_meta WHERE singleton=1").fetchone()[0]
                if revision != expected_revision:
                    raise RevisionConflict("Settings revision has changed")
                # Validate the redacted snapshot before any external secret-store mutation.
                self._snapshot()
                operation(metadata)
                self._db.execute("UPDATE service_settings_meta SET revision=revision+1 WHERE singleton=1 AND revision=?", (expected_revision,))
                self._db.execute("COMMIT")
            except Exception:
                self._db.execute("ROLLBACK")
                raise
            return self.snapshot()

    def _cancel(self, service_id):
        if self.cancel is not None:
            try:
                self.cancel(service_id)
            except Exception:
                raise SettingsError("Cannot cancel active service work") from None

    def update(self, service_id, patch, expected_revision):
        def operation(metadata):
            self._validate(patch, metadata)
            settings = self._settings(service_id, metadata)
            previous_limits = settings["limits"]
            settings.update(patch)
            if "limits" in patch:
                settings["limits"] = {**previous_limits, **settings["limits"]}
            if settings["allow_overage"] and "billing" not in settings["acknowledged"]:
                raise SettingsError("Overage requires a billing acknowledgement")
            self._cancel(service_id)
            self._db.execute("INSERT INTO service_settings(id,settings) VALUES (?,?) ON CONFLICT(id) DO UPDATE SET settings=excluded.settings", (service_id, json.dumps(settings, separators=(",", ":"))))
        return self._mutate(service_id, expected_revision, operation)

    def replace_credentials(self, service_id, credentials, expected_revision):
        def operation(metadata):
            fields = metadata.get("auth_fields", [])
            if not isinstance(credentials, dict) or not fields or set(credentials) != set(fields):
                raise SettingsError("Credentials must match the product authentication schema")
            self.secret_store._validate(credentials)
            self._cancel(service_id)
            self.secret_store.replace(service_id, credentials)
        return self._mutate(service_id, expected_revision, operation)

    def delete_credentials(self, service_id, expected_revision):
        def operation(metadata):
            self._cancel(service_id)
            self.secret_store.delete(service_id)
        return self._mutate(service_id, expected_revision, operation)
