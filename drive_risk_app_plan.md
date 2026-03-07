# Drive Risk App — Implementation Plan

## Goal
Build an MVP web app that estimates the **historical probability of receiving an alarm during a planned drive** in Israel, based on:
- origin
- destination
- planned departure or arrival time
- estimated driving duration
- historical alarm data by city / location / timestamp

> Recommended product wording: avoid claiming actual safety. Prefer:
> **"Historical alarm risk during this drive"** instead of **"Is it safe to drive?"**
>
> This should be presented as an informational probability estimate, not a life-safety guarantee.

---

## MVP Output
The app should:
1. accept start location and target location
2. accept either:
   - departure date/time, or
   - desired arrival date/time
3. calculate route duration
4. estimate alarm probability during the drive window
5. display:
   - rounded percentage (nearest 5%)
   - simple dial / gauge
   - label such as `Low`, `Moderate`, `High`, `Very High`
   - short explanatory text

Example:
- `Estimated historical alarm risk during this drive: 15%`
- `Moderate`
- `Based on historical alarms for this route, day, and time window.`

---

## Recommended MVP Stack
- **Frontend:** Next.js + TypeScript
- **UI:** simple one-page layout, Tailwind, one dial/gauge component
- **Backend:** Next.js API routes or small Node backend
- **Data storage:** start with local processed JSON / SQLite; move to Postgres later if needed
- **Routing provider:** Google Maps Platform Routes API
- **Location input:** Google Places Autocomplete or plain address + geocoding
- **Charts / gauge:** lightweight custom SVG or small React gauge component
- **Testing:** Vitest / Jest + Playwright
- **Deployment:** Vercel for app, server-side env vars for API keys

---

## Core Assumptions
1. Historical missile/alarm data exists in a GitHub repo and can be pulled or copied into your project.
2. Dataset contains at least:
   - timestamp
   - location / city
   - optional metadata such as region, alarm type, source
3. MVP can use **historical probability** only.
4. MVP does **not** try to predict military events in real time.
5. Route-based risk will initially be an approximation if the data is city-based and not road-segment / polygon-based.

---

## Risk Model — Recommended MVP Logic

### Basic idea
The app should estimate:

**Probability of at least one alarm occurring during the drive window along the planned route.**

### MVP statistical approach
Use a **baseline historical frequency model**:
1. take the planned route
2. estimate time spent along route segments
3. map route points / segments to nearby cities or alert areas available in the dataset
4. for each segment time window, estimate alarm frequency from historical data for:
   - that city / area
   - similar time of day
   - similar day of week
   - optional recency window
5. combine segment probabilities into one route probability

### Combination formula
If route is split into small intervals with per-interval probability `p_i`, then:

`P(at least one alarm on drive) = 1 - Π(1 - p_i)`

This is a practical MVP approach.

### Simplified first version
Before doing full segment logic, start with:
- origin city risk
- destination city risk
- optionally 1–3 sampled points along the route

Then combine those to produce a coarse route score.

### Important limitation
If the dataset is only by city, the route model is approximate. In a later phase you can improve it by using:
- official alert zones
- polygons
- spatial clustering
- road-segment exposure

---

## Risk Buckets
Round probability to nearest 5% and label it:

- `0–5%` → Very Low
- `10–20%` → Low
- `25–40%` → Moderate
- `45–60%` → High
- `65%+` → Very High

These thresholds are product choices, so keep them configurable.

---

## System Architecture

### Inputs
- origin
- destination
- date/time mode:
  - leave at
  - arrive by
- date/time value

### Processing
1. geocode locations
2. fetch route and duration
3. derive departure and arrival timestamps
4. sample route points over time
5. map route samples to dataset locations
6. compute per-sample historical alarm probability
7. combine to final score
8. round and label result

### Outputs
- percentage
- label
- dial / gauge
- duration
- short caveat

---

## Phase Plan

## Phase 0 — Scope, Data Audit, and Product Rules
### Objective
Lock the exact MVP behavior before writing real code.

### Tasks
- inspect the GitHub dataset structure
- document fields, missing values, timezone, city naming, duplicates
- define one canonical schema
- define whether app uses:
  - departure time input
  - arrival time input
  - or both
- define risk wording and disclaimer text
- define what counts as an alarm event
- define the geographic resolution:
  - city only
  - region
  - alert area

### Deliverables
- `docs/data-audit.md`
- `docs/product-scope.md`
- canonical event schema

### Tests / Exit Criteria
- sample 100–500 records manually and verify parse quality
- confirm timezone handling is correct
- confirm city names can be normalized
- confirm you can compute event counts per city and per hour

### Result of Phase
You know exactly what the dataset can support and what the MVP should claim.

---

## Phase 1 — Data Pipeline and Normalization
### Objective
Create a repeatable ingestion pipeline for alarm history.

### Tasks
- pull or copy raw dataset from GitHub
- build ETL script:
  - parse timestamps
  - normalize city names
  - remove duplicates
  - handle bad rows
- store normalized events in JSON or SQLite
- create lookup tables:
  - city → normalized name
  - city → coordinates if available
- generate summary aggregates:
  - events by city
  - events by weekday
  - events by hour block

### Suggested files
- `scripts/ingest-alarms.ts`
- `data/alarms.normalized.json`
- `data/alarms.sqlite`
- `src/lib/data/normalize.ts`

### Tests / Exit Criteria
- ingestion runs end-to-end from raw source to normalized output
- duplicate rate is measured
- at least 10 known cities resolve consistently
- unit tests cover date parsing and city normalization
- aggregate counts remain stable across repeated runs

### Result of Phase
Reliable normalized historical dataset ready for scoring.

---

## Phase 2 — Route and Geocoding Integration
### Objective
Get trusted route duration and route geometry.

### Tasks
- implement origin / destination input
- geocode text input or use place autocomplete
- call routing API from backend only
- return:
  - route duration
  - distance
  - polyline or sampled points
  - departure and arrival timestamps
- support both:
  - leave at X
  - arrive by Y

### Suggested files
- `src/app/api/route/route.ts`
- `src/lib/maps/geocode.ts`
- `src/lib/maps/computeRoute.ts`
- `src/types/route.ts`

### Tests / Exit Criteria
- can resolve 5–10 real address pairs in Israel
- route duration is returned consistently
- invalid / ambiguous addresses fail gracefully
- API key remains server-side only
- integration test verifies route response schema

### Result of Phase
App can compute a real planned drive window.

---

## Phase 3 — Historical Risk Engine (Single Location Baseline)
### Objective
Build the first probability engine without route segmentation.

### Tasks
- given one city and a planned time window:
  - compute historical event frequency
  - optionally condition on weekday and hour bin
- define a baseline probability model, for example:
  - all-history average
  - rolling 90-day weighting
  - weekday + hour smoothing
- expose function:
  - `estimateLocationRisk({ city, startTime, durationMinutes })`

### Notes
Start simple. Do **not** overfit early.
A robust baseline is better than a fragile sophisticated model.

### Suggested files
- `src/lib/risk/locationRisk.ts`
- `src/lib/risk/timeBuckets.ts`
- `src/lib/risk/smoothing.ts`

### Tests / Exit Criteria
- risk engine returns stable outputs for known test cases
- probabilities are bounded between 0 and 1
- sparse-data cities fall back gracefully to broader region/global baseline
- snapshot tests validate known example outputs

### Result of Phase
You have a working and explainable probability engine.

---

## Phase 4 — Route Risk Engine (MVP Route Approximation)
### Objective
Extend the model from a single city to a planned route.

### Tasks
- sample points along route by time, not just distance
- map each point to nearest supported city / area
- estimate risk for each sampled interval
- combine interval probabilities into one total probability
- add configurable parameters:
  - sample interval, e.g. every 5 minutes
  - nearest-city radius
  - fallback behavior if no city match

### MVP implementation options
#### Option A — Very simple
- origin + destination only
- average or combine their risks

#### Option B — Better MVP
- origin + destination + midpoint + 1–2 extra route samples

#### Option C — Best MVP before spatial polygons
- sample every N minutes along route
- nearest city matching
- combined probability across samples

### Tests / Exit Criteria
- longer routes generally increase exposure when all else is equal
- route through higher-risk areas produces higher score than route through lower-risk areas
- no duplicated route samples explode the probability
- probability combination logic is unit-tested

### Result of Phase
You now have the main feature: route-aware historical alarm risk.

---

## Phase 5 — UI / UX One-Pager
### Objective
Build the simple public-facing experience.

### Tasks
- one-page form with:
  - origin
  - destination
  - leave at / arrive by selector
  - date/time picker
- submit button
- results card with:
  - rounded percentage
  - dial / gauge
  - label
  - route duration
  - short methodology note
- loading, empty, and error states
- mobile-friendly layout

### Suggested UI blocks
- top title
- short disclaimer
- input card
- result dial
- “how this is estimated” collapsible section

### Tests / Exit Criteria
- full flow works on desktop and mobile sizes
- invalid input states are understandable
- result loads within acceptable time
- Playwright test covers end-to-end happy path

### Result of Phase
Usable MVP with clear result presentation.

---

## Phase 6 — Calibration, Sanity Checks, and Product Hardening
### Objective
Prevent misleading outputs.

### Tasks
- review outputs on many known cities/routes
- inspect whether probabilities are too low or too high
- tune smoothing, fallback logic, and bucket thresholds
- add explicit caveats:
  - historical estimate only
  - not real-time warning
  - not safety advice
- log route/risk requests for debugging
- add rate limiting if public

### Tests / Exit Criteria
- manual review of 20–50 scenarios
- no obviously nonsensical outputs
- sparse-data routes still return sane values
- disclaimer is visible and clear

### Result of Phase
MVP becomes safe to publish as an informational tool.

---

## Phase 7 — Deploy and Monitor
### Objective
Ship the first working version.

### Tasks
- deploy to Vercel or equivalent
- configure env vars
- configure API quotas/billing alerts
- add basic analytics
- add error logging
- document local setup for future agent-assisted coding

### Deliverables
- production URL
- `README.md`
- `.env.example`
- deployment notes

### Tests / Exit Criteria
- production route calculation works
- production scoring works
- environment setup is reproducible on fresh machine
- no exposed secrets in frontend bundle

### Result of Phase
Public MVP is live.

---

## Recommended Testing Strategy

### Unit tests
Test:
- date/time parsing
- city normalization
- route-to-sample conversion
- probability combination
- fallback logic
- bucket labeling

### Integration tests
Test:
- route API response parsing
- end-to-end risk calculation for fixed sample inputs
- dataset ingestion pipeline

### End-to-end tests
Test:
- user enters addresses
- user selects departure time
- app returns dial + percentage + label
- error states behave correctly

### Manual test scenarios
Use a sheet of expected cases:
- same city, short drive
- long intercity drive
- route during historically quiet hour
- route during historically active hour
- invalid location
- sparse-data city

---

## Suggested Folder Structure
```text
/src
  /app
    /api
      /route
      /risk
  /components
    Dial.tsx
    RouteForm.tsx
    ResultCard.tsx
  /lib
    /maps
    /risk
    /data
  /types
/scripts
/data
/docs
/tests
```

---

## Suggested API Contracts

### `POST /api/route`
Input:
```json
{
  "origin": "Ra'anana",
  "destination": "Tel Aviv",
  "mode": "depart_at",
  "datetime": "2026-03-08T07:30:00+02:00"
}
```

Response:
```json
{
  "durationMinutes": 28,
  "distanceMeters": 21500,
  "departureTime": "2026-03-08T07:30:00+02:00",
  "arrivalTime": "2026-03-08T07:58:00+02:00",
  "routeSamples": [
    { "lat": 32.18, "lng": 34.87, "timestamp": "..." }
  ]
}
```

### `POST /api/risk`
Input:
```json
{
  "routeSamples": [
    { "lat": 32.18, "lng": 34.87, "timestamp": "2026-03-08T07:35:00+02:00" }
  ]
}
```

Response:
```json
{
  "rawProbability": 0.17,
  "roundedProbability": 0.15,
  "percentage": 15,
  "label": "Moderate",
  "explanation": "Historical alarm risk estimate for this route and time window"
}
```

---

## Important Product Risks
1. **Life-safety framing risk** — do not imply true safety.
2. **Data quality risk** — city names, duplicates, missing timestamps.
3. **Spatial mismatch risk** — city data is weaker than alert polygons.
4. **Model credibility risk** — users may overtrust the number.
5. **API cost risk** — route/geocoding calls can add up.
6. **Latency risk** — autocomplete + routing + scoring must stay responsive.

---

## Recommended Non-Goals for MVP
Do not include yet:
- real-time Home Front Command alerts
- push notifications
- user accounts
- saved commutes
- route alternatives comparison
- machine learning forecasting
- military-event prediction

These can be later phases.

---

## V2 Ideas
After MVP works, consider:
- compare multiple departure times on same day
- “best departure window” chart
- saved commute presets
- use polygons / official alert areas instead of city proxies
- live alert overlay
- confidence score based on data density
- explanation panel showing which locations contributed most to risk

---

## Final Expected Result
At the end of the MVP, you should have:
- a working one-page web app
- route duration based on a real routing provider
- historical alarm-risk estimate for a chosen drive window
- a clear % result and dial
- a disclaimer that avoids overstating safety
- tests covering ingestion, routing, scoring, and UI
- deployment-ready codebase that an agentic coding tool can implement phase by phase

---

## Recommended Build Order Summary
1. data audit
2. normalization pipeline
3. route integration
4. single-location risk engine
5. route risk engine
6. UI one-pager
7. calibration and disclaimers
8. deploy

```

