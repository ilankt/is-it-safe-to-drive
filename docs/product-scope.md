# Product Scope (Phase 0, 2026 Conflict Slice)

## Scope Decision for This Iteration
For this rerun, risk modeling scope is limited to the late-February 2026 conflict window:
- `event_time >= 2026-02-28 10:10:20`
- data source: `alarms.csv`
- include all threat codes present in this window

This intentionally narrows the baseline from "all-history" to "2026 conflict-only".

Prepared data artifact for this scope:
- `data/alarms_2026_conflict_clean.csv`

## Product Claim (MVP)
The MVP estimates historical alarm risk during a planned drive, not real-time safety.

Approved wording:
- Primary: `Historical alarm risk during this drive`
- Supporting: `Based on historical alarms for the 2026 conflict window, by route location and time.`
- Disclaimer: `This is not a real-time warning system and not safety advice.`

## In-Scope User Inputs
- origin
- destination
- mode: `depart_at` or `arrive_by`
- date/time value

## In-Scope Alarm Definition (This Slice)
Threat codes observed in the filtered window:
- `0` rocket/missile
- `5` hostile aircraft/UAV
- `2` infiltration

Out of slice:
- `3` earthquake was not present in this filtered window
- `8` warning code was not present in this filtered window

Policy:
- include all observed threat codes in this window (`0`, `5`, `2`)
- keep threat handling configurable for future windows

## Geographic Resolution
MVP remains city-level only:
- map route samples to nearest city represented in dataset/coordinates
- avoid road-segment or polygon precision claims

## Time Rules
- treat raw source `time` as Israel local wall-clock values
- normalize to timezone-aware `Asia/Jerusalem` in ETL
- keep UTC derived field for computation consistency

For this conflict slice specifically, no DST ambiguity was detected.

## Data Rules Applied
1. Origin imputation
- If `origin` is null, set to `UNKNOWN`.
- Track with `origin_imputed=true`.

2. City normalization for modeling keys
- Keep `city_raw` for display.
- Use `city_norm` for grouping/joining/scoring.
- Use `city_canonical` when a single display label is needed.

## Canonical Event Schema
- `event_id: string`
- `source_id: number`
- `event_time_local: string` (ISO-8601, `Asia/Jerusalem`)
- `event_time_utc: string` (ISO-8601 UTC)
- `city_raw: string`
- `city_norm: string`
- `threat_code: number`
- `threat_type: rocket_missile | hostile_aircraft | infiltration | earthquake | other`
- `description_raw: string`
- `origin: string | null`
- `is_duplicate: boolean`
- `source_repo: string`
- `source_commit: string`

## MVP Outputs
- probability of at least one alarm during drive window
- rounded percentage (nearest 5%)
- bucket label (`Very Low`, `Low`, `Moderate`, `High`, `Very High`)
- short explanation + disclaimer

## Explicit Non-Goals
- no UI implementation in Phase 0
- no real-time alert ingestion
- no life-safety guarantees
- no military-event prediction
- no polygon-level exposure model yet

## Risks to Carry Into Phase 1
- conflict-only window may not generalize well outside this period
- raw source outside this cleaned artifact may still contain null `origin` and punctuation variants
