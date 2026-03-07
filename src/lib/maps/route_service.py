from __future__ import annotations

import math
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from src.types.route import RouteRequest

JERUSALEM_TZ = ZoneInfo("Asia/Jerusalem")


def _parse_user_datetime(datetime_iso: str) -> datetime:
    parsed = datetime.fromisoformat(datetime_iso)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=JERUSALEM_TZ)
    return parsed


def build_distance_response(request: RouteRequest) -> dict:
    anchor_time = _parse_user_datetime(request.datetime_iso)
    duration_minutes = int(math.ceil(request.distance_km))
    duration = timedelta(minutes=duration_minutes)
    if request.mode == "depart_at":
        departure_time = anchor_time
        arrival_time = anchor_time + duration
    else:
        arrival_time = anchor_time
        departure_time = anchor_time - duration

    return {
        "durationMinutes": duration_minutes,
        "distanceMeters": int(round(request.distance_km * 1000)),
        "departureTime": departure_time.isoformat(timespec="seconds"),
        "arrivalTime": arrival_time.isoformat(timespec="seconds"),
        "assumption": "1 minute per kilometer",
    }
