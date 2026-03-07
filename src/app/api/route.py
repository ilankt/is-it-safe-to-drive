from __future__ import annotations

from typing import Any

from src.lib.maps.route_service import build_distance_response
from src.types.route import RouteRequest, RouteValidationError, validate_route_response


def handle_route_post(
    payload: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    try:
        request = RouteRequest.from_payload(payload)
        response = build_distance_response(request=request)
        validate_route_response(response)
        return 200, response
    except RouteValidationError as exc:
        return 400, {"error": str(exc), "code": "bad_request"}
