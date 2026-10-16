"""Strict, bounded provider input. There is deliberately no URL or raw query field."""

from dataclasses import dataclass
from datetime import datetime, timezone
import math
import re

from ..errors import ServiceError


def utc_time(value):
    if not isinstance(value, str) or len(value) > 32:
        raise ServiceError("Expected an ISO timestamp with timezone.", 400)
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.tzinfo is None:
            raise ValueError
        return result.astimezone(timezone.utc)
    except ValueError:
        raise ServiceError("Expected an ISO timestamp with timezone.", 400) from None


def number(value, minimum, maximum):
    return type(value) in {int, float} and math.isfinite(value) and minimum <= value <= maximum


@dataclass(frozen=True)
class ProviderQuery:
    bbox: tuple | None = None
    latitude: float | None = None
    longitude: float | None = None
    start: str | None = None
    end: str | None = None
    entity_id: str | None = None
    dataset: str | None = None
    text: str | None = None
    limit: int = 50
    pages: int = 1

    def __post_init__(self):
        if type(self.limit) is not int or not 1 <= self.limit <= 100 or type(self.pages) is not int or not 1 <= self.pages <= 3:
            raise ServiceError("Provider result/page limit is invalid.", 400)
        if self.bbox is not None:
            b = self.bbox
            if (type(b) is not tuple or len(b) != 4 or not number(b[0], -180, 180)
                    or not number(b[2], -180, 180) or not number(b[1], -90, 90)
                    or not number(b[3], -90, 90) or b[0] >= b[2] or b[1] >= b[3]
                    or b[2] - b[0] > 30 or b[3] - b[1] > 30):
                raise ServiceError("Viewport must be non-wrapping and at most 30 degrees per axis.", 400)
        if (self.latitude is None) != (self.longitude is None) or (self.latitude is not None and
                (not number(self.latitude, -90, 90) or not number(self.longitude, -180, 180))):
            raise ServiceError("Provider point is invalid.", 400)
        if (self.start is None) != (self.end is None):
            raise ServiceError("Both time bounds are required.", 400)
        if self.start is not None:
            start, end = utc_time(self.start), utc_time(self.end)
            if not 0 < (end - start).total_seconds() <= 31 * 86400:
                raise ServiceError("Provider time range must be positive and at most 31 days.", 400)
        for value in (self.entity_id, self.dataset):
            if value is not None and (not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,100}", value)):
                raise ServiceError("Provider entity/dataset identifier is invalid.", 400)
        if self.text is not None and (not isinstance(self.text, str) or not 1 <= len(self.text) <= 160
                or any(ord(c) < 32 or ord(c) == 127 for c in self.text)):
            raise ServiceError("Provider search text is invalid.", 400)

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict) or set(value) - set(cls.__dataclass_fields__):
            raise ServiceError("Unknown provider query fields.", 400)
        values = dict(value)
        if isinstance(values.get("bbox"), list):
            values["bbox"] = tuple(values["bbox"])
        return cls(**values)

    def require(self, *fields):
        if any(getattr(self, field) is None for field in fields):
            raise ServiceError("Required provider query fields are missing.", 400)
