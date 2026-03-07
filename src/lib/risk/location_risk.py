from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

from src.lib.data.normalize import normalize_city_key
from src.lib.risk.smoothing import blended_city_rate_per_minute, smoothed_multiplier
from src.lib.risk.time_buckets import allocate_minutes_by_hour, allocate_minutes_by_weekday

JERUSALEM_TZ = ZoneInfo("Asia/Jerusalem")


@dataclass(frozen=True)
class RiskEstimate:
    probability: float
    expected_events: float
    city_norm: str
    city_event_count: int
    fallback: str
    duration_minutes: int
    rate_per_minute: float
    hour_factor: float
    weekday_factor: float

    def as_dict(self) -> dict:
        return {
            "probability": self.probability,
            "expectedEvents": self.expected_events,
            "cityNorm": self.city_norm,
            "cityEventCount": self.city_event_count,
            "fallback": self.fallback,
            "durationMinutes": self.duration_minutes,
            "ratePerMinute": self.rate_per_minute,
            "hourFactor": self.hour_factor,
            "weekdayFactor": self.weekday_factor,
        }


@dataclass(frozen=True)
class _RiskStats:
    total_events: int
    unique_city_count: int
    observation_start: datetime
    observation_end: datetime
    observation_minutes: float
    events_by_city: dict[str, int]
    events_by_hour: dict[int, int]
    events_by_weekday: dict[int, int]
    events_by_city_hour: dict[str, dict[int, int]]
    last_event_by_city: dict[str, datetime]


def _ensure_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=JERUSALEM_TZ)
    return dt


def _parse_iso_datetime(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        return _ensure_aware(value)
    parsed = datetime.fromisoformat(value)
    return _ensure_aware(parsed)


def _load_stats_from_events(events: list[dict], include_threat_codes: set[int] | None) -> _RiskStats:
    events_by_city: dict[str, int] = {}
    events_by_hour: dict[int, int] = {hour: 0 for hour in range(24)}
    events_by_weekday: dict[int, int] = {weekday: 0 for weekday in range(7)}
    events_by_city_hour: dict[str, dict[int, int]] = {}
    last_event_by_city: dict[str, datetime] = {}

    timestamps: list[datetime] = []
    total = 0

    for event in events:
        threat_code = int(event.get("threat_code", -1))
        if include_threat_codes is not None and threat_code not in include_threat_codes:
            continue

        ts = _parse_iso_datetime(event["event_time_local"])
        city_norm = str(event["city_norm"])

        timestamps.append(ts)
        total += 1
        events_by_city[city_norm] = events_by_city.get(city_norm, 0) + 1
        events_by_hour[ts.hour] += 1
        events_by_weekday[ts.weekday()] += 1

        city_hours = events_by_city_hour.setdefault(city_norm, {hour: 0 for hour in range(24)})
        city_hours[ts.hour] += 1
        prev_last = last_event_by_city.get(city_norm)
        if prev_last is None or ts > prev_last:
            last_event_by_city[city_norm] = ts

    if not timestamps:
        now = datetime.now(tz=JERUSALEM_TZ)
        return _RiskStats(
            total_events=0,
            unique_city_count=len(events_by_city),
            observation_start=now,
            observation_end=now,
            observation_minutes=1.0,
            events_by_city=events_by_city,
            events_by_hour=events_by_hour,
            events_by_weekday=events_by_weekday,
            events_by_city_hour=events_by_city_hour,
            last_event_by_city=last_event_by_city,
        )

    start = min(timestamps)
    end = max(timestamps)
    observation_minutes = max((end - start).total_seconds() / 60.0, 1.0)
    return _RiskStats(
        total_events=total,
        unique_city_count=len(events_by_city),
        observation_start=start,
        observation_end=end,
        observation_minutes=observation_minutes,
        events_by_city=events_by_city,
        events_by_hour=events_by_hour,
        events_by_weekday=events_by_weekday,
        events_by_city_hour=events_by_city_hour,
        last_event_by_city=last_event_by_city,
    )


class LocationRiskModel:
    def __init__(
        self,
        stats: _RiskStats,
        *,
        min_city_events: int = 20,
        hour_pseudo_count: float = 5.0,
        weekday_pseudo_count: float = 20.0,
        use_weekday_factor: bool = True,
    ) -> None:
        self.stats = stats
        self.min_city_events = min_city_events
        self.hour_pseudo_count = hour_pseudo_count
        self.weekday_pseudo_count = weekday_pseudo_count
        self.use_weekday_factor = use_weekday_factor

    @classmethod
    def from_events(
        cls,
        events: list[dict],
        *,
        include_threat_codes: set[int] | None = None,
        min_city_events: int = 20,
        hour_pseudo_count: float = 5.0,
        weekday_pseudo_count: float = 20.0,
        use_weekday_factor: bool = True,
    ) -> "LocationRiskModel":
        stats = _load_stats_from_events(events, include_threat_codes=include_threat_codes)
        return cls(
            stats,
            min_city_events=min_city_events,
            hour_pseudo_count=hour_pseudo_count,
            weekday_pseudo_count=weekday_pseudo_count,
            use_weekday_factor=use_weekday_factor,
        )

    @classmethod
    def from_json(
        cls,
        data_path: Path,
        *,
        include_threat_codes: set[int] | None = None,
        min_city_events: int = 20,
        hour_pseudo_count: float = 5.0,
        weekday_pseudo_count: float = 20.0,
        use_weekday_factor: bool = True,
    ) -> "LocationRiskModel":
        events = json.loads(data_path.read_text(encoding="utf-8"))
        return cls.from_events(
            events,
            include_threat_codes=include_threat_codes,
            min_city_events=min_city_events,
            hour_pseudo_count=hour_pseudo_count,
            weekday_pseudo_count=weekday_pseudo_count,
            use_weekday_factor=use_weekday_factor,
        )

    def estimate_location_risk(
        self,
        *,
        city: str,
        start_time: str | datetime,
        duration_minutes: int,
    ) -> RiskEstimate:
        if duration_minutes <= 0:
            raise ValueError("duration_minutes must be positive.")

        city_norm = normalize_city_key(city)
        city_count = self.stats.events_by_city.get(city_norm, 0)
        city_count_denominator = max(self.stats.unique_city_count, 1)
        global_rate = self.stats.total_events / (
            self.stats.observation_minutes * city_count_denominator
        )
        rate_per_minute, fallback = blended_city_rate_per_minute(
            city_event_count=city_count,
            observation_minutes=self.stats.observation_minutes,
            global_rate_per_minute=global_rate,
            min_city_events=self.min_city_events,
        )

        start = _parse_iso_datetime(start_time)
        hour_alloc = allocate_minutes_by_hour(start, duration_minutes)
        hour_factor = 1.0
        if hour_alloc:
            hour_factor = 0.0
            for hour, minutes in hour_alloc.items():
                mult = smoothed_multiplier(
                    bucket_count=self.stats.events_by_hour.get(hour, 0),
                    total_count=self.stats.total_events,
                    num_buckets=24,
                    pseudo_count=self.hour_pseudo_count,
                )
                hour_factor += mult * (minutes / duration_minutes)

        weekday_factor = 1.0
        if self.use_weekday_factor:
            weekday_alloc = allocate_minutes_by_weekday(start, duration_minutes)
            if weekday_alloc:
                weekday_factor = 0.0
                for weekday, minutes in weekday_alloc.items():
                    mult = smoothed_multiplier(
                        bucket_count=self.stats.events_by_weekday.get(weekday, 0),
                        total_count=self.stats.total_events,
                        num_buckets=7,
                        pseudo_count=self.weekday_pseudo_count,
                    )
                    weekday_factor += mult * (minutes / duration_minutes)

        expected_events = rate_per_minute * duration_minutes * hour_factor * weekday_factor
        probability = 1.0 - math.exp(-expected_events)
        probability = max(0.0, min(1.0, probability))

        return RiskEstimate(
            probability=probability,
            expected_events=expected_events,
            city_norm=city_norm,
            city_event_count=city_count,
            fallback=fallback,
            duration_minutes=duration_minutes,
            rate_per_minute=rate_per_minute,
            hour_factor=hour_factor,
            weekday_factor=weekday_factor,
        )


@lru_cache(maxsize=2)
def load_default_location_risk_model(
    data_path: str = "data/alarms.normalized.json",
) -> LocationRiskModel:
    return LocationRiskModel.from_json(
        Path(data_path),
        include_threat_codes={0, 2, 5},
        min_city_events=20,
        hour_pseudo_count=5.0,
        weekday_pseudo_count=20.0,
        use_weekday_factor=True,
    )
