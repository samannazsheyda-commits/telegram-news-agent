# Newsroom Command Center Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Persian-first «بی‌خبر» newsroom command center on top of the existing GitHub Pages + command-file architecture.

**Architecture:** Preserve `docs/panel.js` for current auth, refresh, publish, reject, and data loading. Add a separate newsroom controller and stylesheet for the advanced UI, and extend `src/panel_command_file.py` with settings and bulk-clear commands that persist through the existing workflow.

**Tech Stack:** Static HTML/CSS/vanilla JS, GitHub Contents API, Python 3.12, pytest, GitHub Actions, Telegram HTML formatting.

**Spec:** `docs/superpowers/specs/2026-09-07-newsroom-command-center-design.md`

## Global Constraints
- UI is RTL Persian-first.
- Doran NoEn ExtraBold is the first display-font family; do not publish uploaded font binaries.
- Red is reserved for critical/breaking states.
- No visible raw URL or English source label in manual Telegram output.
- Pending clear moves records to terminal history; it must not silently delete editorial evidence.
- Published/rejected clear affects panel history only and never deletes Telegram messages.
- Existing publish/reject/refresh flows must remain working.

---

### Task 1: Newsroom shell and visual system

**Files:**
- Modify: `docs/panel.html`
- Create: `docs/newsroom-v1.css`
- Create: `docs/newsroom-v1.js`
- Test: `tests/test_panel_ui_contract.py`

**Interfaces:**
- Consumes: existing DOM ids and globals from `docs/panel.js` (`queue`, `history`, `filtered`, `load`, `loadSystem`, `createCommand`, `pollCommandResult`, `applyFilters`, `updateStats`, `requireConnection`).
- Produces: `window.NewsroomV1`, enhanced command bar, situation rail, analytics/settings views, bulk-action controls.

- [ ] **Step 1: Write failing panel contract tests**

```python
def test_newsroom_command_center_assets_and_views():
    html = PANEL_HTML.read_text(encoding="utf-8")
    assert "newsroom-v1.css" in html
    assert "newsroom-v1.js" in html
    assert 'data-view="analytics"' in html
    assert 'data-view="settings"' in html
    assert "situationRail" in html
    assert "clearCurrentView" in html
```

- [ ] **Step 2: Run targeted test and confirm failure**

Run: `pytest tests/test_panel_ui_contract.py -q`
Expected: FAIL because newsroom assets/views are absent.

- [ ] **Step 3: Implement HTML shell + CSS + controller**

`newsroom-v1.js` must progressively enhance the existing panel, compute real metrics only from current queue/history, and provide two-step bulk-clear confirmation. No fabricated health values.

- [ ] **Step 4: Run targeted UI tests**

Run: `pytest tests/test_panel_ui_contract.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add docs/panel.html docs/newsroom-v1.css docs/newsroom-v1.js tests/test_panel_ui_contract.py
git commit -m "feat: add newsroom command center shell"
```

### Task 2: Bulk clear and settings backend commands

**Files:**
- Modify: `src/panel_command_file.py`
- Modify: `.github/workflows/panel-file-command.yml`
- Create: `data/newsroom_settings.json`
- Test: `tests/test_panel_command_file.py`

**Interfaces:**
- Consumes command JSON fields: `action`, `scope`, `ids`, `settings`, `command_id`.
- Produces terminal result JSON and persisted `data/newsroom_settings.json`.

- [ ] **Step 1: Add failing tests for command parsing and clear semantics**

```python
def test_clear_pending_moves_items_to_superseded(tmp_path):
    # seed two pending records, issue clear command with both ids
    # assert queue empty and history contains status="superseded"
    ...

def test_settings_save_round_trip(tmp_path):
    # save settings through command processor and assert JSON persisted
    ...
```

- [ ] **Step 2: Run targeted tests and confirm failure**

Run: `pytest tests/test_panel_command_file.py -q`
Expected: FAIL with invalid_action / missing implementation.

- [ ] **Step 3: Implement command parser extensions**

Accepted actions become `publish`, `reject`, `refresh`, `clear`, `settings_save`. `clear` accepts `scope` and explicit `ids`; `settings_save` accepts a JSON object. Validation rejects malformed payloads.

- [ ] **Step 4: Implement clear/settings persistence**

Pending clear moves selected pending records to `superseded`. History clear removes selected historical rows only from the panel history file. Settings save atomically writes `data/newsroom_settings.json` with `updated_at`.

- [ ] **Step 5: Persist settings in workflow snapshot/merge**

Add `data/newsroom_settings.json` to snapshot copy and `git add` paths in `panel-file-command.yml`.

- [ ] **Step 6: Run targeted backend tests**

Run: `pytest tests/test_panel_command_file.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/panel_command_file.py .github/workflows/panel-file-command.yml data/newsroom_settings.json tests/test_panel_command_file.py
git commit -m "feat: add newsroom bulk clear and settings commands"
```

### Task 3: Persian-only Telegram output guard

**Files:**
- Modify: `src/manual_publish.py`
- Test: `tests/test_manual_publish.py`

**Interfaces:**
- Consumes: arbitrary source labels and source URLs.
- Produces: Persian-visible Telegram HTML where source URLs are hidden behind `لینک منبع خبر` and English source labels are localized or replaced with `منبع خبری`.

- [ ] **Step 1: Add failing tests for Times of Israel and unknown Latin source**

```python
def test_manual_output_localizes_times_of_israel_and_hides_raw_url():
    message = _message_for(item(source="Times of Israel", source_url="https://example.com/a"), "تیتر فارسی", "")
    assert "تایمز اسرائیل:" in message
    assert ">لینک منبع خبر</a>" in message
    assert "Times of Israel" not in message
    assert "https://example.com/a" not in visible_text(message)
```

- [ ] **Step 2: Run targeted test and confirm failure**

Run: `pytest tests/test_manual_publish.py -q`
Expected: FAIL on source localization.

- [ ] **Step 3: Implement source map + Latin fallback guard**

Add common source localizations and if the cleaned visible source still contains ASCII letters, display `منبع خبری` while retaining the original href only in the anchor attribute.

- [ ] **Step 4: Run targeted tests**

Run: `pytest tests/test_manual_publish.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/manual_publish.py tests/test_manual_publish.py
git commit -m "fix: enforce Persian-visible Telegram output"
```

### Task 4: Full verification and integration

**Files:**
- All changed files above.

**Interfaces:**
- Produces: merge-ready branch with passing project tests.

- [ ] **Step 1: Run full test suite**

Run: `pytest -q`
Expected: all tests PASS.

- [ ] **Step 2: Review workflow and static asset references**

Verify `panel.html` references only files committed on the same branch and command workflow persists all modified runtime files.

- [ ] **Step 3: Open pull request**

```text
Title: feat: newsroom command center v1
Base: main
Head: newsroom-command-center-v1
```

- [ ] **Step 4: Verify CI on PR**

Expected: all required checks green before merge.
