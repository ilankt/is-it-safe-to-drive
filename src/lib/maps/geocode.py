from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class GeocodeError(RuntimeError):
    pass


class LocationNotFoundError(GeocodeError):
    pass


class AmbiguousLocationError(GeocodeError):
    pass


@dataclass(frozen=True)
class GeocodeResult:
    lat: float
    lng: float
    label: str
    provider: str


class Geocoder(Protocol):
    def geocode_one(self, query: str) -> GeocodeResult:
        ...


class NominatimGeocoder:
    def __init__(
        self,
        base_url: str = "https://nominatim.openstreetmap.org/search",
        user_agent: str = "is-it-safe-to-drive/phase2",
        min_interval_seconds: float = 1.0,
    ) -> None:
        self.base_url = base_url
        self.user_agent = user_agent
        self.min_interval_seconds = min_interval_seconds
        self._last_request_at = 0.0

    def _throttle(self) -> None:
        elapsed = time.time() - self._last_request_at
        wait = self.min_interval_seconds - elapsed
        if wait > 0:
            time.sleep(wait)

    def geocode_one(self, query: str) -> GeocodeResult:
        query = query.strip()
        if len(query) < 3:
            raise AmbiguousLocationError("Query too short; address is ambiguous.")

        params = {
            "q": query,
            "format": "jsonv2",
            "addressdetails": 1,
            "countrycodes": "il",
            "limit": 5,
        }
        url = f"{self.base_url}?{urlencode(params)}"
        self._throttle()
        request = Request(url, headers={"User-Agent": self.user_agent})
        try:
            with urlopen(request, timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception as exc:  # pragma: no cover - network layer
            raise GeocodeError(f"Geocoding request failed: {exc}") from exc
        finally:
            self._last_request_at = time.time()

        if not payload:
            raise LocationNotFoundError(f"No geocoding results for '{query}'.")

        top = payload[0]

        return GeocodeResult(
            lat=float(top["lat"]),
            lng=float(top["lon"]),
            label=str(top.get("display_name", query)),
            provider="nominatim",
        )
