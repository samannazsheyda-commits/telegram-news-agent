# BiKhabar Browser Panel Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current browser panel with a fast newsroom-style control surface where reject feels immediate, publish transitions instantly to a live pending state, and Telegram-confirmed results are reconciled safely without duplicate sends.

**Architecture:** Keep GitHub Pages for the frontend and GitHub Actions for secure execution, but split panel commands from the long-running news monitor. The browser writes one command JSON per action, a dedicated workflow processes exactly that command, `src/panel_command_file.py` persists a result JSON, and the browser polls only that result while maintaining optimistic local UI state.

**Tech Stack:** Static HTML/CSS/vanilla JavaScript, Python 3.12, pytest, GitHub Actions, GitHub Contents API, Telegram Bot API, existing editorial queue/history/state JSON files.

**Spec:** `docs/superpowers/specs/2026-09-07-bikhabar-panel-redesign-design.md`

## Global Constraints

- GitHub Pages remains the frontend host; no VPS and no Vercel.
- Telegram bot token must remain server-side in GitHub Actions secrets.
- Browser GitHub credential remains session-scoped and is never committed or stored in localStorage.
- No browser `alert()`, `confirm()`, or blocking prompt in editorial flow.
- Reject must disappear from the active queue immediately in the UI.
- Publish must leave the active queue immediately and enter `در حال انتشار`; only Telegram-confirmed server success counts as published.
- Failed publish restores the card with the edited draft preserved.
- Panel command workflow must not share the `telegram-news-agent` concurrency group.
- Publish/reject processing must be idempotent and retry-safe.
- Existing `data/editorial_queue.json`, `data/editorial_history.json`, and `state.json` formats remain compatible.
- Existing statuses `pending`, `published_manual`, `published_auto`, `rejected_manual`, and `superseded` remain supported.
- Full queue refresh target is 20–30 seconds while visible, slower while hidden; command result polling is separate and lightweight.
- RTL, mobile support, readable Persian typography, visible focus states, and 15–16px minimum comfortable body text are required.

---

## File Structure

- `docs/panel.html` — semantic shell, tabs, queue toolbar, status lanes, auth sheet, system view.
- `docs/panel.css` — newsroom visual system, responsive/mobile rules, sticky mobile actions, skeleton/loading states, toasts, focus states.
- `docs/panel.js` — data loading, filters, drafts, optimistic state, command creation, result polling, rollback/reconcile, auth UX.
- `src/panel_command_file.py` — parse one command file, validate, idempotently publish/reject, write terminal result, consume command.
- `src/manual_publish.py` — expose retry-safe reconciliation helper only if needed by command processor; retain Telegram-success-before-state-mutation rule.
- `.github/workflows/panel-file-command.yml` — dedicated short workflow triggered by `panel_commands/*.json`, independent concurrency, minimal install, process targeted file, persist state/result.
- `tests/test_panel_command_file.py` — backend idempotency/result/persistence tests.
- `tests/test_panel_ui_contract.py` — static panel feature and safety contract.
- `tests/test_panel_workflow.py` — workflow isolation/performance contract.
- `tests/fixtures/panel_command_*.json` — focused command fixtures if repeated JSON setup improves test readability.

---

### Task 1: Lock the New Panel Contracts with Failing Tests

**Files:**
- Create: `tests/test_panel_ui_contract.py`
- Create: `tests/test_panel_workflow.py`
- Modify: `tests/test_panel_command_file.py` if it already exists; otherwise create it in Task 2.

**Interfaces:**
- Consumes: current `docs/panel.html`, `.github/workflows/panel-file-command.yml`.
- Produces: executable acceptance contracts for UI and workflow structure.

- [ ] **Step 1: Write failing UI contract tests**

```python
from pathlib import Path

PANEL = Path("docs/panel.html")
JS = Path("docs/panel.js")
CSS = Path("docs/panel.css")


def test_panel_has_newsroom_controls_and_no_blocking_dialogs():
    html = PANEL.read_text(encoding="utf-8")
    js = JS.read_text(encoding="utf-8") if JS.exists() else html
    combined = html + "\n" + js

    assert 'dir="rtl"' in html
    assert 'name="viewport"' in html
    assert 'data-view="pending"' in html
    assert 'data-view="processing"' in html
    assert 'data-view="published"' in html
    assert 'data-view="rejected"' in html
    assert 'data-view="system"' in html
    assert 'id="queueSearch"' in html
    assert 'id="sourceFilter"' in html
    assert 'id="sortOrder"' in html
    assert 'id="reasonFilter"' in html
    assert 'alert(' not in combined
    assert 'confirm(' not in combined
    assert 'prompt(' not in combined


def test_panel_uses_session_token_and_local_drafts():
    js = JS.read_text(encoding="utf-8")
    assert "sessionStorage" in js
    assert "localStorage" in js
    assert "github_token" not in js.lower()
    assert "saveDraft" in js
    assert "restoreDraft" in js
    assert "clearDraft" in js


def test_panel_has_optimistic_and_result_polling_hooks():
    js = JS.read_text(encoding="utf-8")
    for hook in (
        "optimisticReject",
        "optimisticPublish",
        "restoreRejectedCard",
        "restorePublishCard",
        "pollCommandResult",
        "reconcileCommandResult",
    ):
        assert hook in js
```

- [ ] **Step 2: Write failing workflow contract tests**

```python
from pathlib import Path

WORKFLOW = Path(".github/workflows/panel-file-command.yml")


def test_panel_workflow_is_isolated_and_targeted():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert 'panel_commands/**.json' in text or 'panel_commands/*.json' in text
    assert "browser-panel-command" in text
    assert "telegram-news-agent" not in text.split("concurrency:", 1)[1].split("jobs:", 1)[0]
    assert "pytest -q" not in text
    assert "src.panel_command_file" in text


def test_panel_workflow_persists_results_and_runtime_data():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "panel_results" in text
    assert "editorial_queue.json" in text
    assert "editorial_history.json" in text
    assert "state.json" in text
```

- [ ] **Step 3: Run the focused tests and verify they fail for missing redesign assets/contracts**

Run:

```bash
python -m pytest -q tests/test_panel_ui_contract.py tests/test_panel_workflow.py
```

Expected: FAIL because `docs/panel.js` / `docs/panel.css` and the new workflow contract do not yet exist or do not satisfy the assertions.

- [ ] **Step 4: Commit only the failing contracts**

```bash
git add tests/test_panel_ui_contract.py tests/test_panel_workflow.py
git commit -m "test: define browser panel redesign contracts"
```

---

### Task 2: Make Command Processing Idempotent and Result-Driven

**Files:**
- Modify: `src/panel_command_file.py`
- Modify: `src/manual_publish.py` only if needed for a reusable reconciliation helper
- Create/Modify: `tests/test_panel_command_file.py`

**Interfaces:**
- Consumes: command JSON with `command_id`, `action`, `item_id`, `title`, `body`, `created_at`.
- Produces: `process_command_file(path: str, *, store, token: str, chat_id: str, state_path: str, result_dir: str = "panel_results", channel_checker=None) -> dict`.
- Produces result statuses: `processing`, `succeeded`, `failed`, `reconciled`.

- [ ] **Step 1: Write failing backend tests for reject idempotency**

```python
def test_reject_command_is_idempotent(tmp_path, store):
    command = write_command(tmp_path, action="reject", item_id="item-1")
    first = process_command_file(str(command), store=store, token="", chat_id="", state_path=str(tmp_path / "state.json"))
    second = process_command_file(str(command), store=store, token="", chat_id="", state_path=str(tmp_path / "state.json"))

    assert first["status"] == "succeeded"
    assert second["status"] in {"succeeded", "reconciled"}
    assert len([x for x in store.history() if x.get("id") == "item-1"]) == 1
```

- [ ] **Step 2: Write failing tests for publish-at-most-once under retry**

```python
def test_publish_retry_never_sends_telegram_twice(tmp_path, store):
    sent = []
    command = write_command(tmp_path, action="publish", item_id="item-1", title="تیتر", body="متن")

    def sender(text, token, chat_id):
        sent.append(text)

    first = process_command_file(
        str(command), store=store, token="bot", chat_id="@bikhabaar",
        state_path=str(tmp_path / "state.json"), sender=sender,
        channel_checker=lambda url: False,
    )
    second = process_command_file(
        str(command), store=store, token="bot", chat_id="@bikhabaar",
        state_path=str(tmp_path / "state.json"), sender=sender,
        channel_checker=lambda url: False,
    )

    assert first["status"] == "succeeded"
    assert second["status"] in {"succeeded", "reconciled"}
    assert len(sent) == 1
```

- [ ] **Step 3: Write failing tests for channel reconciliation and Telegram failure**

```python
def test_publish_reconciles_when_source_already_in_channel(tmp_path, store):
    sent = []
    command = write_command(tmp_path, action="publish", item_id="item-1", title="تیتر", body="متن")

    result = process_command_file(
        str(command), store=store, token="bot", chat_id="@bikhabaar",
        state_path=str(tmp_path / "state.json"), sender=lambda *a, **k: sent.append(a),
        channel_checker=lambda url: True,
    )

    assert result["status"] == "reconciled"
    assert sent == []


def test_publish_failure_keeps_item_pending_and_writes_failed_result(tmp_path, store):
    command = write_command(tmp_path, action="publish", item_id="item-1", title="تیتر", body="متن")

    def boom(*args, **kwargs):
        raise RuntimeError("telegram down")

    result = process_command_file(
        str(command), store=store, token="bot", chat_id="@bikhabaar",
        state_path=str(tmp_path / "state.json"), sender=boom,
        channel_checker=lambda url: False,
    )

    assert result["status"] == "failed"
    assert store.get_pending("item-1") is not None
```

- [ ] **Step 4: Run the backend tests and verify they fail**

Run:

```bash
python -m pytest -q tests/test_panel_command_file.py
```

Expected: FAIL on missing/insufficient idempotent result behavior.

- [ ] **Step 5: Implement result serialization and command identity helpers**

Implement focused helpers in `src/panel_command_file.py`:

```python
def _result_path(result_dir: str, command_id: str) -> Path:
    return Path(result_dir) / f"{command_id}.json"


def _write_result(result_dir: str, payload: dict) -> dict:
    path = _result_path(result_dir, payload["command_id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    return payload


def _terminal_result(result_dir: str, command_id: str) -> dict | None:
    path = _result_path(result_dir, command_id)
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if payload.get("status") in {"succeeded", "failed", "reconciled"} else None
```

- [ ] **Step 6: Implement idempotent action processing**

Required logic:

```python
existing = _terminal_result(result_dir, command_id)
if existing:
    return existing

_write_result(result_dir, processing_payload)

if action == "reject":
    if store.get_pending(item_id) is None:
        return _write_result(result_dir, reconciled_payload)
    reject_review_item(store, item_id)
    return _write_result(result_dir, succeeded_payload)

if action == "publish":
    item = store.get_pending(item_id)
    if item is None:
        return _write_result(result_dir, reconciled_payload)
    if channel_checker and channel_checker(item.source_url):
        reconcile_as_published_without_send(...)
        return _write_result(result_dir, reconciled_payload)
    try:
        publish_review_item(...)
    except Exception as exc:
        return _write_result(result_dir, failed_payload(message=str(exc)))
    return _write_result(result_dir, succeeded_payload)
```

- [ ] **Step 7: Ensure processed command files cannot remain live**

After a terminal result is written, delete or move the command file exactly once. If deletion fails after successful Telegram send, the existing terminal result must prevent resend on retry.

- [ ] **Step 8: Run the backend tests until green**

Run:

```bash
python -m pytest -q tests/test_panel_command_file.py tests/test_manual_publish.py
```

Expected: PASS.

- [ ] **Step 9: Commit backend command safety**

```bash
git add src/panel_command_file.py src/manual_publish.py tests/test_panel_command_file.py
git commit -m "fix: make panel commands idempotent and result-driven"
```

---

### Task 3: Build the Dedicated Fast Panel Workflow

**Files:**
- Replace/Modify: `.github/workflows/panel-file-command.yml`
- Modify: `tests/test_panel_workflow.py`

**Interfaces:**
- Consumes: one pushed `panel_commands/*.json` path from the triggering commit.
- Produces: one `panel_results/<command_id>.json`, updated queue/history/state, consumed command file.

- [ ] **Step 1: Tighten workflow tests for independent concurrency and no full-suite gate**

Add assertions:

```python
def test_panel_workflow_does_not_wait_for_monitor_and_uses_minimal_install():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "browser-panel-command" in text
    assert "cancel-in-progress: false" in text
    assert "requirements.txt" in text
    assert "requirements-dev.txt" not in text
    assert "python -m pytest" not in text
```

- [ ] **Step 2: Run workflow tests and verify failure**

Run:

```bash
python -m pytest -q tests/test_panel_workflow.py
```

Expected: FAIL until the workflow is isolated/minimal.

- [ ] **Step 3: Implement the workflow**

Use this structure:

```yaml
name: Browser Panel File Command

on:
  push:
    branches: [main]
    paths:
      - "panel_commands/*.json"

permissions:
  contents: write

concurrency:
  group: browser-panel-command-${{ github.ref }}
  cancel-in-progress: false

jobs:
  command:
    runs-on: ubuntu-latest
    timeout-minutes: 3
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip
      - run: pip install -r requirements.txt
      - name: Resolve command file
        id: command
        shell: bash
        run: |
          git diff-tree --no-commit-id --name-only -r "$GITHUB_SHA" \
            | grep '^panel_commands/.*\.json$' \
            | head -n 1 \
            | sed 's/^/path=/' >> "$GITHUB_OUTPUT"
      - name: Process command
        env:
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: "@bikhabaar"
        run: python -m src.panel_command_file "${{ steps.command.outputs.path }}"
      - name: Persist result and editorial state
        run: |
          mkdir -p /tmp/panel-snapshot/data /tmp/panel-snapshot/panel_results
          cp state.json /tmp/panel-snapshot/state.json
          cp data/editorial_queue.json /tmp/panel-snapshot/data/editorial_queue.json
          cp data/editorial_history.json /tmp/panel-snapshot/data/editorial_history.json
          cp -a panel_results/. /tmp/panel-snapshot/panel_results/ 2>/dev/null || true
          git fetch origin main
          git reset --hard origin/main
          cp /tmp/panel-snapshot/state.json state.json
          cp /tmp/panel-snapshot/data/editorial_queue.json data/editorial_queue.json
          cp /tmp/panel-snapshot/data/editorial_history.json data/editorial_history.json
          mkdir -p panel_results
          cp -a /tmp/panel-snapshot/panel_results/. panel_results/ 2>/dev/null || true
          git rm -f "${{ steps.command.outputs.path }}" 2>/dev/null || true
          git config user.name "telegram-news-agent[bot]"
          git config user.email "telegram-news-agent[bot]@users.noreply.github.com"
          git add state.json data/editorial_queue.json data/editorial_history.json panel_results
          git commit -m "chore: apply browser panel command" || exit 0
          git push
```

If direct copy-back risks overwriting monitor changes, use the existing merge helper or extend it with explicit panel result merge semantics rather than raw replacement.

- [ ] **Step 4: Run workflow contract tests**

Run:

```bash
python -m pytest -q tests/test_panel_workflow.py
```

Expected: PASS.

- [ ] **Step 5: Commit workflow isolation**

```bash
git add .github/workflows/panel-file-command.yml tests/test_panel_workflow.py
git commit -m "perf: isolate browser panel command workflow"
```

---

### Task 4: Replace the Frontend with a Readable Newsroom Shell

**Files:**
- Replace: `docs/panel.html`
- Create: `docs/panel.css`
- Create: `docs/panel.js`
- Modify: `tests/test_panel_ui_contract.py`

**Interfaces:**
- Consumes: existing queue/history/state raw JSON endpoints and GitHub Contents API.
- Produces: semantic DOM IDs/classes used by `docs/panel.js` and contract tests.

- [ ] **Step 1: Add failing structural UI assertions for stats, tabs, auth, queue toolbar, processing lane, and system view**

Add to `tests/test_panel_ui_contract.py`:

```python
def test_panel_exposes_expected_primary_stats_and_auth_shell():
    html = PANEL.read_text(encoding="utf-8")
    for element_id in (
        "pendingCount", "processingCount", "publishedToday", "rejectedToday",
        "connectionBadge", "connectSheet", "queueSearch", "sourceFilter",
        "sortOrder", "reasonFilter", "pendingList", "processingList",
        "publishedList", "rejectedList", "systemPanel",
    ):
        assert f'id="{element_id}"' in html
```

- [ ] **Step 2: Run UI contract and verify failure**

Run:

```bash
python -m pytest -q tests/test_panel_ui_contract.py
```

Expected: FAIL.

- [ ] **Step 3: Build semantic `docs/panel.html` shell**

Requirements:
- `<html lang="fa" dir="rtl">`.
- Separate `<link rel="stylesheet" href="./panel.css">` and `<script src="./panel.js" defer>`.
- Brand/header, connection badge, refresh button.
- Four stats.
- Tabs: pending, processing, published, rejected, system.
- Queue toolbar: search/source/sort/reason/clear.
- Inline connect sheet that is hidden after successful auth.
- Toast region using `aria-live="polite"`.
- No inline `onclick` handlers.

- [ ] **Step 4: Build `docs/panel.css` visual system**

Implement:
- CSS variables for background/surface/border/text/muted/success/danger/warning.
- Font stack: `Vazirmatn, Tahoma, "Segoe UI", system-ui, sans-serif`.
- Minimum body 16px.
- Headline editor visually dominant.
- 44px+ control heights.
- Clear keyboard focus outlines.
- Responsive one-column mobile layout.
- Sticky mobile action row for active card.
- Skeleton, stale-data, processing, success, failure, and edited states.
- Compact top connection badge after auth.

- [ ] **Step 5: Run UI contract until structural assertions pass**

Run:

```bash
python -m pytest -q tests/test_panel_ui_contract.py
```

Expected: remaining failures should now be JavaScript behavior contracts only.

- [ ] **Step 6: Commit the visual shell**

```bash
git add docs/panel.html docs/panel.css tests/test_panel_ui_contract.py
git commit -m "feat: add newsroom panel shell and responsive styles"
```

---

### Task 5: Implement Fast Queue Loading, Filters, Drafts, and Auth UX

**Files:**
- Modify: `docs/panel.js`
- Modify: `tests/test_panel_ui_contract.py`

**Interfaces:**
- Produces: `loadQueueAndHistory()`, `loadDiagnosticsLazy()`, `applyFilters()`, `saveDraft()`, `restoreDraft()`, `clearDraft()`, `connectGitHub()`, `disconnectGitHub()`.

- [ ] **Step 1: Add failing contract assertions for data flow and no eager system dependency**

```python
def test_panel_loads_queue_before_diagnostics_and_has_visibility_aware_refresh():
    js = JS.read_text(encoding="utf-8")
    assert "loadQueueAndHistory" in js
    assert "loadDiagnosticsLazy" in js
    assert "document.visibilityState" in js
    assert "25000" in js or "30000" in js
```

- [ ] **Step 2: Run contract and verify failure**

Run:

```bash
python -m pytest -q tests/test_panel_ui_contract.py
```

- [ ] **Step 3: Implement queue/history fetch with stale-data retention**

Rules:
- Fetch queue/history first with cache-busting and `cache: 'no-store'`.
- Keep previous rendered data on fetch failure.
- Display a stale-data banner instead of blanking the UI.
- Load diagnostics only after queue render or when System tab opens.

- [ ] **Step 4: Implement filters and progressive rendering**

Required behavior:
- Search title/body/source case-insensitively.
- Source filter from unique current queue sources.
- Sort newest/oldest by `published_at_source`.
- Reason filter.
- Render first 30–50 cards, with “نمایش بیشتر” for the next batch.
- Use event delegation from the list container rather than inline handlers.

- [ ] **Step 5: Implement debounced local drafts**

Use keys such as:

```javascript
const DRAFT_PREFIX = 'bikhabar:draft:';
function draftKey(id){ return DRAFT_PREFIX + id; }
```

Rules:
- Debounce writes ~300ms.
- Store only title/body and original-hash/timestamp, never token.
- Restore on render.
- Show `ویرایش‌شده` indicator when draft differs.
- `بازگشت به متن اولیه` clears draft and restores source values.

- [ ] **Step 6: Implement compact session-only authentication UX**

Rules:
- Store token in `sessionStorage` only.
- Validate with repository GET.
- Hide large connect sheet after success.
- Show compact connected/error badge.
- Provide change/disconnect controls.
- 401/403 shows inline permission guidance for `Contents: Read and write`.

- [ ] **Step 7: Implement visible/hidden refresh cadence**

Use ~25 seconds while visible and ≥60 seconds while hidden. Manual refresh always works.

- [ ] **Step 8: Run contract tests**

Run:

```bash
python -m pytest -q tests/test_panel_ui_contract.py
```

Expected: PASS for loading/filter/draft/auth contracts.

- [ ] **Step 9: Commit frontend data/draft/auth behavior**

```bash
git add docs/panel.js tests/test_panel_ui_contract.py
git commit -m "feat: add fast queue filters drafts and compact auth"
```

---

### Task 6: Implement Optimistic Reject with Undo and Automatic Rollback

**Files:**
- Modify: `docs/panel.js`
- Modify: `docs/panel.css`
- Modify: `tests/test_panel_ui_contract.py`

**Interfaces:**
- Produces: `optimisticReject(itemId)`, `submitRejectCommand(itemId)`, `restoreRejectedCard(itemId)`, `showUndoToast(...)`.

- [ ] **Step 1: Add failing static contract assertions for reject path and undo**

```python
def test_reject_has_optimistic_remove_undo_and_restore_hooks():
    js = JS.read_text(encoding="utf-8")
    for name in ("optimisticReject", "submitRejectCommand", "restoreRejectedCard", "showUndoToast"):
        assert name in js
    assert "5000" in js
```

- [ ] **Step 2: Run test and verify failure**

Run:

```bash
python -m pytest -q tests/test_panel_ui_contract.py
```

- [ ] **Step 3: Implement immediate local removal**

On click:
- Save original index and current edited draft in an in-memory operation record.
- Remove card immediately.
- Decrement pending count immediately.
- Add operation to Processing view as `در حال رد`.
- Show 5-second non-modal Undo toast.

- [ ] **Step 4: Implement undo grace behavior**

During the local grace window:
- Undo cancels submission if command creation has not started.
- Restore card at original index with draft intact.
- Remove processing indicator.

After command is submitted:
- Hide Undo.
- Continue result polling.

- [ ] **Step 5: Implement rollback on GitHub/result failure**

If command file creation fails or result becomes `failed`:
- Restore card automatically.
- Restore pending count.
- Keep draft.
- Show inline error on the restored card and a compact toast.

If result is `succeeded` or `reconciled`:
- Remove operation from Processing.
- Clear local draft.
- Increment rejected-today only for succeeded reject; reconciled terminal item simply refreshes counters on next background load.

- [ ] **Step 6: Run UI contract**

Run:

```bash
python -m pytest -q tests/test_panel_ui_contract.py
```

Expected: PASS.

- [ ] **Step 7: Commit optimistic reject**

```bash
git add docs/panel.js docs/panel.css tests/test_panel_ui_contract.py
git commit -m "feat: make panel reject instant with undo and rollback"
```

---

### Task 7: Implement Optimistic Publish, Per-Command Polling, and Restore-on-Failure

**Files:**
- Modify: `docs/panel.js`
- Modify: `docs/panel.css`
- Modify: `tests/test_panel_ui_contract.py`

**Interfaces:**
- Produces: `optimisticPublish(itemId)`, `createCommand(payload)`, `pollCommandResult(commandId)`, `reconcileCommandResult(commandId, result)`, `restorePublishCard(itemId)`.

- [ ] **Step 1: Add failing contract assertions for publish state and result polling**

```python
def test_publish_uses_per_command_result_polling_not_full_refresh_loop():
    js = JS.read_text(encoding="utf-8")
    assert "optimisticPublish" in js
    assert "pollCommandResult" in js
    assert "panel_results/" in js
    assert "restorePublishCard" in js
```

- [ ] **Step 2: Run and verify failure**

Run:

```bash
python -m pytest -q tests/test_panel_ui_contract.py
```

- [ ] **Step 3: Implement publish validation**

Before local transition:
- Title must be non-empty after trim.
- `source_url` must exist.
- Invalid fields remain in place and receive accessible inline error text.

- [ ] **Step 4: Implement immediate processing transition**

On valid click:
- Snapshot card index + edited title/body.
- Remove from pending list immediately.
- Increment processing count and add Processing item labeled `در حال انتشار`.
- Disable duplicate publish/reject actions for that item while operation is active.
- Create command JSON with UUID and ISO timestamp.

- [ ] **Step 5: Implement command creation with one conflict retry**

`createCommand(payload)` must:
- PUT to `panel_commands/<timestamp>-<uuid>.json` via Contents API.
- On path conflict only, generate a new UUID/path and retry once.
- On 401/403, fail immediately and switch connection badge to error.

- [ ] **Step 6: Implement specific result polling**

Poll only:

```text
https://raw.githubusercontent.com/<owner>/<repo>/main/panel_results/<command_id>.json
```

Behavior:
- Start ~1.5–2 seconds after command creation.
- Poll every ~2 seconds initially, then back off modestly.
- Stop at a bounded timeout (for example 90 seconds).
- Do not reload 1+ MB history on each poll.

- [ ] **Step 7: Implement terminal reconciliation**

- `succeeded`: remove Processing item, clear draft, increment published-today locally, show success toast.
- `reconciled`: remove Processing item, clear draft, show `قبلاً منتشر شده بود؛ وضعیت هماهنگ شد` without claiming a new send.
- `failed`: restore card at original position, keep draft, show server message inline.
- timeout: leave operation in Processing with `بررسی وضعیت`/retry polling action; do not claim success.

- [ ] **Step 8: Run UI contracts**

Run:

```bash
python -m pytest -q tests/test_panel_ui_contract.py
```

Expected: PASS.

- [ ] **Step 9: Commit optimistic publish**

```bash
git add docs/panel.js docs/panel.css tests/test_panel_ui_contract.py
git commit -m "feat: add optimistic publish with confirmed result polling"
```

---

### Task 8: Add Published, Rejected, Processing, and System Views without Slowing the Queue

**Files:**
- Modify: `docs/panel.js`
- Modify: `docs/panel.html`
- Modify: `docs/panel.css`
- Modify: `tests/test_panel_ui_contract.py`

**Interfaces:**
- Produces lazy `renderPublished()`, `renderRejected()`, `renderProcessing()`, `renderSystem()`.

- [ ] **Step 1: Add failing assertions for lazy diagnostic/system behavior**

```python
def test_system_diagnostics_are_lazy_and_queue_is_default_view():
    html = PANEL.read_text(encoding="utf-8")
    js = JS.read_text(encoding="utf-8")
    assert 'data-view="pending"' in html
    assert "renderSystem" in js
    assert "loadDiagnosticsLazy" in js
```

- [ ] **Step 2: Run and verify failure if any hooks are missing**

Run:

```bash
python -m pytest -q tests/test_panel_ui_contract.py
```

- [ ] **Step 3: Implement view rendering**

- Pending: filtered active queue only.
- Processing: local active commands + recoverable timed-out operations.
- Published: recent `published_manual` and `published_auto`, newest first.
- Rejected: recent `rejected_manual` and `superseded`.
- System: workflow health, latest run status, last successful monitor, runtime version/state summary.

- [ ] **Step 4: Load system diagnostics lazily**

Only fetch workflow API/state details after queue is usable or System view is opened.

- [ ] **Step 5: Add compact stale/health labels**

Health states must include text labels, not color only: `سالم`, `در حال اجرا`, `نیاز به بررسی`, `داده قدیمی`.

- [ ] **Step 6: Run UI contracts**

Run:

```bash
python -m pytest -q tests/test_panel_ui_contract.py
```

Expected: PASS.

- [ ] **Step 7: Commit secondary views**

```bash
git add docs/panel.html docs/panel.css docs/panel.js tests/test_panel_ui_contract.py
git commit -m "feat: add processing history and system panel views"
```

---

### Task 9: Verify Mobile Usability and Accessibility Contracts

**Files:**
- Modify: `docs/panel.css`
- Modify: `docs/panel.html`
- Modify: `tests/test_panel_ui_contract.py`

**Interfaces:**
- Produces mobile-safe CSS and keyboard-visible focus behavior.

- [ ] **Step 1: Add static accessibility/mobile assertions**

```python
def test_panel_has_accessible_live_regions_and_mobile_action_styles():
    html = PANEL.read_text(encoding="utf-8")
    css = CSS.read_text(encoding="utf-8")
    assert 'aria-live="polite"' in html
    assert ":focus-visible" in css
    assert "position: sticky" in css
    assert "@media" in css
    assert "44px" in css or "min-height: 2.75rem" in css
```

- [ ] **Step 2: Run and verify failure if missing**

Run:

```bash
python -m pytest -q tests/test_panel_ui_contract.py
```

- [ ] **Step 3: Implement final mobile/accessibility CSS**

Ensure:
- No horizontal overflow at 360px width.
- Sticky action row does not cover textareas.
- Search/filter controls collapse cleanly.
- Buttons remain at least 44px high.
- Focus outlines are visible.
- Status badges always include readable text.

- [ ] **Step 4: Run contract tests**

Run:

```bash
python -m pytest -q tests/test_panel_ui_contract.py
```

Expected: PASS.

- [ ] **Step 5: Commit mobile/accessibility polish**

```bash
git add docs/panel.html docs/panel.css tests/test_panel_ui_contract.py
git commit -m "fix: polish panel mobile and accessibility behavior"
```

---

### Task 10: Full Regression, Live Workflow Verification, and Pages Check

**Files:**
- Modify only if verification exposes defects.

**Interfaces:**
- Consumes all previous tasks.
- Produces evidence that the redesigned panel is safe enough to call complete.

- [ ] **Step 1: Run focused panel/backend tests**

Run:

```bash
python -m pytest -q \
  tests/test_panel_command_file.py \
  tests/test_manual_publish.py \
  tests/test_panel_ui_contract.py \
  tests/test_panel_workflow.py
```

Expected: PASS.

- [ ] **Step 2: Run the full suite**

Run:

```bash
python -m pytest -q
```

Expected: PASS. If unrelated legacy tests fail, investigate and fix only if the failure is caused by this redesign; do not hide failures.

- [ ] **Step 3: Inspect the actual panel workflow file on `main`**

Verify:
- Separate `browser-panel-command-*` concurrency.
- No full pytest in per-click workflow.
- `requirements.txt`, not dev dependencies.
- Result + queue/history/state persistence present.

- [ ] **Step 4: Observe one actual workflow run triggered by a safe command**

Preferred verification:
- Use a disposable/test queue record if one already exists.
- Otherwise use a safe reject test only if it does not remove a real editorial item.
- Do not publish a real Telegram item solely for testing.

Confirm the workflow reaches `success` and writes a terminal `panel_results/<command_id>.json`.

- [ ] **Step 5: Verify GitHub Pages serves all three panel assets**

Check:
- `docs/panel.html`
- `docs/panel.css`
- `docs/panel.js`

Then open the Pages panel URL with a cache-busting query and verify no 404/static asset error.

- [ ] **Step 6: Verify actual UI behavior manually in browser**

Checklist:
- Queue renders before system diagnostics.
- Search/source/sort filters respond immediately.
- Draft survives refresh.
- Reject card disappears immediately without popup.
- Publish card enters `در حال انتشار` immediately.
- Failed command path restores card and draft.
- Connection badge compacts after auth.
- Mobile layout has no horizontal scroll.

- [ ] **Step 7: Review command safety after a retry simulation**

Re-run the same processed command file/path or replay the same `command_id` in a test environment and confirm no second Telegram send occurs.

- [ ] **Step 8: Final commit for any verification-only fixes**

```bash
git add docs src tests .github/workflows
git commit -m "fix: finalize browser panel verification issues"
```

Only create this commit if verification required changes.

---

## Self-Review

- **Spec coverage:** All acceptance requirements are mapped: optimistic reject, optimistic publish, rollback, command result polling, idempotency, workflow isolation, filters, drafts, history views, health/system, auth UX, mobile, accessibility, and full verification.
- **Placeholder scan:** No TBD/TODO placeholders remain. Every code-bearing task includes concrete assertions, interfaces, commands, and expected outcomes.
- **Type/name consistency:** Browser hook names and backend command/result field names are consistent across tasks. Result statuses are exactly `processing`, `succeeded`, `failed`, `reconciled`; command fields are exactly `command_id`, `action`, `item_id`, `title`, `body`, `created_at`.
- **Scope check:** This remains one cohesive subsystem redesign: browser panel + its dedicated command execution path. News-monitor editorial algorithms are explicitly out of scope.
