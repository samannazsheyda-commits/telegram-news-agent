# Bikhabar Panel V4 Control Center Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the rejected heavy V3 panel shell with a fast Panel V4 control center while preserving the existing Flask/Jinja backend and Newsroom V3 production pipeline.

**Architecture:** Keep Flask/Jinja and existing panel data/command interfaces. Introduce one V4 shell stylesheet and JS entrypoint, bounded dashboard rendering, panel-only view helpers/API routes, and a controlled Luna Assistant surface. Do not modify Newsroom V3 decision logic.

**Tech Stack:** Python 3.12, Flask, Jinja2, vanilla JavaScript, CSS, pytest, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-18-panel-v4-control-center-design.md`

## Global Constraints
- Panel-only branch; do not modify Newsroom V3 decision/publish logic or V2 runtime.
- Air Traffic is absent from V4 panel UI.
- No direct Luna publish before final preview.
- RTL Persian, mobile-first, slate/charcoal, minimal blur/animation.
- Initial intake render max 30 items.
- No permanent authentication bypass in repo.
- Sensitive actions require explicit confirmation.

---

### Task 1: V4 render contract tests
**Files:**
- Create: `tests/test_panel_v4.py`
- Read/verify: `panel/app.py`, `panel/templates/base.html`, `panel/templates/dashboard.html`

**Interfaces:**
- Consumes: `panel.app.create_app(config)` and in-memory data backend compatible with `read_json`.
- Produces: regression contract for V4 shell, no Air Traffic, Luna preview flow, bounded intake.

- [ ] Add tests that render the authenticated dashboard and assert `Newsroom V4`, V4 nav labels, quota/Luna surfaces, and absence of `air-traffic`/`ترافیک هوایی`.
- [ ] Add test that only 30 intake cards render from a larger feed.
- [ ] Add test that pre-Luna card contains `ارسال به Luna` and does not expose direct publish.
- [ ] Open PR/check CI and confirm the new tests fail for the expected missing V4 behavior.

### Task 2: V4 shell and navigation
**Files:**
- Modify: `panel/templates/base.html`
- Create: `panel/static/newsroom-v4.css`
- Create: `panel/static/newsroom-v4.js`

**Interfaces:**
- Produces CSS classes prefixed `v4-` and stable nav links/active states.

- [ ] Replace V3 branding with V4 control-center branding.
- [ ] Load only base panel CSS needed plus `newsroom-v4.css`; remove V3 shell/final CSS from the V4 base.
- [ ] Add desktop nav for Dashboard, Intake, Review, Luna, Published, Sources, Settings/System.
- [ ] Add mobile bottom nav with safe-area, large touch targets, active state, and no horizontal overflow.
- [ ] Add lightweight toast/confirmation primitives in `newsroom-v4.js`.

### Task 3: Dashboard and story cards
**Files:**
- Modify: `panel/app.py`
- Replace: `panel/templates/dashboard.html`
- Modify/Create tests in `tests/test_panel_v4.py`

**Interfaces:**
- `dashboard()` provides `published_today`, `daily_target`, `daily_remaining`, `special_target`, `special_used`, `queue_count`, `luna_count`, `health_summary`, `live`.
- Story view model fields: `story_id`, `source_display`, `original_title`, `original_body`, `machine_preview`, `luna_state`, `luna_title`, `luna_body`, `importance`, `decision`, `decision_reason_fa`, `source_url`.

- [ ] Add panel-only helpers for safe integer settings and bounded story normalization.
- [ ] Render daily quota cards and human-readable health indicators.
- [ ] Render at most 30 story cards.
- [ ] Before Luna: Original + machine preview + `ارسال به Luna`/`رد`/`منبع`; no direct publish button.
- [ ] After Luna final exists: show Luna final preview and `انتشار`/`ویرایش`/`رد`.
- [ ] Remove Air Traffic module entirely from dashboard.
- [ ] Keep weather/tanker/market only if existing panel actions remain valid and lightweight.

### Task 4: Real section routes for Intake, Luna, Settings/System
**Files:**
- Modify: `panel/app.py`
- Create: `panel/templates/intake.html`
- Create: `panel/templates/luna.html`
- Create: `panel/templates/settings_v4.html`
- Create: `panel/templates/system_health.html`
- Modify: `panel/templates/history.html`, `panel/templates/source_manager.html` only as needed to inherit V4 shell cleanly.

**Interfaces:**
- GET `/intake`, `/luna`, `/settings`, `/system`.
- POST settings/source actions remain CSRF-protected and reuse existing command/data interfaces.

- [ ] Add real routes; no dead/visual-only tabs.
- [ ] Intake supports query/source/state filters with bounded rendering.
- [ ] Luna page shows waiting/finalized items and assistant mount.
- [ ] Settings exposes regular/special quota and publish-mode controls backed by panel settings storage/command queue.
- [ ] System page summarizes provider/Telegram/agent errors in Persian without dumping secrets.

### Task 5: Luna Assistant panel action layer
**Files:**
- Create: `panel/luna_assistant.py`
- Modify: `panel/app.py` or register a panel-only blueprint.
- Create: `panel/static/luna-assistant.js`
- Modify: `panel/templates/luna.html`
- Add: `tests/test_panel_luna_assistant.py`

**Interfaces:**
- `POST /api/panel/luna/assistant` accepts `{message, story_id?}`.
- Returns `{ok, reply_fa, action?, confirmation_required?, payload?}`.
- Initial read actions: dashboard status, recent published, health explanation.
- Controlled write intents: quota update, one-source enable/disable, finalize selected story through existing safe panel command/action path.

- [ ] Write failing intent/action tests first.
- [ ] Implement deterministic intent routing for supported control commands; use existing Luna/provider integration only for editorial finalization/explanation where available.
- [ ] Require confirmation tokens for sensitive write actions.
- [ ] Write audit entries for user/Luna actions without secrets.

### Task 6: Performance and legacy-load cleanup
**Files:**
- Modify: `panel/templates/base.html`, relevant templates and V4 JS/CSS.
- Add tests to `tests/test_panel_v4.py`.

- [ ] Ensure legacy V3 CSS/JS files are not globally loaded by V4 shell.
- [ ] Keep page-specific scripts only where needed.
- [ ] Bound archive/review rendering and add simple pagination parameters where existing routes render unbounded rows.
- [ ] Ensure no Argos/heavy translation call happens during normal dashboard GET.

### Task 7: CI verification and PR
**Files:**
- No production file change unless CI finds a defect.

- [ ] Open PR from `panel-v4-control-center` to `main` to trigger `pr-check.yml`.
- [ ] Verify JS syntax stage and full `pytest` regression pass.
- [ ] Fix only panel-branch regressions discovered by CI.
- [ ] Re-read final diff for accidental V3/V2/Air Traffic backend changes.
- [ ] Leave deployment to VPS as a separate explicit step after review.