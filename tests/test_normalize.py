from __future__ import annotations

from src.lib.data.normalize import (
    normalize_city_key,
    normalize_origin,
    parse_source_time,
    threat_type_for_code,
    to_local_iso,
    to_utc_iso,
)


def test_parse_source_time_valid() -> None:
    parsed = parse_source_time("2026-03-01 12:34:56")
    assert parsed is not None
    assert parsed.year == 2026
    assert parsed.month == 3
    assert parsed.day == 1


def test_parse_source_time_invalid() -> None:
    assert parse_source_time("2026/03/01 12:34:56") is None
    assert parse_source_time("") is None


def test_city_normalization_resolves_known_variants() -> None:
    variant_groups = [
        ("ג'ת", "גת"),
        ("בית חג\"י", "בית חגי"),
        ("ח'וואלד", "חוואלד"),
        ("'ביר הדאג", "ביר הדאג'"),
        ("ניל''י", "נילי"),
        ("גבעת כ''ח", "גבעת כח"),
        ("כפר ביל''ו", "כפר בילו"),
        ("כפר חב''ד", "כפר חבד"),
        ("עין הנצי''ב", "עין הנציב"),
        ("תקוע ד' וה'", "תקוע ד וה"),
    ]

    for left, right in variant_groups:
        assert normalize_city_key(left) == normalize_city_key(right)


def test_origin_imputation() -> None:
    assert normalize_origin(None) == ("UNKNOWN", True)
    assert normalize_origin("  ") == ("UNKNOWN", True)
    assert normalize_origin("Iran") == ("Iran", False)


def test_threat_type_mapping() -> None:
    assert threat_type_for_code(0) == "rocket_missile"
    assert threat_type_for_code(2) == "infiltration"
    assert threat_type_for_code(5) == "hostile_aircraft"
    assert threat_type_for_code(8) == "other"


def test_time_iso_conversions_include_timezone() -> None:
    parsed = parse_source_time("2026-03-01 12:00:00")
    assert parsed is not None
    local_iso = to_local_iso(parsed)
    utc_iso = to_utc_iso(parsed)
    assert local_iso.endswith("+02:00")
    assert utc_iso.endswith("+00:00")

