"""Loopback-only browser boundary for the local credential broker."""
import secrets
import threading
import time
from http.cookies import SimpleCookie
from urllib.parse import urlsplit


class BrokerError(ValueError):
    def __init__(self, message, status=403):
        super().__init__(message)
        self.status = status


class LocalBroker:
    def __init__(self, port, trusted_origins=()):
        self.hosts = {f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"}
        self.origins = {f"http://{host}" for host in self.hosts}
        for origin in trusted_origins:
            parsed = urlsplit(origin)
            if (parsed.scheme not in {"http", "https"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
                    or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment):
                raise ValueError("Settings UI origins must be exact loopback origins")
            self.origins.add(origin)
        self._sessions = {}
        self._lock = threading.Lock()

    def validate(self, headers, mutation=False):
        if headers.get("Host", "").lower() not in self.hosts:
            raise BrokerError("Untrusted local Host header")
        origin = headers.get("Origin", "")
        if origin and origin not in self.origins:
            raise BrokerError("Untrusted Settings origin")
        if headers.get("Sec-Fetch-Site", "") == "cross-site":
            raise BrokerError("Cross-site Settings access is not permitted")
        if mutation:
            if not origin or origin not in self.origins:
                raise BrokerError("Settings mutations require a trusted Origin")
            if headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
                raise BrokerError("Settings mutations require application/json", 415)
            with self._lock:
                token, expires = self._sessions.get(self._session(headers), ("", 0))
            if not token or expires <= time.monotonic() or not secrets.compare_digest(token, headers.get("X-Meridian-CSRF", "")):
                raise BrokerError("Settings session or CSRF token is invalid")
        return origin

    @staticmethod
    def _session(headers):
        try:
            cookies = SimpleCookie(headers.get("Cookie", ""))
            return cookies["meridian_settings"].value if "meridian_settings" in cookies else ""
        except Exception:
            return ""

    def session(self, headers):
        self.validate(headers)
        now = time.monotonic()
        session = self._session(headers)
        with self._lock:
            self._sessions = {key: value for key, value in self._sessions.items() if value[1] > now}
            if session not in self._sessions:
                if len(self._sessions) >= 128:
                    raise BrokerError("Too many local Settings sessions", 503)
                session = secrets.token_urlsafe(32)
                self._sessions[session] = (secrets.token_urlsafe(32), now + 3600)
            token = self._sessions[session][0]
        return token, f"meridian_settings={session}; HttpOnly; SameSite=Strict; Path=/api/; Max-Age=3600"
