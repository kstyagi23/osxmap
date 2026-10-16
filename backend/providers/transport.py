"""HTTPS-only, exact-origin, DNS-pinned transport without environment/proxy imports."""

from dataclasses import dataclass, field
import http.client
import re
import socket
import threading
import time
from urllib.parse import urlsplit
import zlib

from ..errors import ServiceError
from .. import web_sources as web


ALLOWED_ORIGINS = frozenset({"https://api.adsb.lol", "https://celestrak.org", "https://ll.thespacedevs.com",
    "https://api.weather.gov", "https://api.gdeltproject.org", "https://tie.digitraffic.fi",
    "https://cmr.earthdata.nasa.gov", "https://api.openai.com", "https://serpapi.com",
    "https://api.openweathermap.org", "https://api.open-meteo.com",
    "https://air-quality-api.open-meteo.com", "https://api.rainviewer.com",
    "https://api.entur.io", "https://gtfsrt.api.translink.com.au", "https://stac.dataspace.copernicus.eu"})


@dataclass(frozen=True)
class Request:
    url: str = field(repr=False)
    origin: str
    headers: tuple = field(default=(), repr=False)
    max_compressed: int = 2 * 1024 * 1024
    max_decompressed: int = 4 * 1024 * 1024
    timeout: float = 20
    method: str = "GET"
    body: bytes | None = field(default=None, repr=False)
    media_types: tuple[str, ...] = ("application/json", "application/geo+json")


def validate_origin_url(url, origin):
    """Origin is supplied by a fixed adapter, never by a user query."""
    try:
        if (not isinstance(url, str) or len(url) > 2048 or any(c.isspace() or ord(c) < 32 or c in "\\\x7f" for c in url)):
            raise ValueError
        if origin not in ALLOWED_ORIGINS:
            raise ValueError
        parts, allowed = urlsplit(url), urlsplit(origin)
        if (parts.scheme != "https" or parts.username is not None or parts.password is not None
                or "@" in parts.netloc or parts.port not in {None, 443} or parts.fragment
                or allowed.scheme != "https" or allowed.path or allowed.query or allowed.fragment
                or allowed.username is not None or allowed.port not in {None, 443}
                or parts.hostname != allowed.hostname or not parts.hostname
                or parts.netloc not in {parts.hostname, parts.hostname + ":443"}):
            raise ValueError
        # Validate public hostname syntax independently of private credential query values.
        web.validate_web_url("https://" + parts.hostname + (parts.path or "/"))
        return parts
    except (ValueError, TypeError, ServiceError):
        raise ServiceError("Provider origin is not allowed.", 400) from None


class HTTPSPinnedTransport:
    """No redirects, cookies, proxies, retries, or credential-bearing diagnostics.

    One numeric sockaddr is resolved and validated before TLS with the original SNI.
    Identity and a single gzip member are supported, with independent wire/output caps.
    Cancellation aborts the socket; request outcome may still be billable.
    """

    def fetch(self, request, cancel=None):
        if not isinstance(request, Request):
            raise ServiceError("Invalid provider request.", 400)
        parts = validate_origin_url(request.url, request.origin)
        allowed_media = {"application/json", "application/geo+json"}
        if request.origin in {"https://api.entur.io", "https://gtfsrt.api.translink.com.au"}:
            allowed_media.update({"application/protobuf", "application/x-protobuf", "application/vnd.google.protobuf", "application/octet-stream"})
        if not request.media_types or not set(request.media_types) <= allowed_media:
            raise ServiceError("Unreviewed provider response format.", 400)
        if (type(request.max_compressed) is not int or not 0 < request.max_compressed <= 8 * 1024 * 1024
                or type(request.max_decompressed) is not int or not 0 < request.max_decompressed <= 16 * 1024 * 1024
                or type(request.timeout) not in {int, float} or not 0 < request.timeout <= 60):
            raise ServiceError("Invalid provider transport bounds.", 400)
        if (request.method not in {"GET", "POST"} or request.method == "GET" and request.body is not None
                or request.method == "POST" and (not isinstance(request.body, bytes) or not 1 <= len(request.body) <= 512 * 1024)):
            raise ServiceError("Invalid provider method or body bound.", 400)
        headers = {"User-Agent": "Meridian/provider-reader", "Accept": "application/json, application/geo+json",
                   "Accept-Encoding": "gzip, identity"}
        for key, value in request.headers:
            if (key not in {"Authorization", "X-API-Key", "ET-Client-Name", "Digitraffic-User", "User-Agent", "Accept", "Content-Type"}
                    or not isinstance(value, str) or not 1 <= len(value) <= 1024
                    or any(ord(c) < 32 or ord(c) == 127 for c in value) or key in headers and key != "Accept" and key != "User-Agent"):
                raise ServiceError("Invalid provider headers.", 400)
            headers[key] = value
        if request.method == "POST":
            if headers.get("Content-Type", "application/json") != "application/json":
                raise ServiceError("Provider POST requires JSON content type.", 400)
            headers["Content-Type"] = "application/json"
        deadline = time.monotonic() + request.timeout
        if cancel is not None and cancel.is_set():
            raise ServiceError("Provider request cancelled.", 499)
        address = web._resolve_public(parts.hostname, 443, deadline)
        connection = web._PinnedHTTPSConnection(parts.hostname, 443, address, deadline)
        done = threading.Event()

        def abort_on_cancel():
            while not done.wait(0.05):
                if cancel is not None and cancel.is_set():
                    web._abort_connection(connection)
                    return

        timer = threading.Timer(web._time_left(deadline, request.timeout),
                                web._abort_connection, args=(connection,))
        timer.daemon = True
        timer.start()
        if cancel is not None:
            threading.Thread(target=abort_on_cancel, daemon=True).start()
        response = None
        try:
            if cancel is not None and cancel.is_set():
                raise ServiceError("Provider request cancelled.", 499)
            connection.request(request.method, (parts.path or "/") + ("?" + parts.query if parts.query else ""),
                               body=request.body, headers=headers)
            response = connection.getresponse()
            web._time_left(deadline)
            if response.status in {301, 302, 303, 307, 308}:
                raise ServiceError("Provider redirects are refused.", 502)
            if response.status == 429 or response.status == 503:
                retry = response.getheader("Retry-After", "60")
                retry = min(3600, max(1, int(retry))) if re.fullmatch(r"[0-9]{1,8}", retry) else 60
                raise ServiceError("Provider is throttled or unavailable.", response.status, retry)
            if not 200 <= response.status < 300 or response.status in {204, 206}:
                raise ServiceError("Provider request failed.", 502)
            media = response.getheader("Content-Type", "").split(";", 1)[0].strip().lower()
            if media not in request.media_types:
                raise ServiceError("Provider response format is unsupported.", 415)
            encoding = response.getheader("Content-Encoding", "identity").strip().lower()
            if encoding not in {"", "identity", "gzip"}:
                raise ServiceError("Provider compression is unsupported.", 415)
            length = response.getheader("Content-Length")
            if length is not None and (not re.fullmatch(r"[0-9]{1,12}", length.strip()) or int(length) > request.max_compressed):
                raise ServiceError("Provider wire byte limit exceeded or invalid length.", 413)
            decoder = zlib.decompressobj(16 + zlib.MAX_WBITS) if encoding == "gzip" else None
            chunks, wire, decoded = [], 0, 0
            while True:
                if cancel is not None and cancel.is_set():
                    raise ServiceError("Provider request cancelled.", 499)
                if connection._transport_socket is not None:
                    connection._transport_socket.settimeout(web._time_left(deadline))
                chunk = response.read1(min(65536, request.max_compressed + 1 - wire))
                web._time_left(deadline)
                if not chunk:
                    break
                wire += len(chunk)
                if wire > request.max_compressed:
                    raise ServiceError("Provider wire byte limit exceeded.", 413)
                output = decoder.decompress(chunk, request.max_decompressed + 1 - decoded) if decoder else chunk
                decoded += len(output)
                if decoded > request.max_decompressed or decoder and decoder.unconsumed_tail:
                    raise ServiceError("Provider decoded byte limit exceeded.", 413)
                chunks.append(output)
            if length is not None and wire != int(length):
                raise ServiceError("Provider response is incomplete.", 502)
            if decoder and (not decoder.eof or decoder.unused_data):
                raise ServiceError("Provider gzip is incomplete or has trailing members.", 422)
            return b"".join(chunks)
        except (OSError, http.client.HTTPException, zlib.error, ValueError):
            if cancel is not None and cancel.is_set():
                raise ServiceError("Provider request cancelled.", 499) from None
            if time.monotonic() >= deadline:
                raise ServiceError("Provider request timed out.", 504) from None
            raise ServiceError("Provider transport failed.", 502) from None
        finally:
            done.set()
            timer.cancel()
            if response is not None:
                response.close()
            connection.close()
