from __future__ import annotations

import json
import math
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from flask import Flask, jsonify, render_template, request

from src.lib.data.normalize import normalize_city_key
from src.lib.risk.location_risk import load_default_location_risk_model

JERUSALEM_TZ = ZoneInfo("Asia/Jerusalem")


def _load_city_names(path: Path) -> list[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    names = sorted({str(item["city_canonical"]).strip() for item in data if item.get("city_canonical")})
    return names


def _risk_label(rounded_percentage: int) -> str:
    if rounded_percentage <= 5:
        return "נמוך מאוד"
    if rounded_percentage <= 20:
        return "נמוך"
    if rounded_percentage <= 40:
        return "בינוני"
    if rounded_percentage <= 60:
        return "גבוה"
    return "גבוה מאוד"


def _parse_departure(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("פורמט שעת היציאה אינו תקין.") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=JERUSALEM_TZ)
    return parsed


def _is_israeli_workday(dt: datetime) -> bool:
    weekday = dt.astimezone(JERUSALEM_TZ).weekday()
    return weekday in {6, 0, 1, 2, 3}


def _format_hour_range(hour: int) -> str:
    next_hour = (hour + 1) % 24
    return f"{hour:02d}:00-{next_hour:02d}:00"


def _build_city_risk_summary(model, city_norm: str) -> dict[str, float | str | None]:
    stats = getattr(model, "stats", None)
    if stats is None:
        return {
            "avgAlarmsPerDay": None,
            "mostSafeHour": None,
            "mostDangerousHour": None,
            "lastAlarmTime": None,
        }

    events_by_city = dict(getattr(stats, "events_by_city", {}) or {})
    city_event_count = int(events_by_city.get(city_norm, 0))
    start = getattr(stats, "observation_start", None)
    end = getattr(stats, "observation_end", None)
    observation_days = 1.0
    city_last_alarm = None
    if isinstance(start, datetime) and isinstance(end, datetime):
        observation_days = max((end - start).total_seconds() / 86400.0, 1.0)
    last_event_by_city = dict(getattr(stats, "last_event_by_city", {}) or {})
    if isinstance(last_event_by_city.get(city_norm), datetime):
        city_last_alarm = last_event_by_city[city_norm].astimezone(JERUSALEM_TZ).isoformat(
            timespec="minutes"
        )

    events_by_city_hour = dict(getattr(stats, "events_by_city_hour", {}) or {})
    city_hours = events_by_city_hour.get(city_norm, {})
    if city_event_count > 0 and city_hours:
        most_safe_hour = min(range(24), key=lambda hour: (city_hours.get(hour, 0), hour))
        most_dangerous_hour = max(range(24), key=lambda hour: (city_hours.get(hour, 0), -hour))
        safe_hour_label = _format_hour_range(most_safe_hour)
        dangerous_hour_label = _format_hour_range(most_dangerous_hour)
    else:
        safe_hour_label = None
        dangerous_hour_label = None

    return {
        "avgAlarmsPerDay": round(city_event_count / observation_days, 1),
        "mostSafeHour": safe_hour_label,
        "mostDangerousHour": dangerous_hour_label,
        "lastAlarmTime": city_last_alarm,
    }


def create_app(
    *,
    city_lookup_path: str = "data/city_lookup.json",
    risk_data_path: str = "data/alarms.normalized.json",
    risk_model=None,
    city_names: list[str] | None = None,
) -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")
    catalog = city_names or _load_city_names(Path(city_lookup_path))
    catalog_norm = {normalize_city_key(name): name for name in catalog}
    model = risk_model or load_default_location_risk_model(risk_data_path)

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/api/cities")
    def cities():
        query = request.args.get("q", "").strip()
        limit_raw = request.args.get("limit", "20")
        try:
            limit = max(1, min(int(limit_raw), 5000))
        except ValueError:
            limit = 20

        if not query:
            return jsonify({"items": catalog[:limit]})

        query_norm = normalize_city_key(query)
        starts = [name for name in catalog if normalize_city_key(name).startswith(query_norm)]
        contains = [
            name
            for name in catalog
            if query_norm in normalize_city_key(name) and name not in starts
        ]
        return jsonify({"items": (starts + contains)[:limit]})

    @app.post("/api/estimate")
    def estimate():
        payload = request.get_json(silent=True) or {}
        try:
            origin_city = str(payload.get("originCity", "")).strip()
            if not origin_city:
                raise ValueError("יש לבחור עיר מוצא.")

            origin_norm = normalize_city_key(origin_city)
            if origin_norm not in catalog_norm:
                raise LookupError("העיר לא נמצאה ברשימה הנתמכת.")

            distance_km = float(payload.get("distanceKm"))
            if not (distance_km > 0):
                raise ValueError("מרחק הנסיעה חייב להיות גדול מ-0.")
            if distance_km > 2000:
                raise ValueError("מרחק הנסיעה גדול מדי.")

            departure_raw = str(payload.get("departureTime", "")).strip()
            if not departure_raw:
                raise ValueError("יש לבחור שעת יציאה.")
            departure = _parse_departure(departure_raw)
            if not _is_israeli_workday(departure):
                raise ValueError("שעת היציאה חייבת להיות בין א׳-ה׳.")
        except LookupError as exc:
            return jsonify({"error": str(exc), "code": "city_not_found"}), 404
        except (TypeError, ValueError) as exc:
            return jsonify({"error": str(exc), "code": "bad_request"}), 400

        duration_minutes = int(math.ceil(distance_km))
        arrival = departure + timedelta(minutes=duration_minutes)
        risk = model.estimate_location_risk(
            city=catalog_norm[origin_norm],
            start_time=departure,
            duration_minutes=duration_minutes,
        )
        city_summary = _build_city_risk_summary(model, origin_norm)

        raw_percentage = risk.probability * 100.0
        rounded_percentage = int(round(raw_percentage / 5.0) * 5)
        rounded_percentage = max(0, min(100, rounded_percentage))
        label = _risk_label(rounded_percentage)

        return jsonify(
            {
                "originCity": catalog_norm[origin_norm],
                "distanceKm": distance_km,
                "durationMinutes": duration_minutes,
                "departureTime": departure.isoformat(timespec="minutes"),
                "arrivalTime": arrival.isoformat(timespec="minutes"),
                "rawProbability": risk.probability,
                "rawPercentage": raw_percentage,
                "roundedPercentage": rounded_percentage,
                "label": label,
                "explanation": "הערכת סיכון על בסיס נתוני אזעקות היסטוריים לעיר המוצא ולחלון הנסיעה.",
                "disclaimer": (
                    "הערכה היסטורית בלבד ולמטרות בידור בלבד. "
                    "זו אינה התרעה בזמן אמת ואינה הנחיית בטיחות. "
                    "יש לפעול תמיד לפי הנחיות פיקוד העורף."
                ),
                "avgAlarmsPerDay": city_summary["avgAlarmsPerDay"],
                "mostSafeHour": city_summary["mostSafeHour"],
                "mostDangerousHour": city_summary["mostDangerousHour"],
                "lastAlarmTime": city_summary["lastAlarmTime"],
            }
        )

    return app
