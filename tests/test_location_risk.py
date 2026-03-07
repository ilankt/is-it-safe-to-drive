from __future__ import annotations

import json
from pathlib import Path

from src.lib.risk.location_risk import (
    LocationRiskModel,
    load_default_location_risk_model,
)


def _fixture_model() -> LocationRiskModel:
    fixture_path = Path("tests/fixtures/location_risk_fixture.json")
    events = json.loads(fixture_path.read_text(encoding="utf-8"))
    return LocationRiskModel.from_events(
        events,
        include_threat_codes={0, 2, 5},
        min_city_events=20,
        hour_pseudo_count=5.0,
        weekday_pseudo_count=20.0,
        use_weekday_factor=False,
    )


def test_snapshot_alpha_city_fixture() -> None:
    model = _fixture_model()
    estimate = model.estimate_location_risk(
        city="alpha",
        start_time="2026-03-01T10:00:00+02:00",
        duration_minutes=60,
    )
    assert estimate.fallback == "blended_global"
    assert estimate.city_event_count == 5
    assert round(estimate.expected_events, 6) == 0.647619
    assert round(estimate.probability, 6) == 0.47671


def test_snapshot_unknown_city_fixture_global_fallback() -> None:
    model = _fixture_model()
    estimate = model.estimate_location_risk(
        city="unknown-city",
        start_time="2026-03-01T05:00:00+02:00",
        duration_minutes=60,
    )
    assert estimate.fallback == "global"
    assert estimate.city_event_count == 0
    assert round(estimate.expected_events, 6) == 0.285714
    assert round(estimate.probability, 6) == 0.248523


def test_real_data_probabilities_are_bounded() -> None:
    model = load_default_location_risk_model()
    cases = [
        ("פתח תקווה", "2026-03-04T08:00:00+02:00", 20),
        ("תל אביב - מזרח", "2026-03-06T22:00:00+02:00", 45),
        ("קריית שמונה", "2026-03-05T12:30:00+02:00", 30),
        ("unknown-city-123", "2026-03-05T12:30:00+02:00", 30),
    ]
    for city, start, duration in cases:
        estimate = model.estimate_location_risk(
            city=city, start_time=start, duration_minutes=duration
        )
        assert 0.0 <= estimate.probability <= 1.0
        assert estimate.expected_events >= 0.0


def test_real_data_sparse_city_fallback_is_graceful() -> None:
    model = load_default_location_risk_model()
    estimate = model.estimate_location_risk(
        city="zzzz-non-existing-city",
        start_time="2026-03-05T09:00:00+02:00",
        duration_minutes=35,
    )
    assert estimate.fallback == "global"
    assert estimate.city_event_count == 0
    assert estimate.probability > 0.0


def test_real_data_outputs_are_stable_for_known_cases() -> None:
    model = load_default_location_risk_model()
    inputs = dict(
        city="פתח תקווה",
        start_time="2026-03-05T10:15:00+02:00",
        duration_minutes=25,
    )
    first = model.estimate_location_risk(**inputs)
    second = model.estimate_location_risk(**inputs)

    assert first.as_dict() == second.as_dict()
