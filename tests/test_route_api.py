from __future__ import annotations

from datetime import datetime

from src.app.api.route import handle_route_post
from src.types.route import validate_route_response


def test_route_api_happy_path_depart_at() -> None:
    status, payload = handle_route_post(
        {
            "distanceKm": 27.4,
            "mode": "depart_at",
            "datetime": "2026-03-10T08:00:00+02:00",
        }
    )
    assert status == 200
    validate_route_response(payload)
    assert payload["durationMinutes"] == 28
    assert payload["distanceMeters"] == 27400
    assert payload["assumption"] == "1 minute per kilometer"


def test_route_api_arrive_by_back_calculates_departure() -> None:
    status, payload = handle_route_post(
        {
            "distanceKm": 35.0,
            "mode": "arrive_by",
            "datetime": "2026-03-10T09:00:00+02:00",
        }
    )
    assert status == 200
    dep = datetime.fromisoformat(payload["departureTime"])
    arr = datetime.fromisoformat(payload["arrivalTime"])
    assert int((arr - dep).total_seconds()) == 35 * 60
    assert arr.isoformat(timespec="seconds") == "2026-03-10T09:00:00+02:00"


def test_route_api_rejects_client_api_key_field() -> None:
    status, payload = handle_route_post(
        {
            "distanceKm": 12,
            "mode": "depart_at",
            "datetime": "2026-03-10T09:00:00+02:00",
            "apiKey": "should-not-be-here",
        }
    )
    assert status == 400
    assert payload["code"] == "bad_request"


def test_route_api_invalid_distance_fails_gracefully() -> None:
    status, payload = handle_route_post(
        {
            "distanceKm": 0,
            "mode": "depart_at",
            "datetime": "2026-03-10T09:00:00+02:00",
        }
    )
    assert status == 400
    assert payload["code"] == "bad_request"


def test_duration_consistency_for_multiple_distances() -> None:
    for distance_km, expected_minutes in [
        (1, 1),
        (5.1, 6),
        (12.0, 12),
        (23.9, 24),
        (80.4, 81),
    ]:
        status, payload = handle_route_post(
            {
                "distanceKm": distance_km,
                "mode": "depart_at",
                "datetime": "2026-03-10T09:00:00+02:00",
            }
        )
        assert status == 200
        assert payload["durationMinutes"] == expected_minutes
