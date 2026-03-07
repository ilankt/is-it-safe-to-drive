from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.lib.risk.route_risk import (
    RouteRiskSample,
    build_city_time_samples,
    combine_interval_probabilities,
    estimate_route_risk_from_cities,
    estimate_route_risk_from_samples,
)


@dataclass(frozen=True)
class _SimpleEstimate:
    probability: float


class _FakeLocationRiskModel:
    def __init__(self, city_probabilities: dict[str, float]) -> None:
        self.city_probabilities = city_probabilities

    def estimate_location_risk(self, *, city: str, start_time, duration_minutes: int):
        base = self.city_probabilities.get(city, self.city_probabilities.get("*", 0.01))
        # Convert baseline per-5min probability to duration-scaled interval probability.
        per_minute = base / 5.0
        p = 1.0 - pow((1.0 - per_minute), max(duration_minutes, 1))
        return _SimpleEstimate(probability=max(0.0, min(1.0, p)))


def test_probability_combination_formula() -> None:
    combined = combine_interval_probabilities([0.10, 0.20])
    assert round(combined, 6) == 0.28

    combined_with_clip = combine_interval_probabilities([-1.0, 2.0, 0.2])
    assert combined_with_clip == 1.0


def test_longer_route_increases_exposure_when_all_else_equal() -> None:
    model = _FakeLocationRiskModel({"city-a": 0.08})
    short = estimate_route_risk_from_cities(
        location_risk_model=model,
        city_checkpoints=["city-a", "city-a"],
        departure_time="2026-03-07T08:00:00+02:00",
        total_duration_minutes=15,
        sample_interval_minutes=5,
    )
    long = estimate_route_risk_from_cities(
        location_risk_model=model,
        city_checkpoints=["city-a", "city-a"],
        departure_time="2026-03-07T08:00:00+02:00",
        total_duration_minutes=45,
        sample_interval_minutes=5,
    )
    assert long.exposure_minutes > short.exposure_minutes
    assert long.probability > short.probability


def test_route_through_higher_risk_areas_scores_higher() -> None:
    model = _FakeLocationRiskModel(
        {
            "low": 0.02,
            "high": 0.15,
        }
    )
    low_route = estimate_route_risk_from_cities(
        location_risk_model=model,
        city_checkpoints=["low", "low", "low"],
        departure_time="2026-03-07T08:00:00+02:00",
        total_duration_minutes=30,
        sample_interval_minutes=5,
    )
    high_route = estimate_route_risk_from_cities(
        location_risk_model=model,
        city_checkpoints=["low", "high", "low"],
        departure_time="2026-03-07T08:00:00+02:00",
        total_duration_minutes=30,
        sample_interval_minutes=5,
    )
    assert high_route.probability > low_route.probability


def test_duplicate_samples_do_not_explode_probability() -> None:
    model = _FakeLocationRiskModel({"same-city": 0.10})
    t0 = datetime.fromisoformat("2026-03-07T08:00:00+02:00")
    samples = [
        RouteRiskSample(city="same-city", timestamp=t0),
        RouteRiskSample(city="same-city", timestamp=t0),  # duplicate
        RouteRiskSample(city="same-city", timestamp=t0),  # duplicate
        RouteRiskSample(city="same-city", timestamp=t0.replace(minute=5)),
    ]

    deduped = estimate_route_risk_from_samples(
        location_risk_model=model,
        samples=samples,
        default_sample_minutes=5,
        dedupe_samples=True,
    )
    raw = estimate_route_risk_from_samples(
        location_risk_model=model,
        samples=samples,
        default_sample_minutes=5,
        dedupe_samples=False,
    )

    assert deduped.sample_count_used < raw.sample_count_used
    assert deduped.probability < raw.probability
    assert deduped.probability > 0.0


def test_city_sample_builder_produces_time_ordered_samples() -> None:
    samples = build_city_time_samples(
        city_checkpoints=["a", "b", "c"],
        departure_time="2026-03-07T08:00:00+02:00",
        total_duration_minutes=20,
        sample_interval_minutes=5,
    )
    assert len(samples) >= 2
    assert samples[0].timestamp < samples[-1].timestamp
    assert samples[-1].city == "c"

