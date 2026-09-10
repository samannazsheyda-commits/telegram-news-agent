# Bikhabar Monitoring Panel Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the production panel a fast, Persian, operational «اتاق مانیتورینگ بی‌خبر» with durable live-feed actions, real health, editable priorities, and fresh module previews.

**Architecture:** The VPS runtime writes a dedicated heartbeat, live dismissals are persisted as tombstones checked by the feed store, editable priority rules live in newsroom settings and drive urgency sorting, and panel JavaScript preserves interaction state across frequent JSON refreshes. Preview commands build fresh data without publishing.

**Tech Stack:** Python 3.12, Flask, vanilla JavaScript, JSON runtime state, pytest, systemd/Gunicorn.

**Spec:** `docs/superpowers/specs/2026-09-10-monitoring-panel-recovery-design.md`

## Global Constraints
- Production agent polling remains `POLL_SECONDS=2`.
- Do not fabricate health, tanker, air-traffic, timestamp, or Telegram status.
- Original English may only be optional/collapsible; primary panel news output is Persian.
- Doran remains first in CSS font-family; do not bundle the font binary.
- Preview builders must never publish.

---

### Task 1: Lock regressions with failing tests
**Files:** Create `tests/test_monitoring_panel_recovery.py`; modify no production code.
**Interfaces:** Tests exercise Flask APIs, `LiveFeedStore`, newsroom urgency scoring, and static assets.
- [ ] Add tests asserting the monitoring-room naming, editable `priority_rules`, runtime health endpoint contract, V2 scan routing, selection-state Set in JS, durable dismissal behavior, fresh air-preview command request, compact bottom settings, and Persian-first review/history/source pages.
- [ ] Run `python -m pytest tests/test_monitoring_panel_recovery.py -q` and verify failures are caused by the missing behavior.

### Task 2: Durable deletion and selection
**Files:** Modify `src/panel_live_feed.py`, `panel/command_center.py`, `src/panel_command_router.py`, `panel/static/live.js`.
**Interfaces:** `LiveFeedStore.dismiss(ids, source_urls)` writes `panel_dismissed.json`; `upsert()` skips tombstoned identities; JS owns `selectedNewsIds: Set<string>`.
- [ ] Implement tombstone load/save/check with bounded atomic JSON writes.
- [ ] Make panel single/bulk delete persist tombstones and remove queue/live records.
- [ ] Reapply checkbox state from `selectedNewsIds` after each one-second render.
- [ ] Run the focused deletion/selection tests until green.

### Task 3: Real heartbeat and reliable scan
**Files:** Modify `src/newsroom_hybrid_runtime.py`, `src/vps_runtime.py`, `src/panel_command_router.py`, `panel/command_center.py`.
**Interfaces:** runtime writes `data/runtime_health.json`; health API reads it; `refresh` is a newsroom action executing the current V2 one-shot scan and returning counts.
- [ ] Atomically write cycle start/end, last cycle, source counts, item counts, publish counts, last error, and Telegram evidence without secrets.
- [ ] Route `refresh` through `newsroom_runtime_v2.run_once(... shadow=False ...)` with current settings/data path instead of the legacy scanner.
- [ ] Report scan terminal result with fetched/live/published counts.
- [ ] Run focused command/health tests until green.

### Task 4: Editable priorities wired to runtime
**Files:** Modify `data/newsroom_settings.json`, `panel/command_center.py`, `src/panel_command_router.py`, `src/newsroom_v2.py`, `panel/templates/dashboard.html`, `panel/static/live.js` or `panel/static/settings.js`.
**Interfaces:** settings key `priority_rules` is `list[str]`; status API returns it; settings update validates 1–40 entries, each 2–120 chars; urgency scorer accepts rules.
- [ ] Seed the approved ordered priority phrases.
- [ ] Add authenticated GET/save behavior through existing settings API.
- [ ] Render chips with add/remove/reorder controls and save feedback.
- [ ] Make urgency scoring boost matches according to rule order while retaining hard Iran/missile safeguards.
- [ ] Run priority API/runtime tests until green.

### Task 5: Fresh module previews
**Files:** Modify `panel/static/live.js`, `src/air_traffic.py`, `src/panel_command_router.py`, `panel/command_center.py`, `src/panel_modules.py` as needed.
**Interfaces:** opening a module first POSTs `/api/command-center/module/<name>/preview`, waits for command result, then GETs preview; air preview returns `generated_at`, caption/message, fresh `image_path`.
- [ ] Make every preview opening rebuild exactly once and closing perform no network build.
- [ ] Make air traffic preview fetch current aircraft, render a new PNG, and save metadata with cache-busting URL.
- [ ] Keep Hormuz fail-closed when measurable data is unavailable and show the error in the preview card rather than pretending success.
- [ ] Run module preview tests until green.

### Task 6: Persian-first, readable UI cleanup
**Files:** Modify `panel/templates/base.html`, `panel/templates/dashboard.html`, `panel/templates/review_queue.html`, `panel/templates/history.html`, source-manager templates, `panel/static/newsroom.css`, `panel/static/source_manager.css`, `panel/static/settings.css`.
**Interfaces:** no backend contract changes beyond prior tasks.
- [ ] Rename header/nav/title to «اتاق مانیتورینگ بی‌خبر» / «مانیتورینگ».
- [ ] Move settings after live/history sections and make it a compact collapsed `<details>` block.
- [ ] Use a lighter high-contrast newsroom surface, larger Persian type, clearer source cards, and mobile one-column actions.
- [ ] Ensure review/history/source titles prefer Persian fields and show English only under a collapsed original-text section.
- [ ] Run template/static tests until green.

### Task 7: Full verification and production promotion
**Files:** No feature changes unless a regression is found.
**Interfaces:** GitHub CI is the deployment gate; `main` promotes the exact tested SHA to `production`.
- [ ] Run the full regression suite in CI and require JavaScript syntax checks to pass.
- [ ] Review PR diff for secrets, stale placeholders, English primary labels, and preview publish side effects.
- [ ] Merge only after all checks pass.
- [ ] Verify the `main` push CI completes with `Promote tested main to production` success and confirm `production` points to the same SHA.
