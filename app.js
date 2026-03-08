/* ══════════════════════════════════════════════════════════
   Config
   ══════════════════════════════════════════════════════════ */

const DATA_BASE =
  "https://raw.githubusercontent.com/yuval-harpaz/alarms/master/data/";
const DATA_URL = DATA_BASE + "alarms.csv";
const COORD_URL = DATA_BASE + "coord.csv";
const ROAD_FACTOR = 1.2; // straight-line → road distance multiplier
const CONFLICT_START = new Date("2026-02-28T10:10:20");
const INCLUDE_THREATS = new Set([0, 2, 5]);
// JS getDay(): Sun=0 … Sat=6   →  working days Sun-Thu = 0,1,2,3,4
const WORKING_DAYS = new Set([0, 1, 2, 3, 4]);

/* ── State ── */
let DATA = null;
let COORDS = {}; // { cityName: { lat, lng } }

/* ── DOM refs ── */
const form = document.getElementById("risk-form");
const appShell = document.getElementById("app-shell");
const backButton = document.getElementById("back-btn");
const originInput = document.getElementById("origin-city");
const originSuggestionsBox = document.getElementById("city-suggestions");
const destInput = document.getElementById("dest-city");
const destSuggestionsBox = document.getElementById("dest-suggestions");
const departureHourSelect = document.getElementById("departure-hour");
const formError = document.getElementById("form-error");

const dial = document.getElementById("dial");
const dialValue = document.getElementById("dial-value");
const dialLabel = document.getElementById("dial-label");
const metaDuration = document.getElementById("meta-duration");
const metaArrival = document.getElementById("meta-arrival");
const metaDistance = document.getElementById("meta-distance");
const metaSafeHour = document.getElementById("meta-safe-hour");
const metaDangerHour = document.getElementById("meta-danger-hour");
const metaLastAlarm = document.getElementById("meta-last-alarm");

/* ══════════════════════════════════════════════════════════
   Data loading & aggregation  (fetched live, processed in browser)
   ══════════════════════════════════════════════════════════ */

function countWorkingDayMinutes(start, end) {
  let total = 0;
  const cursor = new Date(start);
  while (cursor < end) {
    if (WORKING_DAYS.has(cursor.getDay())) {
      const nextMidnight = new Date(cursor);
      nextMidnight.setHours(24, 0, 0, 0);
      const boundary = nextMidnight < end ? nextMidnight : end;
      total += (boundary - cursor) / 60000;
    }
    cursor.setHours(24, 0, 0, 0);
  }
  return Math.max(total, 1);
}

function buildAggregates(rows) {
  const eventsByCity = {};
  const eventsByHour = new Array(24).fill(0);
  const eventsByCityHour = {};
  const lastEventByCity = {};
  const citySet = new Set();
  let earliest = null;
  let latest = null;
  let total = 0;

  for (const row of rows) {
    const threat = parseInt(row.threat, 10);
    if (!INCLUDE_THREATS.has(threat)) continue;

    const ts = new Date(row.time.replace(" ", "T"));
    if (isNaN(ts.getTime()) || ts < CONFLICT_START) continue;
    if (!WORKING_DAYS.has(ts.getDay())) continue;

    const city = (row.cities || "").trim();
    if (!city) continue;

    total++;
    citySet.add(city);
    eventsByCity[city] = (eventsByCity[city] || 0) + 1;

    const hour = ts.getHours();
    eventsByHour[hour]++;

    if (!eventsByCityHour[city]) eventsByCityHour[city] = new Array(24).fill(0);
    eventsByCityHour[city][hour]++;

    if (!earliest || ts < earliest) earliest = ts;
    if (!latest || ts > latest) latest = ts;

    const prev = lastEventByCity[city];
    if (!prev || ts > prev) lastEventByCity[city] = ts;
  }

  const cities = Array.from(citySet).sort();
  const observationMinutes = countWorkingDayMinutes(earliest, latest);

  const lastEventIso = {};
  for (const [city, dt] of Object.entries(lastEventByCity)) {
    lastEventIso[city] = dt.toISOString();
  }

  return {
    meta: {
      totalEvents: total,
      observationMinutes,
      uniqueCityCount: cities.length,
    },
    cities,
    eventsByCity,
    eventsByHour,
    eventsByCityHour,
    lastEventByCity: lastEventIso,
  };
}

async function loadData() {
  return new Promise((resolve, reject) => {
    Papa.parse(DATA_URL, {
      download: true,
      header: true,
      skipEmptyLines: true,
      complete: (results) => resolve(buildAggregates(results.data)),
      error: (err) => reject(err),
    });
  });
}

async function loadCoords() {
  return new Promise((resolve, reject) => {
    Papa.parse(COORD_URL, {
      download: true,
      header: true,
      skipEmptyLines: true,
      complete: (results) => {
        const coords = {};
        for (const row of results.data) {
          const name = (row.loc || "").trim();
          const lat = parseFloat(row.lat);
          const lng = parseFloat(row.long);
          if (name && !isNaN(lat) && !isNaN(lng)) {
            coords[name] = { lat, lng };
          }
        }
        resolve(coords);
      },
      error: (err) => reject(err),
    });
  });
}

function haversineKm(lat1, lon1, lat2, lon2) {
  const R = 6371;
  const toRad = (d) => (d * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

/* ══════════════════════════════════════════════════════════
   Statistical Model  (Poisson with smoothed hour factors)
   ══════════════════════════════════════════════════════════ */

function blendedCityRate(cityCount, observationMinutes, globalRate, minEvents) {
  if (observationMinutes <= 0 || cityCount <= 0) return globalRate;
  const cityRate = cityCount / observationMinutes;
  const weight = cityCount / (cityCount + Math.max(minEvents, 1));
  return weight * cityRate + (1 - weight) * globalRate;
}

function smoothedMultiplier(bucketCount, totalCount, numBuckets, pseudoCount) {
  if (numBuckets <= 0 || totalCount <= 0) return 1.0;
  const pseudo = Math.max(pseudoCount, 0);
  const prob = (bucketCount + pseudo) / (totalCount + numBuckets * pseudo);
  return prob * numBuckets;
}

function allocateMinutesByHour(startHour, durationMinutes) {
  if (durationMinutes <= 0) return {};
  const buckets = {};
  let remaining = durationMinutes;
  let h = startHour;
  while (remaining > 0) {
    const chunk = Math.min(remaining, 60);
    buckets[h] = (buckets[h] || 0) + chunk;
    remaining -= chunk;
    h = (h + 1) % 24;
  }
  return buckets;
}

function estimateRisk(originCity, destCity, startHour, distanceKm) {
  const durationMinutes = Math.ceil(distanceKm);
  const globalRate =
    DATA.meta.totalEvents /
    (DATA.meta.observationMinutes * Math.max(DATA.meta.uniqueCityCount, 1));

  const originCount = DATA.eventsByCity[originCity] || 0;
  const destCount = DATA.eventsByCity[destCity] || 0;

  const originRate = blendedCityRate(originCount, DATA.meta.observationMinutes, globalRate, 20);
  const destRate = blendedCityRate(destCount, DATA.meta.observationMinutes, globalRate, 20);
  const routeRate = (originRate + destRate) / 2;

  const hourAlloc = allocateMinutesByHour(startHour, durationMinutes);
  let hourFactor = 0;
  for (const [h, minutes] of Object.entries(hourAlloc)) {
    const mult = smoothedMultiplier(
      DATA.eventsByHour[Number(h)],
      DATA.meta.totalEvents,
      24,
      5.0,
    );
    hourFactor += mult * (minutes / durationMinutes);
  }

  const expected = routeRate * durationMinutes * hourFactor;
  const probability = Math.max(0, Math.min(1, 1 - Math.exp(-expected)));

  return { probability, expected, durationMinutes, distanceKm, originCount, destCount };
}

/* ══════════════════════════════════════════════════════════
   UI helpers
   ══════════════════════════════════════════════════════════ */

function riskLabel(pct) {
  if (pct <= 5) return "נמוך מאוד";
  if (pct <= 20) return "נמוך";
  if (pct <= 40) return "בינוני";
  if (pct <= 60) return "גבוה";
  return "גבוה מאוד";
}

function showView(name) {
  appShell.classList.remove("view-form", "view-result", "view-about");
  appShell.classList.add("view-" + name);
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function showFormView() { showView("form"); }
function showResultView() { showView("result"); }
function showAboutView() { showView("about"); }

function setDial(percentage, label) {
  const clamped = Math.max(0, Math.min(100, Number(percentage) || 0));
  const hue = 120 - (120 * clamped) / 100;
  dial.style.setProperty("--progress", String(clamped));
  dial.style.setProperty("--dial-color", `hsl(${hue}, 86%, 52%)`);
  dial.style.setProperty("--dial-glow", `hsla(${hue}, 92%, 58%, 0.22)`);
  dialValue.textContent = `${clamped}%`;
  dialLabel.textContent = label;
}

function formatHourRange(hour) {
  const next = (hour + 1) % 24;
  return `${String(hour).padStart(2, "0")}:00-${String(next).padStart(2, "0")}:00`;
}

function formatTime(hour, minute) {
  return `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;
}

function formatDate(iso) {
  const date = new Date(iso);
  return date.toLocaleString("he-IL", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function findMinHour(counts) {
  let best = 0;
  for (let h = 1; h < 24; h++) {
    if (counts[h] < counts[best]) best = h;
  }
  return best;
}

function findMaxHour(counts) {
  let best = 0;
  for (let h = 1; h < 24; h++) {
    if (counts[h] > counts[best]) best = h;
  }
  return best;
}

/* ══════════════════════════════════════════════════════════
   Autocomplete (reusable factory)
   ══════════════════════════════════════════════════════════ */

function makeAutocomplete(inputEl, suggestionsEl) {
  const state = { all: [], filtered: [], activeIndex: -1 };

  function render() {
    if (state.filtered.length === 0) {
      suggestionsEl.classList.add("hidden");
      suggestionsEl.innerHTML = "";
      return;
    }
    suggestionsEl.innerHTML = state.filtered
      .map((name, idx) => {
        const cls = idx === state.activeIndex ? "suggestion-item active" : "suggestion-item";
        return `<div class="${cls}" data-index="${idx}" role="option">${name}</div>`;
      })
      .join("");
    suggestionsEl.classList.remove("hidden");
  }

  function filter() {
    const value = inputEl.value.trim().toLowerCase();
    if (!value) {
      state.filtered = state.all.slice(0, 8);
      state.activeIndex = -1;
      render();
      return;
    }
    const starts = state.all.filter((n) => n.toLowerCase().startsWith(value));
    const contains = state.all.filter(
      (n) => n.toLowerCase().includes(value) && !starts.includes(n),
    );
    state.filtered = starts.concat(contains).slice(0, 10);
    state.activeIndex = -1;
    render();
  }

  function select(name) {
    inputEl.value = name;
    suggestionsEl.classList.add("hidden");
    state.filtered = [];
    state.activeIndex = -1;
  }

  inputEl.addEventListener("focus", filter);
  inputEl.addEventListener("input", filter);

  inputEl.addEventListener("keydown", (e) => {
    if (suggestionsEl.classList.contains("hidden")) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      state.activeIndex = Math.min(state.activeIndex + 1, state.filtered.length - 1);
      render();
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      state.activeIndex = Math.max(state.activeIndex - 1, 0);
      render();
    } else if (e.key === "Enter" && state.activeIndex >= 0) {
      e.preventDefault();
      select(state.filtered[state.activeIndex]);
    } else if (e.key === "Escape") {
      suggestionsEl.classList.add("hidden");
    }
  });

  suggestionsEl.addEventListener("mousedown", (e) => {
    const el = e.target.closest(".suggestion-item");
    if (!el) return;
    const idx = Number(el.dataset.index);
    if (!Number.isNaN(idx) && state.filtered[idx]) select(state.filtered[idx]);
  });

  return {
    setItems(items) { state.all = items; },
    getValue() { return inputEl.value.trim(); },
  };
}

let originAC, destAC;

/* ══════════════════════════════════════════════════════════
   Hour selector
   ══════════════════════════════════════════════════════════ */

function fillDepartureHours() {
  departureHourSelect.innerHTML = Array.from({ length: 24 }, (_, hour) => {
    const hh = String(hour).padStart(2, "0");
    return `<option value="${hour}">${hh}:00</option>`;
  }).join("");

  const now = new Date();
  let defaultHour = now.getHours();
  if (now.getMinutes() > 0) defaultHour = (defaultHour + 1) % 24;
  departureHourSelect.value = String(defaultHour);
}

/* ══════════════════════════════════════════════════════════
   Submit
   ══════════════════════════════════════════════════════════ */

function showError(msg) {
  formError.textContent = msg;
  formError.classList.remove("hidden");
}

function handleSubmit(event) {
  event.preventDefault();
  formError.classList.add("hidden");
  formError.textContent = "";

  if (!DATA) { showError("הנתונים עדיין לא נטענו. נסו שוב."); return; }

  const origin = originAC.getValue();
  const dest = destAC.getValue();

  if (!origin) { showError("נא לבחור עיר מוצא."); return; }
  if (!dest) { showError("נא לבחור עיר יעד."); return; }
  if (!COORDS[origin]) { showError("עיר המוצא לא נמצאה בנתוני הקואורדינטות."); return; }
  if (!COORDS[dest]) { showError("עיר היעד לא נמצאה בנתוני הקואורדינטות."); return; }

  const straightKm = haversineKm(
    COORDS[origin].lat, COORDS[origin].lng,
    COORDS[dest].lat, COORDS[dest].lng,
  );
  const distanceKm = Math.round(straightKm * ROAD_FACTOR);

  if (distanceKm < 1) { showError("עיר המוצא ועיר היעד זהות."); return; }

  const startHour = Number(departureHourSelect.value);

  const result = estimateRisk(origin, dest, startHour, distanceKm);
  const rawPct = result.probability * 100;
  const roundedPct = Math.max(0, Math.min(100, Math.round(rawPct)));
  const label = riskLabel(roundedPct);

  setDial(roundedPct, label);

  metaDuration.textContent = `${result.durationMinutes} דק׳`;
  const arrivalTotal = startHour * 60 + result.durationMinutes;
  const arrivalH = Math.floor(arrivalTotal / 60) % 24;
  const arrivalM = arrivalTotal % 60;
  metaArrival.textContent = formatTime(arrivalH, arrivalM);

  metaDistance.textContent = `${distanceKm} ק״מ`;

  // safe/danger hours: merge origin + dest alarm profiles
  const originHours = DATA.eventsByCityHour[origin] || new Array(24).fill(0);
  const destHours = DATA.eventsByCityHour[dest] || new Array(24).fill(0);
  const combinedHours = originHours.map((v, i) => v + destHours[i]);
  const combinedTotal = combinedHours.reduce((a, b) => a + b, 0);
  if (combinedTotal > 0) {
    metaSafeHour.textContent = formatHourRange(findMinHour(combinedHours));
    metaDangerHour.textContent = formatHourRange(findMaxHour(combinedHours));
  } else {
    metaSafeHour.textContent = "--";
    metaDangerHour.textContent = "--";
  }

  // last alarm: most recent between origin and dest
  const lastOrigin = DATA.lastEventByCity[origin];
  const lastDest = DATA.lastEventByCity[dest];
  const lastAlarm = [lastOrigin, lastDest]
    .filter(Boolean)
    .sort((a, b) => new Date(b) - new Date(a))[0];
  metaLastAlarm.textContent = lastAlarm ? formatDate(lastAlarm) : "--";

  showResultView();
}

/* ══════════════════════════════════════════════════════════
   Init
   ══════════════════════════════════════════════════════════ */

async function init() {
  fillDepartureHours();
  setDial(0, "ממתין");
  showFormView();

  originAC = makeAutocomplete(originInput, originSuggestionsBox);
  destAC = makeAutocomplete(destInput, destSuggestionsBox);

  // Close all suggestion boxes when clicking outside
  document.addEventListener("click", (e) => {
    if (!e.target.closest(".field-wrap")) {
      originSuggestionsBox.classList.add("hidden");
      destSuggestionsBox.classList.add("hidden");
    }
  });

  backButton.addEventListener("click", showFormView);
  document.getElementById("about-btn").addEventListener("click", showAboutView);
  document.getElementById("about-back-btn").addEventListener("click", showFormView);
  form.addEventListener("submit", handleSubmit);

  const btn = document.getElementById("estimate-btn");
  btn.disabled = true;
  btn.textContent = "טוען נתונים...";

  try {
    const [data, coords] = await Promise.all([loadData(), loadCoords()]);
    DATA = data;
    COORDS = coords;

    // Autocomplete shows cities that have coordinates
    const coordCities = Object.keys(COORDS).sort();
    originAC.setItems(coordCities);
    destAC.setItems(coordCities);

    btn.disabled = false;
    btn.textContent = "חשב סיכון";
  } catch (error) {
    formError.textContent = "לא ניתן לטעון את נתוני האזעקות.";
    formError.classList.remove("hidden");
    btn.textContent = "חשב סיכון";
    btn.disabled = false;
  }
}

init();
