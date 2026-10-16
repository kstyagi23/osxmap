"""Explicit-path, current-user encrypted credential storage; no import-time I/O."""

import base64
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading


class SecretStoreError(RuntimeError):
    """Safe error suitable for a redacted broker response."""


class ProtectionUnavailable(SecretStoreError):
    pass


class SecretCorruptionError(SecretStoreError):
    pass


class DPAPIProtector:
    """Windows DPAPI with UI forbidden and without machine-wide protection."""

    def _crypt(self, value, decrypt=False):
        if os.name != "nt":
            raise ProtectionUnavailable("Current-user OS protection is unavailable")

        class Blob(ctypes.Structure):
            _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]

        crypt = ctypes.WinDLL("crypt32", use_last_error=True)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.LocalFree.argtypes = [ctypes.c_void_p]
        kernel.LocalFree.restype = ctypes.c_void_p
        buffer = ctypes.create_string_buffer(value)
        source = Blob(len(value), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
        target = Blob()
        function = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
        function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                             ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
        function.restype = wintypes.BOOL
        if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
            raise SecretStoreError("OS credential protection failed")
        try:
            return ctypes.string_at(target.data, target.size)
        finally:
            kernel.LocalFree(target.data)

    def protect(self, value):
        return self._crypt(value)

    def unprotect(self, value):
        return self._crypt(value, decrypt=True)


def restrict_current_user(path):
    """Replace inherited ACLs with a protected owner-only full-control DACL."""
    if os.name != "nt":
        raise ProtectionUnavailable("Restrictive Windows storage permissions are unavailable")
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    descriptor = ctypes.c_void_p()
    advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p]
    advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.restype = wintypes.BOOL
    advapi.SetFileSecurityW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_void_p]
    advapi.SetFileSecurityW.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    advapi.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
    advapi.GetTokenInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    advapi.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
    token = wintypes.HANDLE()
    if not advapi.OpenProcessToken(kernel.GetCurrentProcess(), 8, ctypes.byref(token)):
        raise SecretStoreError("Cannot secure credential storage")
    sid_text = ctypes.c_void_p()
    try:
        size = wintypes.DWORD()
        advapi.GetTokenInformation(token, 1, None, 0, ctypes.byref(size))
        info = ctypes.create_string_buffer(size.value)
        if not advapi.GetTokenInformation(token, 1, info, size, ctypes.byref(size)):
            raise SecretStoreError("Cannot secure credential storage")
        sid = ctypes.cast(info, ctypes.POINTER(ctypes.c_void_p))[0]
        if not advapi.ConvertSidToStringSidW(sid, ctypes.byref(sid_text)):
            raise SecretStoreError("Cannot secure credential storage")
        user_sid = ctypes.wstring_at(sid_text)
    finally:
        if sid_text.value:
            kernel.LocalFree(sid_text)
        kernel.CloseHandle(token)
    if not advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW(
            "D:P(A;OICI;FA;;;" + user_sid + ")", 1, ctypes.byref(descriptor), None):
        raise SecretStoreError("Cannot secure credential storage")
    try:
        if not advapi.SetFileSecurityW(str(path), 0x80000004, descriptor):
            raise SecretStoreError("Cannot secure credential storage")
    finally:
        kernel.LocalFree(descriptor)


class SecretStore:
    VERSION = 1
    MAX_RECORD_BYTES = 65536

    def __init__(self, path, *, protector=None, restrict=None):
        self.path = Path(path)
        self.protector = protector if protector is not None else DPAPIProtector()
        self.restrict = restrict if restrict is not None else restrict_current_user
        self._lock = threading.RLock()

    def _record_path(self, service_id):
        if not isinstance(service_id, str) or not service_id or len(service_id) > 160:
            raise SecretStoreError("Invalid credential record identifier")
        return self.path / (hashlib.sha256(service_id.encode("utf-8")).hexdigest() + ".json")

    def read(self, service_id):
        """Backend-only credential values, or an empty mapping for a missing record."""
        with self._lock:
            path = self._record_path(service_id)
            try:
                with path.open("rb") as record:
                    raw = record.read(self.MAX_RECORD_BYTES + 1)
            except FileNotFoundError:
                return {}
            except OSError:
                raise SecretStoreError("Cannot read credential storage") from None
            try:
                if len(raw) > self.MAX_RECORD_BYTES:
                    raise ValueError()
                outer = json.loads(raw)
                if set(outer) != {"version", "encrypted"} or type(outer["version"]) is not int or outer["version"] != self.VERSION:
                    raise ValueError()
                encrypted = base64.b64decode(outer["encrypted"], validate=True)
                inner = json.loads(self.protector.unprotect(encrypted))
                if set(inner) != {"version", "id", "credentials"} or type(inner["version"]) is not int or inner["version"] != self.VERSION or inner["id"] != service_id:
                    raise ValueError()
                self._validate(inner["credentials"])
                return dict(inner["credentials"])
            except Exception:
                raise SecretCorruptionError("Credential record is corrupt or cannot be decrypted") from None

    @staticmethod
    def _validate(credentials):
        if not isinstance(credentials, dict) or not credentials or len(credentials) > 16:
            raise SecretStoreError("Invalid credentials")
        for name, value in credentials.items():
            if not isinstance(name, str) or not name or len(name) > 80 or not isinstance(value, str) or not value.strip() or len(value) > 8192 or any(ord(c) < 32 for c in value):
                raise SecretStoreError("Invalid credentials")

    def replace(self, service_id, credentials):
        with self._lock:
            target = self._record_path(service_id)
            self._validate(credentials)
            temporary = None
            try:
                clear = json.dumps({"version": self.VERSION, "id": service_id, "credentials": credentials}, separators=(",", ":")).encode("utf-8")
                protected = self.protector.protect(clear)
                record = json.dumps({"version": self.VERSION, "encrypted": base64.b64encode(protected).decode("ascii")}, separators=(",", ":")).encode("ascii")
                if len(record) > self.MAX_RECORD_BYTES:
                    raise SecretStoreError("Credential record is too large")
                self.path.mkdir(parents=True, exist_ok=True)
                self.restrict(self.path)
                descriptor, temporary = tempfile.mkstemp(prefix=".secret-", dir=self.path)
                with os.fdopen(descriptor, "wb") as output:
                    self.restrict(temporary)
                    output.write(record)
                    output.flush()
                    os.fsync(output.fileno())
                os.replace(temporary, target)
                temporary = None
            except ProtectionUnavailable:
                raise
            except Exception:
                raise SecretStoreError("Cannot persist protected credentials") from None
            finally:
                if temporary is not None:
                    try:
                        os.unlink(temporary)
                    except OSError:
                        pass

    def delete(self, service_id):
        with self._lock:
            try:
                self._record_path(service_id).unlink(missing_ok=True)
            except OSError:
                raise SecretStoreError("Cannot delete credential record") from None
