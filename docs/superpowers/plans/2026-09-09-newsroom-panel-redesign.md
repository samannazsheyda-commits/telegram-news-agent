# Bikhabar Newsroom Panel Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a real, fast, Persian 24/7 newsroom panel with actionable live news, collapsible module previews, real command/result tracking, real health state, and visible final Telegram output.

**Architecture:** Keep Flask + JSON stores and the existing VPS command/result bridge. Extend read APIs to expose localized feed details, final output, module previews and command results; rewrite the dashboard JS to poll JSON only and render actions/state without page refresh.

**Tech Stack:** Flask, Jinja2, vanilla JavaScript, JSON files/GitHub data backend, pytest.

**Spec:** `docs/superpowers/specs/2026-09-09-newsroom-panel-redesign.md`

## Global Constraints
- Persian-first UI and live news.
- Static 24/7 priority banner.
- 1s live/command polling; 2s health/status polling.
- No fabricated health or preview data.
- Original English only behind explicit disclosure.
- Preview toggles open/closed inline.

---

### Task 1: Regression contract for newsroom API and UI
**Files:** Modify `tests/test_panel.py`, `tests/test_command_center.py`; add assertions for Persian title, final output fields, command-result endpoint, module preview endpoint, newsroom copy, and collapsible preview hooks.
- [ ] Add failing tests for the approved behavior.
- [ ] Run PR CI and confirm expected failures.

### Task 2: Read APIs and command-result tracking
**Files:** Modify `panel/live_api.py`, `panel/command_center.py`.
- [ ] Expose localized title/body, original title/body, final message, queue/review link metadata and media fields.
- [ ] Add `GET /api/command-center/command/<id>` reading `panel_results/<id>.json`.
- [ ] Add `GET /api/command-center/health` based on persisted runtime state/results, using unknown rather than fabricated values.
- [ ] Add `GET /api/command-center/module/<name>/preview` reading latest persisted preview payloads.
- [ ] Keep POST module actions separate from preview reads.

### Task 3: Real newsroom dashboard
**Files:** Modify `panel/templates/dashboard.html`, `panel/templates/base.html`, `panel/static/panel.css`.
- [ ] Rename command-center copy to newsroom copy.
- [ ] Remove permanently-open weather preview.
- [ ] Make priority banner static.
- [ ] Build module cards with preview toggles and hidden inline preview containers.
- [ ] Build live feed shell for Persian item, final output, original text, edit/review/delete/source controls.
- [ ] Replace decorative health copy with values populated by JSON.
- [ ] Simplify Persian navigation.

### Task 4: Fast live browser controller
**Files:** Modify `panel/static/live.js`.
- [ ] Poll live feed every 1000ms and status/health every 2000ms.
- [ ] Play one ding when first item changes and sound is on.
- [ ] Track command IDs until succeeded/failed and reflect result in buttons/state.
- [ ] Toggle module previews open/closed with one click and load preview JSON on open.
- [ ] Render final Telegram output and original English in collapsible details.
- [ ] Support single-item delete and bulk delete through real clear command.
- [ ] Link queued items to review/edit route.

### Task 5: Verification and deployment
**Files:** No production code beyond fixes required by failing tests.
- [ ] Run full CI regression suite.
- [ ] Review PR diff for static fake health/English leakage/regressions.
- [ ] Merge only when checks pass.
- [ ] Verify post-merge main CI passes and promotes exact commit to `production`.
