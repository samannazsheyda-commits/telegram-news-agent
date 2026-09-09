# Bikhabar Command Center War Room Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the existing Flask panel into a production-ready Persian RTL War Room with live news, operational controls, diagnostics, modules, alerts, and PWA support.

**Architecture:** Keep the existing Flask + Jinja + vanilla JavaScript stack and extend the existing `panel/command_center.py` API rather than rewriting the app. The dashboard remains server-rendered for auth/reliability while small JSON endpoints and periodic fetches provide live operational behavior. Static CSS/JS carry the visual system and PWA shell.

**Tech Stack:** Python 3.12, Flask 3.1, Flask-WTF/CSRF, Jinja2, vanilla JS, CSS, pytest, systemd-backed VPS agent.

**Spec:** `docs/superpowers/specs/2026-09-09-command-center-war-room-design.md`

## Global Constraints
- VPS is the only production runtime.
- Preserve existing admin auth and CSRF.
- Never expose secrets in HTML, JavaScript, manifest, or JSON endpoints.
- Live feed refresh remains 3 seconds; operational status refresh remains 5 seconds.
- Doran is the first CSS font family only when an authorized asset exists; no external font CDN.
- Breaking priorities: missiles from Iran, missiles into Iran, explosions, direct attacks, Strait of Hormuz, drones, ships/tankers.
- Unsupported modules must never report fake success.

---

### Task 1: War Room dashboard and diagnostics

**Files:**
- Modify: `panel/templates/dashboard.html`
- Modify: `panel/app.py`
- Test: `tests/test_panel.py`

**Interfaces:**
- Consumes: existing `live`, `pending`, `published`, `state` template context.
- Produces: dashboard DOM IDs consumed by `panel/static/live.js` and richer diagnostics context.

- [ ] **Step 1: Write failing dashboard assertions**
Add assertions that the authenticated dashboard contains `اتاق فرمان جنگ`, `توقف کامل انتشار`, `اسکن فوری`, `ترافیک هوایی ایران و منطقه`, `هواشناسی فردا`, `نفتکش‌ها و تنگه هرمز`, `بازار و دلار`, `سلامت سیستم`, and the live-feed container.

- [ ] **Step 2: Run focused test**
Run: `pytest tests/test_panel.py::test_authenticated_dashboard_loads -v`
Expected: FAIL until new War Room copy/structure is present.

- [ ] **Step 3: Implement dashboard hierarchy**
Use semantic sections for operations header, priority strip, stats, modules, health diagnostics, live newsroom feed, manual review, and recent publications. Keep all current URLs and source links intact.

- [ ] **Step 4: Extend safe diagnostics context**
In `dashboard()`, derive counts and timestamps only from existing JSON state/history/feed. Do not add secrets or shell access. Pass values such as latest feed timestamp and recent failure count if available.

- [ ] **Step 5: Run test**
Run: `pytest tests/test_panel.py::test_authenticated_dashboard_loads -v`
Expected: PASS.

### Task 2: Command Center API completeness

**Files:**
- Modify: `panel/command_center.py`
- Test: `tests/test_command_center.py`

**Interfaces:**
- Produces: `GET /api/command-center/status`, `POST /api/command-center/publishing`, `POST /api/command-center/module/<module_name>`.

- [ ] **Step 1: Add API tests**
Verify unauthenticated calls return 401, status exposes only safe operational fields, publishing toggles `auto_publish`/`emergency_lock`, `scan`, `weather`, and `air-traffic` enqueue commands, and unsupported `tanker`/`market` currently return an explicit unavailable response rather than success.

- [ ] **Step 2: Run focused API tests**
Run: `pytest tests/test_command_center.py -v`
Expected: FAIL for missing extended status/unavailable behavior.

- [ ] **Step 3: Implement safe status payload**
Return publishing state, live/queue counts, target poll seconds, updated timestamp, and module capability map. Keep secrets out.

- [ ] **Step 4: Implement explicit module capability behavior**
Supported modules enqueue existing agent commands. Known-but-unwired modules return HTTP 409 with `{ok:false,error:"module_unavailable"}`. Unknown names remain 404.

- [ ] **Step 5: Run focused API tests**
Run: `pytest tests/test_command_center.py -v`
Expected: PASS.

### Task 3: Premium responsive visual system and Doran-first typography

**Files:**
- Modify: `panel/static/panel.css`
- Modify: `panel/templates/base.html`
- Test: `tests/test_panel.py`

**Interfaces:**
- Consumes DOM classes/IDs from dashboard/base templates.
- Produces responsive newsroom styling with Doran-first fallback stack.

- [ ] **Step 1: Add presentation assertions**
Check base/dashboard HTML references the panel stylesheet and PWA metadata; read CSS in test and assert `font-family: Doran` or equivalent Doran-first stack exists.

- [ ] **Step 2: Run focused test**
Run: `pytest tests/test_panel.py -v`
Expected: FAIL until CSS/metadata are added.

- [ ] **Step 3: Implement newsroom visual system**
Use graphite background, layered panels, subtle borders, restrained red urgent states, green health state, responsive grids, status chips, large touch targets, sticky mobile operations, and Doran-first fallback typography. Do not embed or distribute font files.

- [ ] **Step 4: Add mobile/PWA metadata to base template**
Add `theme-color`, manifest link, Apple mobile-capable metadata, icons only if repo assets exist, and service-worker registration script.

- [ ] **Step 5: Run focused tests**
Run: `pytest tests/test_panel.py -v`
Expected: PASS.

### Task 4: Live newsroom interactions and alert UX

**Files:**
- Modify: `panel/static/live.js`
- Test: `tests/test_panel.py` and JS syntax check in CI.

**Interfaces:**
- Consumes command-center endpoints and dashboard DOM IDs.
- Produces live connection badge, sound preference, command feedback, module capability states, and new-item alert behavior.

- [ ] **Step 1: Add HTML assertions for required IDs/data attributes**
Assert dashboard includes `liveConnection`, `soundToggle`, `panicToggle`, `commandResult`, and module action attributes.

- [ ] **Step 2: Implement capability-aware controls**
Fetch status; disable unavailable module buttons and label them honestly. Preserve 3-second feed polling and 5-second status polling.

- [ ] **Step 3: Improve alert UX**
Keep localStorage sound preference, short WebAudio tone, visible new-news badge, last-sync timestamp, and reconnect state. Ensure browser title clears when tab becomes visible.

- [ ] **Step 4: Verify JS syntax and panel tests**
Run: `node --check panel/static/live.js` and `pytest tests/test_panel.py -v`
Expected: PASS.

### Task 5: PWA shell

**Files:**
- Create: `panel/static/manifest.webmanifest`
- Create: `panel/static/sw.js`
- Modify: `panel/templates/base.html`
- Modify: `panel/app.py` only if explicit routes are needed by current Flask static behavior.
- Test: `tests/test_panel.py`

**Interfaces:**
- Produces installable web-app metadata and static-shell service worker.

- [ ] **Step 1: Add manifest/service-worker response tests**
Verify authenticated page links the manifest and registration; verify static files are retrievable and contain Bikhabar branding only.

- [ ] **Step 2: Implement manifest**
Use Persian name `بی‌خبر — اتاق فرمان`, standalone display, dark theme/background, and `/` start URL.

- [ ] **Step 3: Implement service worker**
Cache only static CSS/JS/manifest shell. Never cache command-center API, live dashboard HTML, auth responses, or newsroom data.

- [ ] **Step 4: Run tests**
Run: `pytest tests/test_panel.py -v`
Expected: PASS.

### Task 6: Regression, PR, CI, production promotion

**Files:**
- No product file changes unless failures require fixes.

- [ ] **Step 1: Run full suite**
Run: `pytest -q`
Expected: all tests pass.

- [ ] **Step 2: Run JS syntax check**
Run: `node --check panel/static/live.js`
Expected: exit 0.

- [ ] **Step 3: Open PR**
Create a PR from `command-center-war-room-2026-09-09` to `main` summarizing War Room, diagnostics, PWA, responsive design, and preserved safety.

- [ ] **Step 4: Wait for CI**
Require both project CI and PR checks to pass; inspect logs for any failure and fix before merge.

- [ ] **Step 5: Merge and verify production promotion**
Merge only after green CI, then verify main CI promotes the exact merge SHA to the `production` branch.
