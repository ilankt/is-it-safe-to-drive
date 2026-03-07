from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

SOURCE_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
JERUSALEM_TZ = ZoneInfo("Asia/Jerusalem")
CONFLICT_START_LOCAL = datetime(2026, 2, 28, 10, 10, 20)

THREAT_TYPE_BY_CODE = {
    0: "rocket_missile",
    2: "infiltration",
    3: "earthquake",
    5: "hostile_aircraft",
}


def parse_source_time(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, SOURCE_TIME_FORMAT)
    except ValueError:
        return None


def localize_jerusalem(local_naive: datetime) -> datetime:
    return local_naive.replace(tzinfo=JERUSALEM_TZ)


def to_local_iso(local_naive: datetime) -> str:
    return localize_jerusalem(local_naive).isoformat(timespec="seconds")


def to_utc_iso(local_naive: datetime) -> str:
    return (
        localize_jerusalem(local_naive)
        .astimezone(timezone.utc)
        .isoformat(timespec="seconds")
    )


def normalize_origin(origin: str | None) -> tuple[str, bool]:
    if origin is None:
        return "UNKNOWN", True
    stripped = origin.strip()
    if not stripped:
        return "UNKNOWN", True
    return stripped, False


def normalize_city_key(city_raw: str) -> str:
    city = city_raw.strip()
    city = " ".join(city.split())

    for old, new in (
        ("־", "-"),
        ("–", "-"),
        ("״", '"'),
        ("”", '"'),
        ("“", '"'),
        ("׳", "'"),
        ("`", "'"),
    ):
        city = city.replace(old, new)

    city = city.replace('"', "").replace("'", "")
    return city.lower()


def threat_type_for_code(threat_code: int) -> str:
    return THREAT_TYPE_BY_CODE.get(threat_code, "other")

