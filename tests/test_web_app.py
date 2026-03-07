from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.app.web import create_app


@dataclass(frozen=True)
class _FakeEstimate:
    probability: float


@dataclass(frozen=True)
class _FakeStats:
    total_events: int
    observation_start: datetime
    observation_end: datetime
    events_by_hour: dict[int, int]
    events_by_city: dict[str, int]
    events_by_city_hour: dict[str, dict[int, int]]
    last_event_by_city: dict[str, datetime]


class _FakeRiskModel:
    def __init__(self) -> None:
        tel_aviv_hours = {hour: 3 for hour in range(24)}
        tel_aviv_hours[2] = 0
        tel_aviv_hours[14] = 17

        haifa_hours = {hour: 1 for hour in range(24)}
        haifa_hours[4] = 0
        haifa_hours[9] = 6

        self.stats = _FakeStats(
            total_events=240,
            observation_start=datetime.fromisoformat("2026-03-01T00:00:00+02:00"),
            observation_end=datetime.fromisoformat("2026-03-03T00:00:00+02:00"),
            events_by_hour={
                0: 4,
                1: 3,
                2: 0,
                14: 17,
            },
            events_by_city={
                "תל אביב - מזרח": 60,
                "חיפה": 20,
                "ירושלים": 0,
            },
            events_by_city_hour={
                "תל אביב - מזרח": tel_aviv_hours,
                "חיפה": haifa_hours,
            },
            last_event_by_city={
                "תל אביב - מזרח": datetime.fromisoformat("2026-03-02T22:00:00+02:00"),
                "חיפה": datetime.fromisoformat("2026-03-02T18:30:00+02:00"),
            },
        )

    def estimate_location_risk(self, *, city: str, start_time, duration_minutes: int):
        if city == "תל אביב - מזרח":
            return _FakeEstimate(probability=0.173)
        return _FakeEstimate(probability=0.041)


def _client():
    app = create_app(
        risk_model=_FakeRiskModel(),
        city_names=["תל אביב - מזרח", "חיפה", "ירושלים"],
    )
    app.config.update({"TESTING": True})
    return app.test_client()


def test_index_page_renders() -> None:
    client = _client()
    response = client.get("/")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'dir="rtl"' in html
    assert "סיכון אזעקות היסטורי" in html
    assert "האם בטוח לנסוע לעבודה?" in html
    assert "יום מוצא" in html
    assert "חשב סיכון" in html


def test_city_autocomplete_returns_filtered_items() -> None:
    client = _client()
    response = client.get("/api/cities?q=חי&limit=5")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["items"][0] == "חיפה"


def test_estimate_endpoint_happy_path() -> None:
    client = _client()
    response = client.post(
        "/api/estimate",
        json={
            "originCity": "תל אביב - מזרח",
            "distanceKm": 12.2,
            "departureTime": "2026-03-05T18:00",
        },
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["durationMinutes"] == 13
    assert payload["roundedPercentage"] == 15
    assert payload["label"] == "נמוך"
    assert payload["avgAlarmsPerDay"] == 30.0
    assert payload["mostSafeHour"] == "02:00-03:00"
    assert payload["mostDangerousHour"] == "14:00-15:00"
    assert payload["lastAlarmTime"] == "2026-03-02T22:00+02:00"
    assert "הערכה היסטורית בלבד" in payload["disclaimer"]


def test_estimate_endpoint_rejects_non_workday() -> None:
    client = _client()
    response = client.post(
        "/api/estimate",
        json={
            "originCity": "חיפה",
            "distanceKm": 12.2,
            "departureTime": "2026-03-06T18:00",
        },
    )
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["code"] == "bad_request"
    assert "א׳-ה׳" in payload["error"]


def test_estimate_endpoint_city_summary_is_per_selected_city() -> None:
    client = _client()
    response = client.post(
        "/api/estimate",
        json={
            "originCity": "חיפה",
            "distanceKm": 12.2,
            "departureTime": "2026-03-05T18:00",
        },
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["avgAlarmsPerDay"] == 10.0
    assert payload["mostSafeHour"] == "04:00-05:00"
    assert payload["mostDangerousHour"] == "09:00-10:00"
    assert payload["lastAlarmTime"] == "2026-03-02T18:30+02:00"


def test_estimate_endpoint_city_not_found() -> None:
    client = _client()
    response = client.post(
        "/api/estimate",
        json={
            "originCity": "לא קיים",
            "distanceKm": 12.2,
            "departureTime": "2026-03-07T18:00",
        },
    )
    assert response.status_code == 404
    payload = response.get_json()
    assert payload["code"] == "city_not_found"


def test_estimate_endpoint_bad_request() -> None:
    client = _client()
    response = client.post(
        "/api/estimate",
        json={
            "originCity": "חיפה",
            "distanceKm": 0,
            "departureTime": "2026-03-07T18:00",
        },
    )
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["code"] == "bad_request"


def test_city_api_supports_large_limits_and_hebrew_query() -> None:
    city_names = [f"City {i:04d}" for i in range(300)] + ["רעננה"]
    app = create_app(risk_model=_FakeRiskModel(), city_names=city_names)
    app.config.update({"TESTING": True})
    client = app.test_client()

    full_response = client.get("/api/cities?limit=2000")
    assert full_response.status_code == 200
    full_payload = full_response.get_json()
    assert len(full_payload["items"]) == len(city_names)

    query_response = client.get("/api/cities?q=רענ&limit=10")
    assert query_response.status_code == 200
    query_payload = query_response.get_json()
    assert "רעננה" in query_payload["items"]
