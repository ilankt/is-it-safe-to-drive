from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta


def allocate_minutes_by_hour(start: datetime, duration_minutes: int) -> dict[int, float]:
    if duration_minutes <= 0:
        return {}

    remaining = float(duration_minutes)
    cursor = start
    buckets: dict[int, float] = defaultdict(float)
    while remaining > 0:
        hour_boundary = (
            cursor.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        )
        chunk = min(remaining, (hour_boundary - cursor).total_seconds() / 60.0)
        buckets[cursor.hour] += chunk
        cursor += timedelta(minutes=chunk)
        remaining -= chunk
    return dict(buckets)


def allocate_minutes_by_weekday(start: datetime, duration_minutes: int) -> dict[int, float]:
    if duration_minutes <= 0:
        return {}

    remaining = float(duration_minutes)
    cursor = start
    buckets: dict[int, float] = defaultdict(float)
    while remaining > 0:
        day_boundary = (
            cursor.replace(hour=0, minute=0, second=0, microsecond=0)
            + timedelta(days=1)
        )
        chunk = min(remaining, (day_boundary - cursor).total_seconds() / 60.0)
        buckets[cursor.weekday()] += chunk
        cursor += timedelta(minutes=chunk)
        remaining -= chunk
    return dict(buckets)

