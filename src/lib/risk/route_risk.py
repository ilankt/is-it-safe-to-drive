from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable, Protocol

from src.lib.data.normalize import normalize_city_key


class _LocationRiskLike(Protocol):
    def estimate_location_risk(
        self, *, city: str, start_time: str | datetime, duration_minutes: int
    ):
        ...


@dataclass(frozen=True)
class RouteRiskSample:
    city: str
    timestamp: datetime


@dataclass(frozen=True)
class RouteRiskContribution:
    city: str
    city_norm: str
    timestamp: str
    duration_minutes: int
    probability: float

    def as_dict(self) -> dict:
        return {
            "city": self.city,
            "cityNorm": self.city_norm,
            "timestamp": self.timestamp,
            "durationMinutes": self.duration_minutes,
            "probability": self.probability,
        }


@dataclass(frozen=True)
class RouteRiskEstimate:
    probability: float
    sample_count_raw: int
    sample_count_used: int
    exposure_minutes: int
    contributions: list[RouteRiskContribution]

    def as_dict(self) -> dict:
        return {
            "probability": self.probability,
            "sampleCountRaw": self.sample_count_raw,
            "sampleCountUsed": self.sample_count_used,
            "exposureMinutes": self.exposure_minutes,
            "contributions": [contrib.as_dict() for contrib in self.contributions],
        }


def combine_interval_probabilities(probabilities: Iterable[float]) -> float:
    product = 1.0
    for probability in probabilities:
        clipped = min(1.0, max(0.0, float(probability)))
        product *= 1.0 - clipped
    combined = 1.0 - product
    return min(1.0, max(0.0, combined))


def build_city_time_samples(
    *,
    city_checkpoints: list[str],
    departure_time: str | datetime,
    total_duration_minutes: int,
    sample_interval_minutes: int = 5,
) -> list[RouteRiskSample]:
    if total_duration_minutes <= 0:
        raise ValueError("total_duration_minutes must be positive.")
    if sample_interval_minutes <= 0:
        raise ValueError("sample_interval_minutes must be positive.")
    if len(city_checkpoints) < 1:
        raise ValueError("city_checkpoints must include at least one city.")

    if isinstance(departure_time, str):
        start = datetime.fromisoformat(departure_time)
    else:
        start = departure_time

    if len(city_checkpoints) == 1:
        city_checkpoints = [city_checkpoints[0], city_checkpoints[0]]

    sample_count = max(2, int(math.ceil(total_duration_minutes / sample_interval_minutes)) + 1)
    samples: list[RouteRiskSample] = []
    for idx in range(sample_count):
        ratio = idx / float(sample_count - 1)
        checkpoint_idx = min(
            len(city_checkpoints) - 1,
            int(round(ratio * (len(city_checkpoints) - 1))),
        )
        minute_offset = min(total_duration_minutes, idx * sample_interval_minutes)
        timestamp = start + timedelta(minutes=minute_offset)
        samples.append(
            RouteRiskSample(
                city=city_checkpoints[checkpoint_idx],
                timestamp=timestamp,
            )
        )

    # Ensure final sample lands exactly on arrival.
    samples[-1] = RouteRiskSample(
        city=samples[-1].city,
        timestamp=start + timedelta(minutes=total_duration_minutes),
    )
    return samples


def estimate_route_risk_from_samples(
    *,
    location_risk_model: _LocationRiskLike,
    samples: list[RouteRiskSample],
    default_sample_minutes: int = 5,
    dedupe_samples: bool = True,
) -> RouteRiskEstimate:
    if not samples:
        raise ValueError("At least one route sample is required.")
    if default_sample_minutes <= 0:
        raise ValueError("default_sample_minutes must be positive.")

    ordered = sorted(samples, key=lambda sample: sample.timestamp)
    raw_count = len(ordered)

    used_samples: list[RouteRiskSample] = []
    seen_keys: set[tuple[str, str]] = set()
    for sample in ordered:
        city_norm = normalize_city_key(sample.city)
        ts_key = sample.timestamp.replace(second=0, microsecond=0).isoformat()
        key = (city_norm, ts_key)
        if dedupe_samples and key in seen_keys:
            continue
        seen_keys.add(key)
        used_samples.append(sample)

    contributions: list[RouteRiskContribution] = []
    probabilities: list[float] = []
    exposure_minutes = 0

    for idx, sample in enumerate(used_samples):
        if idx < len(used_samples) - 1:
            next_ts = used_samples[idx + 1].timestamp
            delta_minutes = int(round((next_ts - sample.timestamp).total_seconds() / 60.0))
            duration_minutes = max(1, delta_minutes)
        else:
            duration_minutes = default_sample_minutes

        estimate = location_risk_model.estimate_location_risk(
            city=sample.city,
            start_time=sample.timestamp,
            duration_minutes=duration_minutes,
        )
        probability = float(estimate.probability)
        probabilities.append(probability)
        exposure_minutes += duration_minutes
        contributions.append(
            RouteRiskContribution(
                city=sample.city,
                city_norm=normalize_city_key(sample.city),
                timestamp=sample.timestamp.isoformat(timespec="seconds"),
                duration_minutes=duration_minutes,
                probability=probability,
            )
        )

    combined = combine_interval_probabilities(probabilities)
    return RouteRiskEstimate(
        probability=combined,
        sample_count_raw=raw_count,
        sample_count_used=len(used_samples),
        exposure_minutes=exposure_minutes,
        contributions=contributions,
    )


def estimate_route_risk_from_cities(
    *,
    location_risk_model: _LocationRiskLike,
    city_checkpoints: list[str],
    departure_time: str | datetime,
    total_duration_minutes: int,
    sample_interval_minutes: int = 5,
    dedupe_samples: bool = True,
) -> RouteRiskEstimate:
    samples = build_city_time_samples(
        city_checkpoints=city_checkpoints,
        departure_time=departure_time,
        total_duration_minutes=total_duration_minutes,
        sample_interval_minutes=sample_interval_minutes,
    )
    return estimate_route_risk_from_samples(
        location_risk_model=location_risk_model,
        samples=samples,
        default_sample_minutes=sample_interval_minutes,
        dedupe_samples=dedupe_samples,
    )

