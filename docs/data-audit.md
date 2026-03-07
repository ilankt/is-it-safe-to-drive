# Data Audit (Phase 0, 2026 Conflict Slice)

## Scope
Audit target: `https://github.com/yuval-harpaz/alarms` (commit `acfc4e130ec62577b268deb6d81aa866f76e385f`, audited on 2026-03-07).

Primary source table: `data/alarms.csv`.

Filter applied for this rerun:
- `time >= 2026-02-28 10:10:20` (late-February 2026 conflict window used by upstream repo scripts).
- Include all threat codes present in this time window.

Cleaned Phase 0 artifact created:
- `data/alarms_2026_conflict_clean.csv`

## Raw Schema
Columns in the filtered source:
- `time` (string datetime, `%Y-%m-%d %H:%M:%S`)
- `cities` (place label)
- `threat` (integer code)
- `id` (source alarm id)
- `description` (text label)
- `origin` (nullable categorical source)

Filtered dataset size:
- Rows: `37,248`
- Unique cities: `1,450`
- Unique ids: `4,310`
- Time range: `2026-02-28 10:10:20` to `2026-03-07 17:39:11`

Cleaned artifact stats:
- Rows: `37,248`
- `origin` nulls after cleaning: `0`
- `origin='UNKNOWN'` rows: `19`
- Unique `city_raw`: `1,450`
- Unique `city_norm`: `1,449` (one punctuation-variant merge)

## Phase 0 Exit Checks

### 1) Sample 100-500 records and verify parse quality
- Random sample size: `300`
- Sample parse failures: `0`
- Full filtered table parse failures: `0`

Result: pass.

### 2) Confirm timezone handling
Evidence from upstream script `code/alarms3.py`:
- Input epochs are converted to Israel local time.
- CSV writes timezone-naive local timestamps.

Validation on filtered rows:
- `Asia/Jerusalem` localization ambiguous/nonexistent rows: `0`

Result: pass for this conflict slice.

### 3) Confirm city names can be normalized
Cross-check against `data/coord.csv`:
- Row coverage by exact city match: `100%`
- Unique-city coverage by exact city match: `100%`
- Normalization collisions in this slice: `1` key (`ג'ת` vs `גת`)

Result: pass.

### 4) Confirm event counts per city and per hour
Computed successfully.

- Distinct city buckets counted: `1,450`
- Hour buckets present: all `24` hours (0-23)

Top city counts in this slice (all near-equal barrage distribution):
- `67`: Petah Tikva, Holon, Givat Shmuel, Tel Aviv East, and others
- `66`: many nearby central-area locations

Result: pass.

## Threat Mix in 2026 Conflict Slice
- `threat=0` (rocket/missile): `35,861`
- `threat=5` (hostile aircraft): `1,385`
- `threat=2` (infiltration): `2`
- `threat=3`: `0`
- `threat=8`: `0`

Description consistency check:
- No threat/description mismatches found in this filtered slice.

## Data Quality Issues (Filtered Slice)
1. Comma-containing city labels
- `114` rows contain commas in `cities` (valid compound names).
- Impact: do not split `cities` by commas in ETL.

2. Global DST ambiguity still exists outside this slice
- Not present in the filtered range, but exists in older records.
- Impact: if model later expands time range, DST handling remains required.

## Applied Fixes
1. `origin` null handling
- Rule applied: null `origin` is imputed to `UNKNOWN`.
- Tracking field added: `origin_imputed` boolean.
- Result: `origin` null count reduced from `19` to `0`.

2. City punctuation normalization
- Raw city kept in `city_raw`.
- Deterministic normalized key added as `city_norm`:
  - trim/whitespace normalization
  - normalize quote/hyphen variants
  - remove quote/apostrophe punctuation from key
  - lowercase key
- Canonical label field added: `city_canonical` (most frequent raw variant per `city_norm`).
- Result: punctuation variant pair merged (`ג'ת` / `גת`), reducing unique keys by `1`.

## Canonical Event Schema (Phase 1 Input Contract)
- `event_id` (string): hash of `source_id + city_norm + event_time_local`
- `source_id` (integer): raw `id`
- `event_time_local` (string): ISO-8601 with `Asia/Jerusalem`
- `event_time_utc` (string): UTC ISO-8601
- `city_raw` (string): raw `cities`
- `city_norm` (string): normalized city key
- `threat_code` (integer): raw `threat`
- `threat_type` (enum): `rocket_missile | hostile_aircraft | infiltration | earthquake | other`
- `description_raw` (string): raw `description`
- `origin` (string|null): raw `origin`
- `is_duplicate` (boolean): duplicate marker from ETL rules
- `source_repo` (string): `yuval-harpaz/alarms`
- `source_commit` (string): commit hash

## Dedupe Recommendation for This Slice
No duplicate rows were detected by:
- exact row duplicate
- (`time`,`cities`,`threat`,`description`,`origin`)
- (`id`,`time`,`cities`)

Keep dedupe logic in pipeline anyway to stay safe when source updates.
