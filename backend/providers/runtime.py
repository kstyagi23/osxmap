"""Bounded admission, singleflight, policy gates and memory-only freshness cache."""

from collections import OrderedDict
from copy import deepcopy
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
import threading
import time

from ..errors import ServiceError
from .. import web_sources as web
from .adapters import ADAPTERS
from .query import ProviderQuery
from .transport import HTTPSPinnedTransport
from .quota import QuotaRule


@dataclass
class _Flight:
    done: threading.Event = field(default_factory=threading.Event)
    cancel: threading.Event = field(default_factory=threading.Event)
    result: dict | None = None
    error: Exception | None = None
    waiters: int = 0


class ProviderRuntime:
    """Policy must be injected and affirmatively approve every read/dispatch/return.

    A cancelled caller detaches; shared work continues for remaining consumers.
    Last-consumer cancellation or disable aborts transport, without quota refund.
    No background refresh, disk feed cache, stored credentials, or configured server import.
    """

    def __init__(self, quota_store, *, policy_gate, transport=None, workers=4, max_waiters=32,
                 cache_entries=32, account="public", clock=time.monotonic, credentials=None, adapters=None):
        if not callable(policy_gate) or type(workers) is not int or not 1 <= workers <= 16 or type(max_waiters) is not int or not workers <= max_waiters <= 128 or type(cache_entries) is not int or not 0 <= cache_entries <= 128:
            raise ValueError("Invalid provider runtime configuration")
        if credentials is not None and not callable(credentials):
            raise ValueError("Credentials must be an injected callback")
        self.quota, self.policy_gate = quota_store, policy_gate
        self.credentials = credentials
        self.adapters = ADAPTERS if adapters is None else dict(adapters)
        self.transport = transport or HTTPSPinnedTransport()
        self.account, self.clock = account, clock
        self._lock = threading.RLock()
        self._slots = threading.BoundedSemaphore(workers)
        self._admission = threading.BoundedSemaphore(max_waiters)
        self._cache, self._flights, self._backoff = OrderedDict(), {}, {}
        self.cache_entries = cache_entries

    def _gate(self, provider, query):
        decision = self.policy_gate(provider, query)
        allowed = decision is True or isinstance(decision, dict) and decision.get("effective_enabled") is True
        if not allowed:
            raise ServiceError("Provider is disabled or blocked by current policy.", 403)
        return decision

    def _credentials(self, adapter):
        if not adapter.requires_credentials:
            return None  # Public/NC adapters never receive arbitrary authorization.
        try:
            values = self.credentials(adapter.id) if self.credentials is not None else None
        except Exception:
            raise ServiceError("Provider credentials could not be resolved.", 409) from None
        return {"api_key": values.get("api_key")} if isinstance(values, dict) else None

    @staticmethod
    def _delivery(result, adapter):
        if getattr(adapter, 'format', 'json') != 'protobuf':
            return result
        now = time.time()
        if result.get('feed_timestamp'):
            result['feed_age_seconds'] = now - datetime.fromisoformat(result['feed_timestamp'].replace('Z', '+00:00')).timestamp()
        for row in [*result.get('records', []), *[feature.get('properties', {}) for feature in result.get('features', [])]]:
            if row.get('observed_at'):
                row['age_seconds'] = now - datetime.fromisoformat(row['observed_at'].replace('Z', '+00:00')).timestamp()
                row['stale'] = row['age_seconds'] > adapter.stale_after
        if (result.get('feed_age_seconds') is not None and result['feed_age_seconds'] > adapter.stale_after
                or any(row.get('stale') for row in result.get('records', []))
                or any(feature.get('properties', {}).get('stale') for feature in result.get('features', []))):
            result.update(state='stale', stale=True)
        return result

    def cancel_provider(self, provider):
        with self._lock:
            for key, flight in self._flights.items():
                if key[0] == provider:
                    flight.cancel.set()
            for key in list(self._cache):
                if key[0] == provider:
                    del self._cache[key]

    def close(self, timeout=5):
        """Cancel work and wait boundedly for ledger finalization/socket cleanup."""
        with self._lock:
            flights = list(self._flights.values())
            for flight in flights:
                flight.cancel.set()
            self._cache.clear()
        deadline = time.monotonic() + min(60, max(0, timeout))
        for flight in flights:
            flight.done.wait(max(0, deadline - time.monotonic()))

    def status(self, provider):
        adapter = self.adapters.get(provider)
        if adapter is None:
            raise ServiceError("Unsupported provider ID.", 404)
        return {"provider_id": provider, "state": "needs_setup" if adapter.blocker else "ready",
                "reason": adapter.blocker, "coverage": adapter.coverage,
                "quota": self.quota.snapshot(provider, self.account), "live_tested": False}

    def execute(self, provider_id, query, cancel=None):
        if not isinstance(provider_id, str) or provider_id not in self.adapters:
            raise ServiceError("Unsupported provider ID.", 404)
        if not isinstance(query, ProviderQuery):
            raise ServiceError("Expected a typed ProviderQuery.", 400)
        adapter = self.adapters[provider_id]
        self._gate(provider_id, query)
        if adapter.blocker:
            raise ServiceError(adapter.blocker, 409)
        adapter.request(query, credentials=self._credentials(adapter))  # Validate before charging/admission.
        if cancel is not None and cancel.is_set():
            raise ServiceError("Provider request cancelled.", 499)
        if not self._admission.acquire(blocking=False):
            raise ServiceError("Provider admission is full.", 503, 1)
        key, flight = (provider_id, query), None
        try:
            with self._lock:
                cached = self._cache.get(key)
                if not adapter.requires_credentials and cached and self.clock() - cached[0] <= adapter.ttl:
                    self._cache.move_to_end(key)
                    result = deepcopy(cached[1])
                    result["cached"] = True
                    return self._delivery(result, adapter)
                flight = self._flights.get(key)
                if flight is None:
                    flight = _Flight()
                    self._flights[key] = flight
                    threading.Thread(target=self._run, args=(key, flight, adapter), daemon=True).start()
                flight.waiters += 1
            while not flight.done.wait(0.05):
                if cancel is not None and cancel.is_set():
                    raise ServiceError("Provider request cancelled.", 499)
            if cancel is not None and cancel.is_set():
                raise ServiceError("Provider request cancelled.", 499)
            self._gate(provider_id, query)
            if flight.error:
                raise flight.error
            return self._delivery(deepcopy(flight.result), adapter)
        finally:
            if flight:
                with self._lock:
                    flight.waiters -= 1
                    if flight.waiters == 0 and not flight.done.is_set():
                        flight.cancel.set()
            self._admission.release()

    def _run(self, key, flight, adapter):
        provider, query = key
        acquired = False
        try:
            deadline = self.clock() + 5
            while not self._slots.acquire(timeout=0.05):
                if flight.cancel.is_set():
                    raise ServiceError("Provider request cancelled.", 499)
                if self.clock() >= deadline:
                    raise ServiceError("Provider queue wait exceeded.", 503, 1)
            acquired = True
            self._gate(provider, query)
            if flight.cancel.is_set():
                raise ServiceError("Provider request cancelled.", 499)
            with self._lock:
                backoff = self._backoff.get(provider, 0) - self.clock()
            if backoff > 0:
                raise ServiceError("Provider backoff is active.", 429, backoff)
            features, records, partial, truncated, rejected, errors = [], [], False, False, 0, []
            for page in range(1, query.pages + 1):
                decision = self._gate(provider, query)
                if flight.cancel.is_set():
                    raise ServiceError("Provider request cancelled.", 499)
                request = adapter.request(query, page, credentials=self._credentials(adapter))
                limits = decision.get("limits", {}) if isinstance(decision, dict) else {}
                def lower(name, default):
                    value = limits.get(name, default)
                    if value == 0:
                        raise ServiceError("Local product limit is exhausted or disabled.", 429)
                    if type(value) not in {int, float} or not 0 < value <= default:
                        return default
                    return value
                if page > lower("max_pages", query.pages):
                    truncated = True
                    break
                request = replace(request, max_compressed=int(lower("max_response_bytes", request.max_compressed)),
                    max_decompressed=int(lower("max_response_bytes", request.max_decompressed)),
                    timeout=lower("timeout_seconds", request.timeout))
                rule = QuotaRule(limit=int(lower("requests_hour_ip", lower("requests_hour", adapter.hourly_limit))))
                try:
                    token = self.quota.reserve(provider, self.account, (rule,))
                except ServiceError as error:
                    if page == 1:
                        raise
                    partial, truncated = True, True
                    errors.append(str(error))
                    break
                try:
                    raw = self.transport.fetch(request, cancel=flight.cancel)
                    if not isinstance(raw, bytes) or len(raw) > request.max_decompressed:
                        raise ServiceError("Provider decoded byte limit exceeded.", 413)
                    value = raw if getattr(adapter, 'format', 'json') == 'protobuf' else web._load_json(raw.decode("utf-8-sig"))
                    parsed = adapter.parse(value, query)
                except Exception as error:
                    self.quota.finish(token, ambiguous=True)
                    if page == 1 or not isinstance(error, ServiceError) or error.status not in {429, 502, 503, 504}:
                        raise
                    partial, truncated = True, True
                    errors.append(str(error))
                    if error.retry_after:
                        with self._lock:
                            self._backoff[provider] = self.clock() + error.retry_after
                    break
                else:
                    self.quota.finish(token)
                features.extend(parsed["features"])
                records.extend(parsed["records"])
                partial |= parsed["partial"]
                truncated |= parsed["truncated"]
                rejected += parsed["rejected_records"]
                if not parsed["has_more"] or adapter.id not in {"nasa.cmr", "thespacedevs.ll2"}:
                    break
            self._gate(provider, query)
            if flight.cancel.is_set():
                raise ServiceError("Provider request cancelled.", 499)
            result = {"provider_id": provider, "state": "partial" if partial or truncated else "fresh",
                "features": features[:query.limit], "records": records[:query.limit],
                "provenance": {"source": provider, "citation": adapter.citation, "license": adapter.license,
                    "crs": "EPSG:4326", "allowed_operations": ["display"], "linked_media": "not fetched"},
                "coverage": adapter.coverage, "partial": bool(partial),
                "truncated": bool(truncated or len(features) > query.limit or len(records) > query.limit),
                "rejected_records": rejected, "ingested_at": datetime.now(timezone.utc).isoformat(),
                "errors": errors, "cached": False}
            if getattr(adapter, 'format', 'json') == 'protobuf':
                result.update(state=parsed['state'], feed_timestamp=parsed['feed_timestamp'],
                              feed_age_seconds=parsed['feed_age_seconds'], stale=parsed['stale'], provenance=parsed['provenance'])
            with self._lock:
                if flight.cancel.is_set():
                    raise ServiceError("Provider request cancelled.", 499)
                if self.cache_entries and not adapter.requires_credentials:
                    self._cache[key] = (self.clock(), deepcopy(result))
                    while len(self._cache) > self.cache_entries:
                        self._cache.popitem(last=False)
                flight.result = result
        except Exception as error:
            safe = error if isinstance(error, ServiceError) else ServiceError("Provider response or runtime failed.", 502)
            if adapter.requires_credentials:
                safe = ServiceError("Credentialed provider request failed.", safe.status, safe.retry_after)
            stale_allowed = False
            try:
                self._gate(provider, query)
                stale_allowed = True
            except ServiceError as denied:
                safe = denied
            with self._lock:
                if safe.retry_after and safe.status in {429, 503}:
                    self._backoff[provider] = self.clock() + safe.retry_after
                cached = self._cache.get(key)
                if stale_allowed and cached and self.clock() - cached[0] <= adapter.stale_age and safe.status in {502, 503, 504} and not flight.cancel.is_set():
                    flight.result = deepcopy(cached[1])
                    flight.result.update(state="stale", cached=True, errors=[str(safe)])
                else:
                    flight.error = safe
        finally:
            if acquired:
                self._slots.release()
            with self._lock:
                flight.done.set()
                self._flights.pop(key, None)
