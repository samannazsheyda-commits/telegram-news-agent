# Bikhabar Newsroom Panel Final Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the 24/7 Persian newsroom panel fast, truthful and fully operational while preserving every already-published Telegram post.

**Architecture:** Keep Flask + local JSON runtime, but separate panel-only dismissal from Telegram/publication history, make command/result tracking authoritative, persist Persian live output and final Telegram previews, expose editable priority rules consumed by the runtime, and keep module previews collapsible and non-publishing. Use a revisioned JSON live feed so one-second polling does not rebuild unchanged DOM.

**Tech Stack:** Python 3.12, Flask, vanilla JavaScript, CSS, JSON state files, pytest, GitHub Actions.

**Spec:** Approved newsroom redesign from the project conversation, clarified on 2026-09-11: never delete existing Telegram posts; clear only the current panel feed.

## Global Constraints

- Existing Telegram posts must never be deleted or altered by panel cleanup actions.
- Main title is «اتاق خبر بی‌خبر»; no command-center/war-room wording in user-facing navigation.
- Live feed is Persian-first; original-language source text is secondary and collapsible.
- The exact final Telegram-formatted output is visible per item.
- New live items trigger a short Ding when sound is enabled.
- Live panel refresh target is 1 second; runtime scan target remains 2 seconds.
- Unchanged feed revisions must not rebuild the DOM or lose selections/open state.
- Stop publication and scan commands must show queued/processing/succeeded/failed state from the real result file.
- 24/7 priority rules are editable and persisted to newsroom settings, and the runtime must consume them when ordering fresh items.
- Weather, air traffic, tanker/Hormuz and market previews open in-place and close on the next click; preview generation must not publish.
- Health cards may only display values read from runtime state; missing data is «نامشخص».
- Doran remains the first CSS font family without adding or distributing font binaries.

---

### Task 1: Regression tests for panel-only cleanup and operator controls

**Files:**
- Create: `tests/test_panel_final_operator.py`
- Modify later: `panel/command_center.py`, `panel/static/live.js`, `panel/templates/dashboard.html`

**Interfaces:**
- Consumes: Flask command-center blueprint and fake JSON backend.
- Produces: locked behavior for panel-only dismissal, editable priorities, real command result UI, module preview toggles and Persian final-output controls.

- [ ] **Step 1: Write failing tests** covering live-only cleanup, no published-history deletion scope, editable priority API, one-second revisioned live refresh, Ding, final-output/details controls, and no user-facing English navigation labels.
- [ ] **Step 2: Run CI to verify the regression tests fail on current main-derived branch.**
- [ ] **Step 3: Keep the failures as root-cause evidence before implementation.**

### Task 2: Safe panel-only live cleanup and editable priority settings

**Files:**
- Modify: `panel/command_center.py`
- Modify: `src/panel_command_router.py`
- Modify: `data/newsroom_settings.json`

**Interfaces:**
- Produces `GET/POST /api/command-center/priorities` with an ordered list of short strings.
- `POST /api/command-center/clear` accepts only `scope=live` and never changes publication history or Telegram.

- [ ] **Step 1: Restrict clear scope to live feed only and return explicit `telegram_untouched=true`.**
- [ ] **Step 2: Remove published/rejected history clearing from the newsroom command router.**
- [ ] **Step 3: Add validated priority read/write endpoints and persist `priority_terms` in `newsroom_settings.json`.**
- [ ] **Step 4: Run focused tests and commit.**

### Task 3: Make priority settings affect runtime ordering

**Files:**
- Modify: `src/newsroom_v2.py`
- Test: `tests/test_panel_final_operator.py`

**Interfaces:**
- `_urgency_score(raw, priority_terms=None)` uses user-managed priority terms before fixed fallback war/Iran scoring.
- `run_cycle` passes `settings["priority_terms"]` into ordering.

- [ ] **Step 1: Add a failing ordering test with a custom priority term.**
- [ ] **Step 2: Implement deterministic custom-priority scoring while retaining missile/war fallback.**
- [ ] **Step 3: Run focused tests and commit.**

### Task 4: Revisioned one-second Persian live desk with durable interaction state

**Files:**
- Modify: `panel/live_api.py`
- Modify: `panel/static/live.js`
- Modify: `panel/templates/dashboard.html`

**Interfaces:**
- `GET /api/live-feed` returns `revision` plus Persian-first rows.
- Client keeps selected/open item IDs in Sets, skips DOM rebuild when revision is unchanged, and plays Ding only for a genuinely new top item.

- [ ] **Step 1: Add stable feed revision hashing to the JSON endpoint.**
- [ ] **Step 2: Preserve selections and open details across changed revisions.**
- [ ] **Step 3: Collapse final output by default under «خروجی نهایی تلگرام» and keep original source text separately collapsed.**
- [ ] **Step 4: Rename cleanup actions to «حذف از پنل» and add «پاک‌کردن ورودی‌های فعلی پنل» without any Telegram action.**
- [ ] **Step 5: Run focused tests and commit.**

### Task 5: Operator dashboard layout, previews and settings

**Files:**
- Modify: `panel/templates/dashboard.html`
- Modify: `panel/templates/base.html`
- Modify: `panel/static/settings.js`
- Create/Modify: `panel/static/newsroom-compact.css`

**Interfaces:**
- Live desk is the first working surface after the status strip.
- Operational tools and settings/health are collapsible `<details>` sections.
- Module preview buttons toggle their own inline panel; opening triggers non-publishing refresh and result tracking.
- Priority editor supports add/remove/reorder/save.

- [ ] **Step 1: Move live desk above operational modules.**
- [ ] **Step 2: Replace decorative menu/copy with concise Persian newsroom navigation.**
- [ ] **Step 3: Add collapsible operational and settings/health groups.**
- [ ] **Step 4: Add priority editor UI wired to priority API.**
- [ ] **Step 5: Make module cards toggle previews in place and never leave weather preview permanently open.**
- [ ] **Step 6: Add compact responsive styling with Doran first in the font stack.**
- [ ] **Step 7: Run focused UI/static tests and commit.**

### Task 6: Truthful health and command outcomes

**Files:**
- Modify: `panel/command_center.py`
- Modify: `src/newsroom_hybrid_runtime.py` only if missing runtime metrics are required.
- Test: `tests/test_panel_final_operator.py`

**Interfaces:**
- Health response returns heartbeat, last scan, source counts, fetched count, publication/error state and configured poll interval from runtime state/env.
- Commands are presented as queued → processing → succeeded/failed/reconciled.

- [ ] **Step 1: Expose existing heartbeat counters from `state.json`; do not synthesize green health.**
- [ ] **Step 2: Read poll interval from `POLL_SECONDS` with default 2.**
- [ ] **Step 3: Run focused tests and commit.**

### Task 7: Full verification and production promotion

**Files:**
- No product code unless a regression is discovered.

**Interfaces:**
- GitHub PR checks and main CI are the deployment gate; main CI promotes the exact tested SHA to `production`.

- [ ] **Step 1: Run full pytest suite and JavaScript syntax checks in CI.**
- [ ] **Step 2: Review PR diff for any Telegram deletion call or publication-history clear path.**
- [ ] **Step 3: Merge only with green checks.**
- [ ] **Step 4: Verify the post-merge main CI reports test success and production promotion success.**
- [ ] **Step 5: Verify `production` points to the exact tested merge SHA.**
