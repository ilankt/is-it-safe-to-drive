from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path

from src.lib.data.ingest import run_ingest


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_ingest_end_to_end_and_stability(tmp_path: Path) -> None:
    raw_path = Path(".tmp-alarms/data/alarms.csv")
    assert raw_path.exists(), "Raw dataset is required for Phase 1 tests."

    out1 = tmp_path / "run1"
    out2 = tmp_path / "run2"

    res1 = run_ingest(
        raw_csv_path=raw_path,
        output_dir=out1,
        source_repo="yuval-harpaz/alarms",
        source_commit="acfc4e130ec62577b268deb6d81aa866f76e385f",
    )
    res2 = run_ingest(
        raw_csv_path=raw_path,
        output_dir=out2,
        source_repo="yuval-harpaz/alarms",
        source_commit="acfc4e130ec62577b268deb6d81aa866f76e385f",
    )

    assert res1.normalized_events_path.exists()
    assert res1.city_lookup_path.exists()
    assert res1.aggregates_path.exists()
    assert res1.sqlite_path.exists()

    # Stable outputs across repeated runs.
    assert _digest(res1.normalized_events_path) == _digest(res2.normalized_events_path)
    assert _digest(res1.city_lookup_path) == _digest(res2.city_lookup_path)
    assert _digest(res1.aggregates_path) == _digest(res2.aggregates_path)

    normalized = json.loads(res1.normalized_events_path.read_text(encoding="utf-8"))
    city_lookup = json.loads(res1.city_lookup_path.read_text(encoding="utf-8"))
    aggregates = json.loads(res1.aggregates_path.read_text(encoding="utf-8"))

    assert len(normalized) > 0
    assert aggregates["summary"]["rows_in_conflict_window"] >= len(normalized)
    assert aggregates["summary"]["duplicates_dropped"] >= 0
    assert 0 <= aggregates["summary"]["duplicate_rate"] <= 1
    assert aggregates["summary"]["rows_with_coordinates"] == len(normalized)
    assert aggregates["summary"]["coordinate_row_coverage"] == 1.0

    # Conflict window filter is enforced.
    conflict_start = datetime.fromisoformat("2026-02-28T10:10:20")
    for event in normalized[:200]:
        event_local = datetime.fromisoformat(event["event_time_local"]).replace(tzinfo=None)
        assert event_local >= conflict_start

    # At least 10 known cities resolve consistently.
    known_cities = [
        "פתח תקווה",
        "חולון",
        "קריית אונו",
        "אור יהודה",
        "ראשון לציון - מזרח",
        "גבעת שמואל",
        "תל אביב - מזרח",
        "רמת גן - מערב",
        "בית דגן",
        "סביון",
    ]
    city_norm_sets: dict[str, set[str]] = {city: set() for city in known_cities}
    for event in normalized:
        raw = event["city_raw"]
        if raw in city_norm_sets:
            city_norm_sets[raw].add(event["city_norm"])

    for city in known_cities:
        assert len(city_norm_sets[city]) == 1, f"{city} did not resolve consistently"

    # Aggregates include complete hour bins.
    assert len(aggregates["events_by_hour_local"]) == 24
    assert set(aggregates["events_by_hour_local"].keys()) == {
        f"{hour:02d}" for hour in range(24)
    }

    # City lookup includes coordinates.
    lookup_with_coords = [row for row in city_lookup if row["lat"] is not None and row["lng"] is not None]
    assert len(lookup_with_coords) == len(city_lookup)

    # SQLite output exists and row count is stable with JSON output.
    connection = sqlite3.connect(res1.sqlite_path)
    try:
        row_count = connection.execute("SELECT COUNT(*) FROM normalized_events").fetchone()[0]
    finally:
        connection.close()
    assert row_count == len(normalized)
