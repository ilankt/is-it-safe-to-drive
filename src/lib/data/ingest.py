from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from src.lib.data.normalize import (
    CONFLICT_START_LOCAL,
    normalize_city_key,
    normalize_origin,
    parse_source_time,
    threat_type_for_code,
    to_local_iso,
    to_utc_iso,
)


@dataclass
class IngestResult:
    normalized_events_path: Path
    city_lookup_path: Path
    aggregates_path: Path
    sqlite_path: Path
    summary: dict[str, Any]


def _event_id(source_id: int, city_norm: str, local_iso: str) -> str:
    seed = f"{source_id}|{city_norm}|{local_iso}"
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()


def run_ingest(
    raw_csv_path: Path,
    output_dir: Path,
    source_repo: str,
    source_commit: str,
    conflict_start: datetime = CONFLICT_START_LOCAL,
    coord_csv_path: Path | None = None,
) -> IngestResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    if coord_csv_path is None:
        coord_csv_path = Path(".tmp-alarms/data/coord.csv")

    raw_rows = 0
    parse_failures = 0
    invalid_threat = 0
    filtered_in = 0
    duplicates_dropped = 0
    origin_imputed_rows = 0

    events: list[dict[str, Any]] = []
    city_raw_counts_by_norm: dict[str, Counter[str]] = defaultdict(Counter)
    seen_business_keys: set[tuple[Any, ...]] = set()

    with raw_csv_path.open("r", encoding="utf-8", newline="") as infile:
        reader = csv.DictReader(infile)
        for row in reader:
            raw_rows += 1

            parsed = parse_source_time((row.get("time") or "").strip())
            if parsed is None:
                parse_failures += 1
                continue
            if parsed < conflict_start:
                continue

            filtered_in += 1

            try:
                threat_code = int(str(row.get("threat", "")).strip())
            except ValueError:
                invalid_threat += 1
                continue

            source_id = int(str(row.get("id", "")).strip())
            city_raw = (row.get("cities") or "").strip()
            description_raw = (row.get("description") or "").strip()
            origin, was_imputed = normalize_origin(row.get("origin"))
            if was_imputed:
                origin_imputed_rows += 1

            business_key = (
                parsed.strftime("%Y-%m-%d %H:%M:%S"),
                city_raw,
                threat_code,
                description_raw,
                origin,
            )
            if business_key in seen_business_keys:
                duplicates_dropped += 1
                continue
            seen_business_keys.add(business_key)

            city_norm = normalize_city_key(city_raw)
            local_iso = to_local_iso(parsed)

            city_raw_counts_by_norm[city_norm][city_raw] += 1
            events.append(
                {
                    "event_id": _event_id(source_id, city_norm, local_iso),
                    "source_id": source_id,
                    "event_time_local": local_iso,
                    "event_time_utc": to_utc_iso(parsed),
                    "city_raw": city_raw,
                    "city_norm": city_norm,
                    "city_canonical": "",
                    "threat_code": threat_code,
                    "threat_type": threat_type_for_code(threat_code),
                    "description_raw": description_raw,
                    "origin": origin,
                    "origin_imputed": was_imputed,
                    "is_duplicate": False,
                    "source_repo": source_repo,
                    "source_commit": source_commit,
                }
            )

    city_canonical_by_norm: dict[str, str] = {}
    for city_norm, counter in city_raw_counts_by_norm.items():
        ranked = sorted(counter.items(), key=lambda item: (-item[1], item[0]))
        city_canonical_by_norm[city_norm] = ranked[0][0]

    for event in events:
        event["city_canonical"] = city_canonical_by_norm[event["city_norm"]]

    events.sort(
        key=lambda e: (
            e["event_time_local"],
            e["source_id"],
            e["city_raw"],
            e["threat_code"],
            e["origin"],
        )
    )

    events_by_city = Counter(event["city_norm"] for event in events)
    events_by_hour = Counter(
        int(event["event_time_local"][11:13]) for event in events
    )
    threat_code_counts = Counter(event["threat_code"] for event in events)
    threat_type_counts = Counter(event["threat_type"] for event in events)

    city_lookup = []
    coord_map: dict[str, tuple[float, float]] = {}
    if coord_csv_path.exists():
        with coord_csv_path.open("r", encoding="utf-8", newline="") as coord_file:
            coord_reader = csv.DictReader(coord_file)
            for row in coord_reader:
                loc = (row.get("loc") or "").strip()
                if not loc:
                    continue
                lat = float(str(row.get("lat", "")).strip())
                lng = float(str(row.get("long", "")).strip())
                coord_map[loc] = (lat, lng)

    rows_with_coords = 0
    for city_norm in sorted(city_raw_counts_by_norm):
        raw_counter = city_raw_counts_by_norm[city_norm]
        canonical = city_canonical_by_norm[city_norm]
        coords = coord_map.get(canonical)
        if coords is not None:
            rows_with_coords += sum(raw_counter.values())
        city_lookup.append(
            {
                "city_norm": city_norm,
                "city_canonical": canonical,
                "raw_variants": sorted(raw_counter.keys()),
                "row_count": sum(raw_counter.values()),
                "lat": None if coords is None else coords[0],
                "lng": None if coords is None else coords[1],
            }
        )

    normalized_events_path = output_dir / "alarms.normalized.json"
    city_lookup_path = output_dir / "city_lookup.json"
    aggregates_path = output_dir / "alarms.aggregates.json"
    sqlite_path = output_dir / "alarms.sqlite"

    normalized_events_path.write_text(
        json.dumps(events, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    city_lookup_path.write_text(
        json.dumps(city_lookup, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    if sqlite_path.exists():
        sqlite_path.unlink()
    connection = sqlite3.connect(sqlite_path)
    try:
        connection.execute(
            """
            CREATE TABLE normalized_events (
                event_id TEXT PRIMARY KEY,
                source_id INTEGER NOT NULL,
                event_time_local TEXT NOT NULL,
                event_time_utc TEXT NOT NULL,
                city_raw TEXT NOT NULL,
                city_norm TEXT NOT NULL,
                city_canonical TEXT NOT NULL,
                threat_code INTEGER NOT NULL,
                threat_type TEXT NOT NULL,
                description_raw TEXT NOT NULL,
                origin TEXT NOT NULL,
                origin_imputed INTEGER NOT NULL,
                is_duplicate INTEGER NOT NULL,
                source_repo TEXT NOT NULL,
                source_commit TEXT NOT NULL
            )
            """
        )
        rows = [
            (
                e["event_id"],
                e["source_id"],
                e["event_time_local"],
                e["event_time_utc"],
                e["city_raw"],
                e["city_norm"],
                e["city_canonical"],
                e["threat_code"],
                e["threat_type"],
                e["description_raw"],
                e["origin"],
                int(bool(e["origin_imputed"])),
                int(bool(e["is_duplicate"])),
                e["source_repo"],
                e["source_commit"],
            )
            for e in events
        ]
        connection.executemany(
            """
            INSERT INTO normalized_events (
                event_id, source_id, event_time_local, event_time_utc, city_raw, city_norm,
                city_canonical, threat_code, threat_type, description_raw, origin,
                origin_imputed, is_duplicate, source_repo, source_commit
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        connection.execute(
            "CREATE INDEX idx_events_city_norm_time ON normalized_events(city_norm, event_time_local)"
        )
        connection.execute(
            "CREATE INDEX idx_events_threat_time ON normalized_events(threat_code, event_time_local)"
        )
        connection.commit()
    finally:
        connection.close()

    denominator = filtered_in if filtered_in else 1
    summary = {
        "source_repo": source_repo,
        "source_commit": source_commit,
        "conflict_start_local": conflict_start.strftime("%Y-%m-%d %H:%M:%S"),
        "raw_rows": raw_rows,
        "rows_in_conflict_window": filtered_in,
        "parse_failures": parse_failures,
        "invalid_threat_rows": invalid_threat,
        "duplicates_dropped": duplicates_dropped,
        "duplicate_rate": duplicates_dropped / denominator,
        "origin_imputed_rows": origin_imputed_rows,
        "normalized_rows": len(events),
        "unique_city_raw": len({event["city_raw"] for event in events}),
        "unique_city_norm": len({event["city_norm"] for event in events}),
        "rows_with_coordinates": rows_with_coords,
        "coordinate_row_coverage": rows_with_coords / len(events) if events else 0.0,
    }

    aggregates = {
        "summary": summary,
        "events_by_city_norm": dict(sorted(events_by_city.items())),
        "events_by_hour_local": {
            f"{hour:02d}": events_by_hour.get(hour, 0) for hour in range(24)
        },
        "threat_code_counts": dict(sorted(threat_code_counts.items())),
        "threat_type_counts": dict(sorted(threat_type_counts.items())),
    }

    aggregates_path.write_text(
        json.dumps(aggregates, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return IngestResult(
        normalized_events_path=normalized_events_path,
        city_lookup_path=city_lookup_path,
        aggregates_path=aggregates_path,
        sqlite_path=sqlite_path,
        summary=summary,
    )
