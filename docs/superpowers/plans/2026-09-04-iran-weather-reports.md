# Iran Weather Reports Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add reliable noon and nightly weather posts for all 31 Iranian provincial capitals.

**Architecture:** Add a focused weather service module that owns the 31-city catalog, Open-Meteo request/parsing, WMO labels, alerts, and Telegram text formatting. Wire it into the existing minute-polling agent with date-based once-per-day state gates so weather failures remain isolated from news/Truth/market processing.

**Tech Stack:** Python 3.12, requests, pytest, existing Telegram sender/state helpers, Open-Meteo Forecast API.

**Spec:** `docs/superpowers/specs/2026-09-04-iran-weather-reports-design.md`

## Global Constraints

- Cover exactly the capitals of all 31 provinces.
- Noon report: 12:00 Asia/Tehran, once per Tehran calendar date.
- Night report: 22:00 Asia/Tehran, once per Tehran calendar date.
- No API key or paid weather dependency.
- No invented weather facts or official-warning claims.
- Weather failure must not stop news, Truth Social, or markets.
- Existing market quiet hours and two-hour cadence remain unchanged.

---

### Task 1: Weather domain and Open-Meteo parser

**Files:**
- Create: `src/weather.py`
- Create: `tests/test_weather.py`

**Interfaces:**
- Produces: `PROVINCIAL_CAPITALS`, `WeatherCity`, `WeatherDay`, `WeatherReport`, `fetch_weather_report(session=requests)`, `weather_code_fa(code)`, `format_noon_weather(report)`, `format_night_weather(report)`.

- [ ] **Step 1: Write failing tests**

Add tests asserting `len(PROVINCIAL_CAPITALS) == 31`, unique province/city names, WMO mapping for clear/rain/snow/thunderstorm, parser handling of a representative multi-location Open-Meteo JSON payload, and alert thresholds.

- [ ] **Step 2: Run targeted tests to verify RED**

Run: `python -m pytest tests/test_weather.py -q`
Expected: FAIL because `src.weather` does not exist.

- [ ] **Step 3: Implement minimal weather module**

Use fixed WGS84 coordinates for the 31 provincial capitals. Request Open-Meteo `/v1/forecast` with comma-separated latitude/longitude and `timezone=Asia/Tehran`, `forecast_days=4`, current fields `temperature_2m,apparent_temperature,weather_code,wind_speed_10m` and daily fields `temperature_2m_max,temperature_2m_min,precipitation_probability_max,precipitation_sum,snowfall_sum,weather_code,wind_gusts_10m_max`.

Normalize a single-location dict or multi-location list into `WeatherReport` without fabricating missing values. Map WMO codes to concise Persian descriptions. Build deterministic alert strings from the thresholds in the spec.

- [ ] **Step 4: Run targeted tests to verify GREEN**

Run: `python -m pytest tests/test_weather.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

Commit message: `feat: add Iran provincial weather service`

---

### Task 2: Noon and night scheduling/state integration

**Files:**
- Modify: `src/main.py`
- Modify: `tests/test_main.py`

**Interfaces:**
- Consumes: `fetch_weather_report`, `format_noon_weather`, `format_night_weather`.
- Produces: `_weather_noon_due(state, now)`, `_weather_night_due(state, now)` and state keys `weather_noon_last_sent_date`, `weather_night_last_sent_date`.

- [ ] **Step 1: Write failing integration tests**

Add tests that at 12:00 Tehran noon weather sends once and a second cycle that day does not resend; at 22:00 Tehran night weather sends once; before each threshold nothing sends; and a weather exception leaves `run()` successful while other sections continue.

- [ ] **Step 2: Run integration tests to verify RED**

Run: `python -m pytest tests/test_main.py -q`
Expected: weather scheduling tests FAIL.

- [ ] **Step 3: Implement isolated scheduling**

After news processing and before/after markets without changing market logic, compute Tehran local date/hour. If noon/night is due, fetch one report, send the appropriate formatted Telegram message, then persist the corresponding last-sent date only after `send_telegram` returns successfully. Wrap weather processing in its own `try/except` and log `Weather error:` on failure.

- [ ] **Step 4: Run integration tests to verify GREEN**

Run: `python -m pytest tests/test_main.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

Commit message: `feat: schedule daily Iran weather posts`

---

### Task 3: Repair near-realtime regression and full verification

**Files:**
- Modify if needed: `tests/test_main.py`
- Modify if root-cause evidence requires: `src/main.py`

**Interfaces:**
- Preserve semantic duplicate suppression while proving the removed eight-story cap does not hold distinct breaking events.

- [ ] **Step 1: Reproduce the existing CI failure**

Run the failing test `test_more_than_eight_new_military_stories_are_not_held_for_later` and inspect which synthetic items are suppressed by `_same_story`.

- [ ] **Step 2: Fix the test fixture or production logic at the root cause**

If the synthetic stories are semantically duplicates under the intentional dedupe rule, change the fixture to nine genuinely distinct events with distinct token sets rather than weakening production dedupe. If real distinct events are being collapsed, tighten `_same_story` with a regression test before changing it.

- [ ] **Step 3: Run the complete suite**

Run: `python -m pytest -q`
Expected: all tests PASS.

- [ ] **Step 4: Verify workflow configuration**

Confirm `.github/workflows/agent.yml` still runs tests first, then `python -m src.main --monitor`, retains `workflow_dispatch`, the 5-minute schedule, and state persistence.

- [ ] **Step 5: Commit**

Commit message: `test: verify weather and realtime monitor behavior`

---

### Task 4: Fresh GitHub Actions verification

**Files:** none unless CI reveals a real defect.

- [ ] **Step 1: Run/observe a fresh workflow on the final commit**

Expected: tests green, near-realtime monitor step executes, state persistence completes.

- [ ] **Step 2: Inspect job logs**

Verify no weather import/runtime error, no failing tests, and monitor launches with the intended environment.

- [ ] **Step 3: Only then report completion**

Do not describe the weather subsystem as live until the fresh workflow is green.
