from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

RouteMode = Literal["depart_at", "arrive_by"]


class RouteValidationError(ValueError):
    pass


@dataclass(frozen=True)
class Coordinate:
    lat: float
    lng: float

    def as_dict(self) -> dict[str, float]:
        return {"lat": self.lat, "lng": self.lng}


@dataclass(frozen=True)
class RouteSample:
    lat: float
    lng: float
    timestamp: str

    def as_dict(self) -> dict[str, Any]:
        return {"lat": self.lat, "lng": self.lng, "timestamp": self.timestamp}


@dataclass(frozen=True)
class RouteRequest:
    distance_km: float
    mode: RouteMode
    datetime_iso: str

    @staticmethod
    def from_payload(payload: dict[str, Any]) -> "RouteRequest":
        if "apiKey" in payload or "api_key" in payload:
            raise RouteValidationError("API key must not be provided by clients.")

        required_fields = {"distanceKm", "mode", "datetime"}
        missing = sorted(field for field in required_fields if field not in payload)
        if missing:
            raise RouteValidationError(f"Missing fields: {', '.join(missing)}")

        mode = str(payload["mode"]).strip()
        datetime_iso = str(payload["datetime"]).strip()
        try:
            distance_km = float(payload["distanceKm"])
        except (TypeError, ValueError):
            raise RouteValidationError("distanceKm must be a number.") from None

        if not (distance_km > 0):
            raise RouteValidationError("distanceKm must be greater than 0.")
        if distance_km > 2000:
            raise RouteValidationError("distanceKm is too large.")
        if mode not in ("depart_at", "arrive_by"):
            raise RouteValidationError("Mode must be 'depart_at' or 'arrive_by'.")
        if not datetime_iso:
            raise RouteValidationError("Datetime is required.")

        return RouteRequest(
            distance_km=distance_km,
            mode=mode,  # type: ignore[arg-type]
            datetime_iso=datetime_iso,
        )


def validate_route_response(payload: dict[str, Any]) -> None:
    required = {
        "durationMinutes",
        "distanceMeters",
        "departureTime",
        "arrivalTime",
        "assumption",
    }
    missing = sorted(field for field in required if field not in payload)
    if missing:
        raise RouteValidationError(f"Missing response fields: {', '.join(missing)}")

    if not isinstance(payload["durationMinutes"], int) or payload["durationMinutes"] <= 0:
        raise RouteValidationError("durationMinutes must be a positive integer.")
    if not isinstance(payload["distanceMeters"], int) or payload["distanceMeters"] <= 0:
        raise RouteValidationError("distanceMeters must be a positive integer.")

    assumption = payload["assumption"]
    if not isinstance(assumption, str) or not assumption.strip():
        raise RouteValidationError("assumption must be a non-empty string.")

    for key in ("departureTime", "arrivalTime"):
        value = payload[key]
        if not isinstance(value, str):
            raise RouteValidationError(f"{key} must be a string.")
        datetime.fromisoformat(value)
