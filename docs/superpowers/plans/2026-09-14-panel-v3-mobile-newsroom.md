# Bikhabar V3 Mobile Newsroom Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current layered monitoring panel with a lightweight, mobile-first, single-admin Newsroom V3 control surface that operates directly on VPS runtime state and commands.

**Architecture:** Keep Flask/Jinja, Gunicorn, session auth, CSRF, and `LocalJsonRepository`. Add one V3-centric snapshot API and normalized local command endpoints; move all manual news publication through a guarded V3 runtime command instead of direct Telegram calls. Replace the stacked newsroom CSS/large page script with a focused shell plus small vanilla-JS modules.

**Tech Stack:** Python 3.12, Flask 3.1, Flask-WTF, Jinja, Gunicorn, vanilla JS/CSS, Newsroom V3 SQLite/WAL store and command files.

**Spec:** `docs/superpowers/specs/2026-09-14-panel-v3-mobile-newsroom-design.md`

## Global Constraints

- Single administrator only; no roles or multi-user workflow.
- Mobile-first responsive UX; desktop uses the same capabilities in a denser combined layout.
- Dark premium visual system with Bikhabar red accent.
- Production panel actions operate on local VPS state and command files, not GitHub Actions.
- Browser code never receives Telegram credentials.
- Manual publication must not call Telegram directly from Flask and must preserve V3 ambiguous-state and duplicate protections.
- Canary marker is read-only and must never be reset or retried.
- No React/Node production runtime or external UI dependency.
- Existing Weather, Air Traffic, market/tanker modules and their services must continue to work.

---

### Task 1: V3 newsroom snapshot API

**Files:**
- Create: `panel/newsroom_api.py`
- Modify: `panel/wsgi.py`
- Test: `tests/test_newsroom_v3_panel_api.py`

**Interfaces:**
- Produces: `GET /api/newsroom/snapshot` authenticated JSON contract containing `engine`, V3 production status, publishing state, counts, current live rows, settings, and fingerprint.
- Consumes: existing `current_app.extensions["editorial_data"]`, `data/newsroom_v3_production_status.json`, `state.json`, `data/newsroom_settings.json`, panel live/queue/history files.

- [ ] Write failing tests proving authentication and exact V3 fields (`mode`, `reason`, `error`, source counts, publish counts, Telegram message id) come from the V3 production status rather than legacy guesses.
- [ ] Run PR CI and verify only the new API tests fail because the endpoint/blueprint does not exist.
- [ ] Implement `panel/newsroom_api.py` with one read-only snapshot endpoint and deterministic fingerprint; register it in `panel/wsgi.py`.
- [ ] Verify targeted and full test suites are green.

### Task 2: Guarded V3 manual publication command

**Files:**
- Create: `src/newsroom_v3/manual_publish.py`
- Modify: `src/panel_command_router.py`
- Modify: `src/newsroom_v3/production.py`
- Modify: `panel/command_center.py`
- Modify: `panel/app.py`
- Test: `tests/test_v3_panel_manual_publish.py`
- Test: `tests/test_newsroom_v3_panel_api.py`

**Interfaces:**
- Produces runtime command action `v3_publish` with stable result states `succeeded`, `failed`, `ambiguous`, `reconciled`.
- Produces Flask endpoint `POST /api/newsroom/live/<item_id>/publish` that enqueues exactly one `v3_publish` command.
- Existing manual review POST also enqueues `v3_publish`; it never invokes `send_telegram` inside Flask.

- [ ] Write failing tests proving live/manual publish creates a local `v3_publish` command and Flask never calls `send_telegram`.
- [ ] Write failing tests proving an ambiguous V3 publish result is persisted and a repeated automatic attempt is blocked.
- [ ] Implement a durable manual story identity in the V3 SQLite store path, use `NewsroomV3PublisherWorker` + the production guarded publisher for already-final Persian title/body, and update the V3 production status with the external-attempt timestamp.
- [ ] Extend the production interval gate to honor the latest external/manual attempt so one hybrid cycle cannot immediately send an automatic second Telegram write.
- [ ] Route `v3_publish` in `panel_command_router.py`; on confirmed success/reconciliation update editorial history/queue, but never mark success before the runtime result exists.
- [ ] Migrate Flask manual review publication to enqueue only.
- [ ] Verify targeted and full suites are green.

### Task 3: Normalized VPS-first newsroom actions

**Files:**
- Modify: `panel/newsroom_api.py`
- Modify: `panel/command_center.py`
- Test: `tests/test_newsroom_v3_panel_api.py`

**Interfaces:**
- `POST /api/newsroom/scan`
- `POST /api/newsroom/publishing`
- `POST /api/newsroom/live/<id>/review`
- `POST /api/newsroom/live/<id>/reject`
- `GET /api/newsroom/command/<id>`

- [ ] Add failing contract tests for stable action response shapes and CSRF/auth protection.
- [ ] Implement thin endpoints that reuse existing command/settings helpers instead of duplicating operational code.
- [ ] Normalize command states without masking `failed` or `ambiguous` results.
- [ ] Verify no endpoint leaks tokens/passwords and all tests pass.

### Task 4: Premium mobile-first newsroom shell

**Files:**
- Create: `panel/static/newsroom-shell.css`
- Create: `panel/static/newsroom-ui.js`
- Create: `panel/static/newsroom-live.js`
- Create: `panel/static/newsroom-actions.js`
- Create: `panel/static/newsroom-editor.js`
- Modify: `panel/templates/base.html`
- Modify: `panel/templates/dashboard.html`
- Modify: `panel/templates/review_queue.html`
- Modify: `panel/templates/review_edit.html`
- Modify: `panel/templates/history.html`
- Test: `tests/test_newsroom_v3_ui_contract.py`

**Interfaces:**
- Client reads `/api/newsroom/snapshot` every 3s while visible and 15s in background.
- Story action hooks use `data-story-id`, `data-action`, and the normalized `/api/newsroom/*` endpoints.
- Destructive actions use a confirmation sheet/dialog; edit uses inline sheet/drawer.

- [ ] Add failing UI-contract tests for mobile bottom navigation, V3 status bar, story publish/edit/reject/source controls, confirmation hooks, and absence of old overlapping newsroom style layers.
- [ ] Build a single dark graphite/red responsive shell with >=44px touch targets and server-rendered first content.
- [ ] Implement snapshot polling with `AbortController`, visibility-aware cadence, fingerprint-based no-op updates, and no full-page refresh for routine actions.
- [ ] Implement command-result polling and truthful ready → sending → queued → succeeded/failed/ambiguous feedback.
- [ ] Implement inline mobile editor/full-height sheet and desktop drawer.
- [ ] Keep sound alerts optional and persisted in local storage.
- [ ] Verify mobile/desktop contracts and full suite.

### Task 5: Sources, regression, deployment readiness

**Files:**
- Modify: `panel/templates/source_manager.html`
- Modify: `panel/static/source_manager.css` only if needed for the new shell
- Modify: `.github/workflows/panel-redesign-check.yml` only if existing checks do not cover new assets
- Test: existing panel/source/deploy suites

**Interfaces:**
- Source delete confirmation uses the existing authenticated source-manager backend.
- No source-management change alters V3 publish safety or ancillary modules.

- [ ] Add/adjust contract coverage for source-delete confirmation and responsive shell consistency.
- [ ] Run the full pytest suite and deployment script validation.
- [ ] Inspect PR patch for direct Telegram calls from supported panel publish paths, secrets in HTML/JSON, accidental Canary changes, and unrelated refactors.
- [ ] Mark PR ready only after all checks are green.
- [ ] Merge with expected head SHA, verify post-merge `main` CI and promotion to `production`.
- [ ] Deploy using the existing VPS updater, then verify production SHA, `bikhabar-panel.service=active`, `bikhabar-agent.service=active`, V3 engine status, panel login/snapshot, and a non-Telegram command before claiming the panel live.
