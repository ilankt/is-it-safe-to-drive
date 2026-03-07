const form = document.getElementById("risk-form");
const appShell = document.getElementById("app-shell");
const backButton = document.getElementById("back-btn");
const originInput = document.getElementById("origin-city");
const suggestionsBox = document.getElementById("city-suggestions");
const distanceRange = document.getElementById("distance-km");
const distanceNumber = document.getElementById("distance-km-number");
const departureInput = document.getElementById("departure-time");
const departureDaySelect = document.getElementById("departure-day");
const departureHourSelect = document.getElementById("departure-hour");
const departurePreview = document.getElementById("departure-preview");
const formError = document.getElementById("form-error");

const dial = document.getElementById("dial");
const dialValue = document.getElementById("dial-value");
const dialLabel = document.getElementById("dial-label");
const metaDuration = document.getElementById("meta-duration");
const metaArrival = document.getElementById("meta-arrival");
const metaAvgAlarms = document.getElementById("meta-avg-alarms");
const metaSafeHour = document.getElementById("meta-safe-hour");
const metaDangerHour = document.getElementById("meta-danger-hour");
const metaLastAlarm = document.getElementById("meta-last-alarm");
const explanation = document.getElementById("result-explanation");
const disclaimer = document.getElementById("result-disclaimer");

const cityState = {
  all: [],
  filtered: [],
  activeIndex: -1,
};

const departureState = {
  workdays: [],
  selectedDateIso: "",
};

function showFormView() {
  appShell.classList.remove("view-result");
  appShell.classList.add("view-form");
}

function showResultView() {
  appShell.classList.remove("view-form");
  appShell.classList.add("view-result");
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function isIsraeliWorkday(date) {
  const day = date.getDay();
  return day >= 0 && day <= 4;
}

function toIsoDate(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function addDays(date, days) {
  const next = new Date(date);
  next.setDate(next.getDate() + days);
  return next;
}

function toRoundHour(now) {
  const rounded = new Date(now);
  rounded.setSeconds(0, 0);
  if (rounded.getMinutes() > 0) {
    rounded.setHours(rounded.getHours() + 1);
  }
  rounded.setMinutes(0, 0, 0);
  return rounded;
}

function buildUpcomingWorkdays(start, count) {
  const days = [];
  let cursor = new Date(start);
  cursor.setHours(0, 0, 0, 0);

  while (days.length < count) {
    if (isIsraeliWorkday(cursor)) {
      days.push(new Date(cursor));
    }
    cursor = addDays(cursor, 1);
  }
  return days;
}

function fillDepartureDayOptions() {
  departureDaySelect.innerHTML = departureState.workdays
    .map((day) => {
      const iso = toIsoDate(day);
      const label = day.toLocaleDateString("he-IL", {
        weekday: "short",
        day: "2-digit",
        month: "short",
      });
      return `<option value="${iso}">${label}</option>`;
    })
    .join("");
}

function fillDepartureHours() {
  departureHourSelect.innerHTML = Array.from({ length: 24 }, (_, hour) => {
    const hh = String(hour).padStart(2, "0");
    return `<option value="${hour}">${hh}:00</option>`;
  }).join("");
}

function syncDepartureValue() {
  if (!departureState.selectedDateIso) {
    departureInput.value = "";
    departurePreview.textContent = "--";
    return;
  }

  const selectedHour = Number(departureHourSelect.value);
  if (!Number.isFinite(selectedHour)) {
    departureInput.value = "";
    departurePreview.textContent = "--";
    return;
  }

  const hh = String(selectedHour).padStart(2, "0");
  departureInput.value = `${departureState.selectedDateIso}T${hh}:00`;

  const previewDate = new Date(`${departureState.selectedDateIso}T${hh}:00`);
  departurePreview.textContent = previewDate.toLocaleString("he-IL", {
    weekday: "long",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function initDeparturePicker() {
  fillDepartureHours();

  const roundedNow = toRoundHour(new Date());
  let defaultDate = new Date(roundedNow);
  while (!isIsraeliWorkday(defaultDate)) {
    defaultDate = addDays(defaultDate, 1);
  }

  departureState.workdays = buildUpcomingWorkdays(defaultDate, 7);
  departureState.selectedDateIso = toIsoDate(defaultDate);
  fillDepartureDayOptions();
  departureDaySelect.value = departureState.selectedDateIso;
  departureHourSelect.value = String(defaultDate.getHours());

  syncDepartureValue();
}

function syncDistanceInputs(source) {
  if (source === "range") {
    distanceNumber.value = distanceRange.value;
  } else {
    const value = Math.max(1, Math.min(2000, Number(distanceNumber.value || 1)));
    distanceNumber.value = String(value);
    distanceRange.value = String(Math.max(1, Math.min(250, value)));
  }
}

function renderSuggestions() {
  if (cityState.filtered.length === 0) {
    suggestionsBox.classList.add("hidden");
    suggestionsBox.innerHTML = "";
    return;
  }

  suggestionsBox.innerHTML = cityState.filtered
    .map((name, idx) => {
      const cls = idx === cityState.activeIndex ? "suggestion-item active" : "suggestion-item";
      return `<div class="${cls}" data-index="${idx}" role="option">${name}</div>`;
    })
    .join("");
  suggestionsBox.classList.remove("hidden");
}

function filterCities() {
  const value = originInput.value.trim().toLowerCase();
  if (!value) {
    cityState.filtered = cityState.all.slice(0, 8);
    cityState.activeIndex = -1;
    renderSuggestions();
    return;
  }
  const starts = cityState.all.filter((name) => name.toLowerCase().startsWith(value));
  const contains = cityState.all.filter(
    (name) => name.toLowerCase().includes(value) && !starts.includes(name),
  );
  cityState.filtered = starts.concat(contains).slice(0, 10);
  cityState.activeIndex = -1;
  renderSuggestions();
}

function selectCity(name) {
  originInput.value = name;
  suggestionsBox.classList.add("hidden");
  cityState.filtered = [];
  cityState.activeIndex = -1;
}

function setDial(percentage, label) {
  const clamped = Math.max(0, Math.min(100, Number(percentage) || 0));
  const hue = 120 - (120 * clamped) / 100;
  dial.style.setProperty("--progress", String(clamped));
  dial.style.setProperty("--dial-color", `hsl(${hue}, 86%, 52%)`);
  dial.style.setProperty("--dial-glow", `hsla(${hue}, 92%, 58%, 0.22)`);
  dialValue.textContent = `${clamped}%`;
  dialLabel.textContent = label;
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

function setDatasetSummary(data) {
  metaAvgAlarms.textContent =
    Number.isFinite(data.avgAlarmsPerDay) ? data.avgAlarmsPerDay.toFixed(1) : "--";
  metaSafeHour.textContent = data.mostSafeHour || "--";
  metaDangerHour.textContent = data.mostDangerousHour || "--";
  metaLastAlarm.textContent = data.lastAlarmTime ? formatDate(data.lastAlarmTime) : "--";
}

async function loadCities() {
  const response = await fetch("/api/cities?limit=2000");
  const payload = await response.json();
  cityState.all = Array.isArray(payload.items) ? payload.items : [];
}

async function submitEstimate(event) {
  event.preventDefault();
  formError.classList.add("hidden");
  formError.textContent = "";

  syncDepartureValue();
  if (!departureInput.value) {
    formError.textContent = "נא לבחור שעת יציאה.";
    formError.classList.remove("hidden");
    return;
  }

  const selectedDeparture = new Date(departureInput.value);
  if (Number.isNaN(selectedDeparture.getTime())) {
    formError.textContent = "שעת היציאה אינה תקינה.";
    formError.classList.remove("hidden");
    return;
  }

  if (!isIsraeliWorkday(selectedDeparture)) {
    formError.textContent = "נא לבחור יום יציאה בין א׳-ה׳.";
    formError.classList.remove("hidden");
    return;
  }

  const payload = {
    originCity: originInput.value.trim(),
    distanceKm: Number(distanceNumber.value),
    departureTime: departureInput.value,
  };

  if (!payload.originCity) {
    formError.textContent = "נא לבחור עיר מוצא.";
    formError.classList.remove("hidden");
    return;
  }

  const button = document.getElementById("estimate-btn");
  button.disabled = true;
  button.textContent = "מחשב...";

  try {
    const response = await fetch("/api/estimate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "חישוב הסיכון נכשל.");
    }

    setDial(data.roundedPercentage, data.label);
    metaDuration.textContent = `${data.durationMinutes} דק׳`;
    metaArrival.textContent = formatDate(data.arrivalTime);
    setDatasetSummary(data);
    explanation.textContent = data.explanation;
    disclaimer.textContent = data.disclaimer;
    showResultView();
  } catch (error) {
    formError.textContent = error.message || "אירעה שגיאה.";
    formError.classList.remove("hidden");
  } finally {
    button.disabled = false;
    button.textContent = "חשב סיכון";
  }
}

function wireAutocompleteHandlers() {
  originInput.addEventListener("focus", filterCities);
  originInput.addEventListener("input", filterCities);

  originInput.addEventListener("keydown", (event) => {
    if (suggestionsBox.classList.contains("hidden")) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      cityState.activeIndex = Math.min(cityState.activeIndex + 1, cityState.filtered.length - 1);
      renderSuggestions();
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      cityState.activeIndex = Math.max(cityState.activeIndex - 1, 0);
      renderSuggestions();
    } else if (event.key === "Enter" && cityState.activeIndex >= 0) {
      event.preventDefault();
      selectCity(cityState.filtered[cityState.activeIndex]);
    } else if (event.key === "Escape") {
      suggestionsBox.classList.add("hidden");
    }
  });

  suggestionsBox.addEventListener("mousedown", (event) => {
    const el = event.target.closest(".suggestion-item");
    if (!el) return;
    const idx = Number(el.dataset.index);
    if (!Number.isNaN(idx) && cityState.filtered[idx]) {
      selectCity(cityState.filtered[idx]);
    }
  });

  document.addEventListener("click", (event) => {
    if (!event.target.closest(".field-wrap")) {
      suggestionsBox.classList.add("hidden");
    }
  });
}

function wireDistanceHandlers() {
  distanceRange.addEventListener("input", () => syncDistanceInputs("range"));
  distanceNumber.addEventListener("input", () => syncDistanceInputs("number"));
}

function wireDepartureHandlers() {
  departureDaySelect.addEventListener("change", () => {
    departureState.selectedDateIso = departureDaySelect.value;
    syncDepartureValue();
  });

  departureHourSelect.addEventListener("change", syncDepartureValue);
}

async function init() {
  initDeparturePicker();
  setDial(0, "ממתין");
  showFormView();
  wireDistanceHandlers();
  wireDepartureHandlers();
  wireAutocompleteHandlers();
  backButton.addEventListener("click", showFormView);
  form.addEventListener("submit", submitEstimate);

  try {
    await loadCities();
  } catch (error) {
    formError.textContent = "לא ניתן לטעון את רשימת הערים.";
    formError.classList.remove("hidden");
  }
}

init();
