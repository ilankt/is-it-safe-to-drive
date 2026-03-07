from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from src.types.route import Coordinate


class RoutingError(RuntimeError):
    pass


@dataclass(frozen=True)
class RoutePath:
    distance_meters: float
    duration_seconds: float
    coordinates: list[Coordinate]
    provider: str


class Router(Protocol):
    def compute_route(self, origin: Coordinate, destination: Coordinate) -> RoutePath:
        ...


class OsrmRouter:
    def __init__(
        self,
        base_url: str = "https://router.project-osrm.org",
        profile: str = "driving",
        user_agent: str = "is-it-safe-to-drive/phase2",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.profile = profile
        self.user_agent = user_agent

    def compute_route(self, origin: Coordinate, destination: Coordinate) -> RoutePath:
        coordinates = f"{origin.lng},{origin.lat};{destination.lng},{destination.lat}"
        params = urlencode(
            {
                "overview": "full",
                "geometries": "geojson",
                "steps": "false",
            }
        )
        url = f"{self.base_url}/route/v1/{self.profile}/{coordinates}?{params}"
        request = Request(url, headers={"User-Agent": self.user_agent})

        try:
            with urlopen(request, timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception as exc:  # pragma: no cover - network layer
            raise RoutingError(f"Routing request failed: {exc}") from exc

        if payload.get("code") != "Ok":
            raise RoutingError(f"Routing provider error: {payload.get('code')}")

        routes = payload.get("routes") or []
        if not routes:
            raise RoutingError("No route found.")

        route = routes[0]
        geometry = route.get("geometry", {})
        points = geometry.get("coordinates") or []
        if len(points) < 2:
            raise RoutingError("Route geometry is empty.")

        path = [Coordinate(lat=float(lat), lng=float(lng)) for lng, lat in points]
        return RoutePath(
            distance_meters=float(route["distance"]),
            duration_seconds=float(route["duration"]),
            coordinates=path,
            provider="osrm",
        )

