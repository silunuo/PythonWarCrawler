from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

from src.common.config import AppConfig


@dataclass(frozen=True)
class DateRange:
    enabled: bool = True
    start: date | None = None
    end: date | None = None

    def contains_date(self, value: date | None) -> bool:
        if not self.enabled:
            return True
        if value is None:
            return False
        if self.start and value < self.start:
            return False
        if self.end and value > self.end:
            return False
        return True

    def contains_datetime(self, value: datetime | None) -> bool:
        if value is None:
            return self.contains_date(None)
        return self.contains_date(value.date())

    def is_before_start(self, value: datetime | None) -> bool:
        return bool(self.enabled and self.start and value and value.date() < self.start)

    def after_unix(self) -> int | None:
        if not self.enabled or not self.start:
            return None
        return int(datetime.combine(self.start, datetime.min.time(), timezone.utc).timestamp())

    def before_unix(self) -> int | None:
        if not self.enabled or not self.end:
            return None
        next_day = self.end + timedelta(days=1)
        return int(datetime.combine(next_day, datetime.min.time(), timezone.utc).timestamp()) - 1


def build_date_range(
    config: AppConfig,
    start_date: str | None = None,
    end_date: str | None = None,
    no_date_filter: bool = False,
) -> DateRange:
    settings = config.get("date_range", default={}) or {}
    enabled = bool(settings.get("enabled", True)) and not no_date_filter
    start_raw = start_date if start_date is not None else settings.get("start_date", "2026-02-28")
    end_raw = end_date if end_date is not None else settings.get("end_date")
    return DateRange(
        enabled=enabled,
        start=parse_date(start_raw) if enabled else None,
        end=parse_date(end_raw) if enabled else None,
    )


def parse_date(value: Any) -> date | None:
    if value in (None, ""):
        return date.today()
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    return datetime.strptime(str(value), "%Y-%m-%d").date()


def parse_iso_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    try:
        normalized = text.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def datetime_from_unix(value: Any) -> datetime | None:
    try:
        timestamp = int(float(value))
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(timestamp, timezone.utc)


def date_from_relative(text: str, now: datetime | None = None) -> date | None:
    value = (text or "").strip().lower()
    if not value:
        return None
    now = now or datetime.now(timezone.utc)
    if value in {"now", "just now"}:
        return now.date()
    match = re.search(r"(\d+)\s+(second|minute|hour|day|week|month|year)s?\s+ago", value)
    if not match:
        return None
    amount = int(match.group(1))
    unit = match.group(2)
    if unit in {"second", "minute", "hour"}:
        delta = timedelta(days=0)
    elif unit == "day":
        delta = timedelta(days=amount)
    elif unit == "week":
        delta = timedelta(days=amount * 7)
    elif unit == "month":
        delta = timedelta(days=amount * 30)
    else:
        delta = timedelta(days=amount * 365)
    return (now - delta).date()

