# Bikhabar Final Newsroom Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a fast light/slate Bikhabar newsroom where incoming stories get cached offline Argos literal previews, one-tap reject is immediate, and one-tap publish uses Luna to produce the final Persian Telegram copy.

**Architecture:** Keep source text immutable. Make panel localization explicitly offline-only and cached; keep final publication separate and AI-gated. Reuse existing newsroom APIs and strict publisher protections, while simplifying the browser shell and reducing polling/render cost.

**Tech Stack:** Python 3.12, Flask/Jinja, vanilla JavaScript, CSS, pytest, Argos offline translation, 1xAI/Luna, Telegram Bot API.

**Spec:** `docs/superpowers/specs/2026-09-16-panel-final-newsroom-design.md`

## Global Constraints

- Offline panel preview uses `src.offline_translation.translate_to_fa_offline` only.
- Offline preview is never final publishable copy.
- Per-story Publish and Reject have no confirmation dialog.
- Manual Publish uses Luna/1xAI and fails closed on Luna failure.
- Global stop-publishing may retain confirmation.
- Light/slate mobile-first UI; fixed safe-area bottom nav; no primary-shell backdrop blur.
- Visible canonical `Clash Report` label is Persian.
- Existing V3 daily cap and automatic production safeguards remain intact.

---

### Task 1: Lock behavior with regression tests

**Files:**
- Create: `tests/test_panel_final_newsroom_contract.py`
- Modify: none

**Interfaces:**
- Consumes: existing panel static/templates and `src.formatters._source_label`.
- Produces: failing regression expectations for all user-visible panel contracts.

- [ ] **Step 1: Write failing tests**

Create tests that assert:
- `panel/live_api.py` imports/calls offline translation rather than `services.translate_to_fa` for panel localization.
- `panel/static/newsroom-live.js` contains the exact UI label `ترجمه آفلاین · تحت‌اللفظی` and uses visible/hidden polling intervals of at least 5000/30000 ms.
- `panel/static/newsroom-actions.js` does not call `confirmAction` in per-story `publish` or `reject` branches.
- `panel/templates/base.html` declares a light color scheme/theme and `panel/static/newsroom-shell.css` uses a light background and no `backdrop-filter` for `.nr-topbar`.
- `_source_label("Clash Report") == "کلش ریپورت"`.

- [ ] **Step 2: Run targeted tests and confirm RED**

Run: `pytest -q tests/test_panel_final_newsroom_contract.py`

Expected: failures for the current network/localization, dark theme, polling cadence, source label, and confirmation behavior.

- [ ] **Step 3: Commit RED tests**

Commit message: `test: lock final newsroom panel behavior`

---

### Task 2: Offline-only literal panel localization

**Files:**
- Modify: `panel/live_api.py`
- Modify: `panel/static/newsroom-live.js`
- Test: `tests/test_panel_final_newsroom_contract.py`

**Interfaces:**
- Consumes: `translate_to_fa_offline(text: str) -> str`.
- Produces: `/api/live-feed/localize` rows with Persian preview fields and `translation_mode="offline_literal"`.

- [ ] **Step 1: Add focused endpoint tests**

Patch the offline translator in the panel module, call localization with representative English title/body, and assert the offline translator is called and the response reports `offline_literal`. Assert no network translator is needed.

- [ ] **Step 2: Run focused endpoint tests and confirm RED**

Run the new endpoint tests only; expect failure because current code uses the existing network-oriented localization path.

- [ ] **Step 3: Implement minimal offline localization and cache**

Import `translate_to_fa_offline` directly. Cache by SHA-256 of source title/body in a bounded in-process dictionary. Return literal localized title/body while retaining original fields. Do not call Luna here.

- [ ] **Step 4: Label the browser preview**

Render `ترجمه آفلاین · تحت‌اللفظی` above the localized preview. Keep `متن اصلی منبع` collapsed below. Offline localization failure should show retry but must not permanently disable Publish.

- [ ] **Step 5: Run targeted tests**

Run: `pytest -q tests/test_panel_final_newsroom_contract.py`

Expected: localization contract tests pass.

- [ ] **Step 6: Commit**

Commit message: `feat: use offline literal previews in newsroom panel`

---

### Task 3: One-tap story actions and Luna-only final publish

**Files:**
- Modify: `panel/static/newsroom-actions.js`
- Modify: `panel/newsroom_api.py` and/or the existing panel command consumer used by manual story actions
- Reuse: `src/one_x_ai_newsroom.py`, strict Persian/editorial guards
- Test: `tests/test_panel_final_newsroom_contract.py`
- Add focused backend test file if existing API tests make that clearer.

**Interfaces:**
- Consumes: story id, immutable source title/body, Luna/1xAI.
- Produces: immediate reject state or validated final Persian publication result.

- [ ] **Step 1: Write failing manual-publish tests**

Test that manual Publish sends original source text to the Luna finalization path and never publishes the offline preview. Test that a Luna error/invalid result produces zero Telegram writes. Test that Reject changes state without a confirmation contract.

- [ ] **Step 2: Run tests and confirm RED**

Expected: current panel publish path does not satisfy the explicit Luna-only manual finalization contract and/or UI still confirms.

- [ ] **Step 3: Remove per-story confirmations**

In story action handling, Publish and Reject immediately POST after setting the card busy. Keep confirmation only for whole-system controls.

- [ ] **Step 4: Route manual Publish through Luna finalization**

Reload the original story server-side. Ask 1xAI/Luna for faithful translation plus natural Persian edit, validate with existing strict translation/editorial guards, then pass only the resulting final Persian copy to the Telegram publisher. On any Luna failure, return a clear error and do not invoke Telegram.

- [ ] **Step 5: Verify action tests**

Run focused tests and confirm one-tap behavior and fail-closed Luna behavior are green.

- [ ] **Step 6: Commit**

Commit message: `feat: finalize manual publishes with Luna`

---

### Task 4: Final light/slate professional UI and performance pass

**Files:**
- Modify: `panel/templates/base.html`
- Modify: `panel/templates/dashboard.html`
- Modify: `panel/static/newsroom-shell.css`
- Modify: `panel/static/newsroom-live.js`
- Test: `tests/test_panel_final_newsroom_contract.py`

**Interfaces:**
- Consumes: existing snapshot JSON and action endpoints.
- Produces: professional mobile-first newsroom shell.

- [ ] **Step 1: Update theme metadata**

Set browser theme/color-scheme for light UI while keeping a charcoal/navy top navigation.

- [ ] **Step 2: Replace shell design tokens**

Use a soft slate page background, near-white cards, dark text, muted slate secondary text, restrained borders/shadows, and red only for priority/danger. Remove expensive backdrop blur from the main top bar/cards and reduce nonessential animation.

- [ ] **Step 3: Stabilize mobile bottom nav**

Use fixed positioning, safe-area bottom padding, explicit z-index, clear active state, and page bottom padding so cards/sheets never obscure navigation.

- [ ] **Step 4: Improve card hierarchy**

Make literal translation the readable main preview, clearly mark it as offline/literal, keep original source collapsible, and keep four large touch actions with Publish/Reject visually distinct.

- [ ] **Step 5: Reduce refresh cost**

Change visible polling from 3000 ms to 5000 ms and hidden polling from 15000 ms to 30000 ms. Preserve fingerprint short-circuit and localization cache.

- [ ] **Step 6: Run panel contract tests**

Run: `pytest -q tests/test_panel_final_newsroom_contract.py`

Expected: green.

- [ ] **Step 7: Commit**

Commit message: `feat: finish light newsroom panel`

---

### Task 5: Source label safety and full verification

**Files:**
- Modify: `src/formatters.py`
- Test: `tests/test_panel_final_newsroom_contract.py`

**Interfaces:**
- Consumes: canonical source id `Clash Report`.
- Produces: visible Persian source label `کلش ریپورت`.

- [ ] **Step 1: Add the canonical source mapping**

Add `"Clash Report": "کلش ریپورت"` without changing source identity stored internally.

- [ ] **Step 2: Run targeted formatter/panel tests**

Run: `pytest -q tests/test_panel_final_newsroom_contract.py`

- [ ] **Step 3: Run full suite**

Run: `pytest -q`

Expected: all existing tests and new panel tests pass.

- [ ] **Step 4: Inspect diff for accidental scope creep**

Confirm no air-traffic changes, no secret changes, no daily-cap changes, and no unrelated production-engine refactor.

- [ ] **Step 5: Commit**

Commit message: `fix: localize canonical visible source labels`

---

### Task 6: PR, CI, merge, production handoff

**Files:** none beyond prior tasks.

**Interfaces:**
- Consumes: tested feature branch.
- Produces: merged main/production-ready panel.

- [ ] **Step 1: Open PR**

Create PR from `feature/panel-final-newsroom-0916` to `main` with the product rules and verification summary.

- [ ] **Step 2: Wait for CI**

Require all repository CI and panel tests to succeed. If a test fails, diagnose root cause before changing code.

- [ ] **Step 3: Review diff**

Verify offline-preview/Luna-final boundaries, no-confirm actions, UI performance, and no-English source-label regression.

- [ ] **Step 4: Squash merge**

Merge only after CI is green.

- [ ] **Step 5: Verify production promotion**

Confirm the tested main SHA is promoted to `production` by the repository workflow.

- [ ] **Step 6: VPS deploy**

Only then ask the operator for one command if automatic VPS deployment does not already occur: `bash /opt/bikhabar/app/deploy/update-vps.sh`.
