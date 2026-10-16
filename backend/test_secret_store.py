"""No real credentials or production storage; fake protection unless explicitly tested."""

import json
import os
from pathlib import Path
import tempfile
import unittest

from .secret_store import DPAPIProtector, ProtectionUnavailable, SecretCorruptionError, SecretStore, SecretStoreError


class FakeProtector:
    def protect(self, value):
        return bytes(byte ^ 0xA5 for byte in value)

    def unprotect(self, value):
        return self.protect(value)


class SecretStoreTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "secrets"
        self.restricted = []
        self.store = SecretStore(self.path, protector=FakeProtector(), restrict=self.restricted.append)

    def test_replace_restart_delete_and_no_plaintext(self):
        self.assertEqual(self.store.read("provider.key"), {})
        self.store.replace("provider.key", {"api_key": "private-value-123"})
        records = list(self.path.iterdir())
        self.assertEqual(len(records), 1)
        self.assertNotIn(b"private-value-123", records[0].read_bytes())
        self.assertNotIn(b"api_key", records[0].read_bytes())
        self.assertEqual(set(json.loads(records[0].read_bytes())), {"version", "encrypted"})
        self.assertEqual(len(self.restricted), 2)
        restarted = SecretStore(self.path, protector=FakeProtector(), restrict=lambda _: None)
        self.assertEqual(restarted.read("provider.key"), {"api_key": "private-value-123"})
        restarted.replace("provider.key", {"api_key": "replacement"})
        self.assertEqual(restarted.read("provider.key"), {"api_key": "replacement"})
        restarted.delete("provider.key")
        restarted.delete("provider.key")
        self.assertEqual(restarted.read("provider.key"), {})

    def test_corruption_and_wrong_record_do_not_leak(self):
        self.store.replace("provider.key", {"api_key": "secret"})
        path = self.store._record_path("provider.key")
        path.write_bytes(b"secret malformed")
        with self.assertRaises(SecretCorruptionError) as error:
            self.store.read("provider.key")
        self.assertNotIn("secret", str(error.exception).lower())
        self.store.replace("provider.key", {"api_key": "secret"})
        path.replace(self.store._record_path("different.key"))
        with self.assertRaises(SecretCorruptionError):
            self.store.read("different.key")

    def test_failure_keeps_previous_record_and_cleans_temporary(self):
        self.store.replace("provider.key", {"api_key": "old"})
        def reject(_):
            raise OSError("secret exception details")
        self.store.restrict = reject
        with self.assertRaises(SecretStoreError) as error:
            self.store.replace("provider.key", {"api_key": "new"})
        self.assertNotIn("exception details", str(error.exception))
        self.assertEqual(self.store.read("provider.key"), {"api_key": "old"})
        self.assertEqual(len(list(self.path.iterdir())), 1)

    def test_unavailable_protection_never_persists(self):
        class Unavailable:
            def protect(self, _):
                raise ProtectionUnavailable("Unavailable")
        store = SecretStore(self.path, protector=Unavailable(), restrict=lambda _: None)
        with self.assertRaises(ProtectionUnavailable):
            store.replace("provider.key", {"api_key": "secret"})
        self.assertFalse(self.path.exists())

    def test_decrypt_failure_safe_and_temporary_acl_failure_cleans_up(self):
        self.store.replace("provider.key", {"api_key": "old"})
        class Broken(FakeProtector):
            def unprotect(self, _):
                raise RuntimeError("private secret details")
        reader = SecretStore(self.path, protector=Broken(), restrict=lambda _: None)
        with self.assertRaises(SecretCorruptionError) as error:
            reader.read("provider.key")
        self.assertNotIn("private", str(error.exception))
        def reject_file(path):
            if Path(path) != self.path:
                raise OSError("Cannot apply ACL")
        self.store.restrict = reject_file
        with self.assertRaises(SecretStoreError):
            self.store.replace("provider.key", {"api_key": "new"})
        self.assertEqual(self.store.read("provider.key"), {"api_key": "old"})
        self.assertEqual(len(list(self.path.iterdir())), 1)

    def test_strict_credentials_and_traversal_safe_ids(self):
        for credentials in ({}, {"api_key": ""}, {"api_key": "line\nbreak"}, {"api_key": 1}):
            with self.assertRaises(SecretStoreError):
                self.store.replace("provider.key", credentials)
        self.store.replace("../../elsewhere", {"api_key": "secret"})
        self.assertEqual(self.store._record_path("../../elsewhere").parent, self.path)

    @unittest.skipUnless(os.name == "nt", "Windows-only current-user DPAPI")
    def test_current_user_dpapi_temporary_roundtrip(self):
        store = SecretStore(self.path)
        store.replace("isolated.test", {"api_key": "isolated-not-real"})
        self.assertEqual(store.read("isolated.test"), {"api_key": "isolated-not-real"})
        self.assertNotIn(b"isolated-not-real", store._record_path("isolated.test").read_bytes())
        store.delete("isolated.test")


if __name__ == "__main__":
    unittest.main()
