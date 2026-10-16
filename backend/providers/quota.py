"""Durable local admission ledger. Upstream/account usage elsewhere remains unknown."""

from dataclasses import dataclass
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import sqlite3
import time
import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ..errors import ServiceError


@dataclass(frozen=True)
class QuotaRule:
    unit: str = "requests"
    limit: int = 100
    window_seconds: int = 3600
    calendar: str | None = None
    timezone: str = "UTC"

    def __post_init__(self):
        if (self.unit not in {"requests", "events", "processing_units", "bytes"}
                or type(self.limit) is not int or not 1 <= self.limit <= 10**12
                or type(self.window_seconds) is not int or not 1 <= self.window_seconds <= 366 * 86400
                or self.calendar not in {None, "day", "month"}):
            raise ValueError("Invalid quota rule")
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, TypeError):
            raise ValueError("Quota timezone is unavailable") from None

    def window(self, now):
        if self.calendar is None:
            start = int(now // self.window_seconds) * self.window_seconds
            return start, start + self.window_seconds
        local = datetime.fromtimestamp(now, ZoneInfo(self.timezone))
        start = local.replace(hour=0, minute=0, second=0, microsecond=0,
                              day=1 if self.calendar == "month" else local.day)
        end = (start + timedelta(days=1) if self.calendar == "day" else
               start.replace(year=start.year + (start.month == 12), month=start.month % 12 + 1))
        return int(start.timestamp()), int(end.timestamp())


class QuotaStore:
    """Each reservation atomically charges every dimension before dispatch.

    Pending reservations survive crashes as charges. Only explicit actual usage
    reconciliation can reduce them; failures/cancellation are never refunded.
    The storage path and non-secret account identity are injected by the caller.
    """

    def __init__(self, path, clock=time.time):
        self.path, self.clock = str(path), clock
        if self.path == ":memory:":
            raise ValueError("Quota storage must be durable")
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS provider_usage (
                    provider TEXT, account TEXT, unit TEXT, window_start INTEGER,
                    used INTEGER NOT NULL, PRIMARY KEY(provider,account,unit,window_start));
                CREATE TABLE IF NOT EXISTS provider_reservations (
                    token TEXT, provider TEXT, account TEXT, unit TEXT, window_start INTEGER,
                    amount INTEGER NOT NULL, state TEXT NOT NULL,
                    PRIMARY KEY(token,unit));
                CREATE TABLE IF NOT EXISTS provider_clock (id INTEGER PRIMARY KEY, last REAL);
            """)

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        try:
            db.execute("PRAGMA busy_timeout=5000")
            db.execute("PRAGMA synchronous=FULL")
            with db:
                yield db
        finally:
            db.close()

    def reserve(self, provider, account, rules, costs=None):
        costs = {"requests": 1} if costs is None else costs
        if (not isinstance(provider, str) or not 1 <= len(provider) <= 100 or not isinstance(account, str)
                or not 1 <= len(account) <= 100 or not rules or len({r.unit for r in rules}) != len(rules)
                or set(costs) != {r.unit for r in rules}
                or any(type(v) is not int or not 0 <= v <= 10**12 for v in costs.values())):
            raise ValueError("Invalid quota reservation")
        token = uuid.uuid4().hex
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            # A backward wall-clock jump must not reopen an older local allowance.
            last = db.execute("SELECT last FROM provider_clock WHERE id=1").fetchone()
            now = max(self.clock(), last[0] if last else 0)
            db.execute("INSERT OR REPLACE INTO provider_clock VALUES (1,?)", (now,))
            for rule in rules:
                start, end = rule.window(now)
                identity = (provider, account, rule.unit, start)
                row = db.execute("SELECT used FROM provider_usage WHERE provider=? AND account=? AND unit=? AND window_start=?", identity).fetchone()
                used, amount = (row[0] if row else 0), costs[rule.unit]
                if used + amount > rule.limit:
                    raise ServiceError("Local provider quota exhausted; external account usage is unknown.", 429, end - now)
                db.execute("INSERT INTO provider_usage VALUES (?,?,?,?,?) ON CONFLICT(provider,account,unit,window_start) DO UPDATE SET used=used+excluded.used", identity + (amount,))
                db.execute("INSERT INTO provider_reservations VALUES (?,?,?,?,?,?,?)", (token,) + identity + (amount, "reserved"))
        return token

    def finish(self, token, *, actual=None, ambiguous=False):
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute("SELECT provider,account,unit,window_start,amount,state FROM provider_reservations WHERE token=?", (token,)).fetchall()
            if not rows:
                raise ValueError("Unknown reservation")
            if actual is not None and (set(actual) != {r[2] for r in rows} or
                    any(type(v) is not int or not 0 <= v <= 10**12 for v in actual.values()) or ambiguous):
                raise ValueError("Invalid actual usage")
            if any(row[5] != "reserved" for row in rows):
                raise ValueError("Reservation already finalized")
            for provider, account, unit, start, amount, _ in rows:
                charged = amount if actual is None else actual[unit]
                db.execute("UPDATE provider_usage SET used=used+? WHERE provider=? AND account=? AND unit=? AND window_start=?",
                           (charged - amount, provider, account, unit, start))
                db.execute("UPDATE provider_reservations SET amount=?,state=? WHERE token=? AND unit=?",
                           (charged, "ambiguous" if ambiguous else "charged", token, unit))

    def snapshot(self, provider, account="public"):
        with self._connect() as db:
            rows = db.execute("SELECT unit,window_start,used FROM provider_usage WHERE provider=? AND account=? ORDER BY window_start,unit", (provider, account)).fetchall()
            pending = db.execute("SELECT count(DISTINCT token) FROM provider_reservations WHERE provider=? AND account=? AND state IN ('reserved','ambiguous')", (provider, account)).fetchone()[0]
        return {"usage": [{"unit": r[0], "window_start": r[1], "used": r[2]} for r in rows],
                "uncertain_reservations": pending, "external_account_usage": "unknown"}
