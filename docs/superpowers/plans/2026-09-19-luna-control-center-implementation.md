# Luna Control Center Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn Luna into the confirmed natural-language control surface for the Bikhabar newsroom while fixing the live dashboard workflow: persisted machine Persian for every incoming story, direct-vs-Luna publishing, one-shot new-story alarm, and removal of successfully published cards.

**Architecture:** Preserve the existing V4.1 operator endpoint, safe `v3_publish` command path, source tooling, Builder flow, and 1xAI-backed Responses client. Add a central capability registry plus a frozen mutation-proposal layer so read-only actions execute immediately, every mutation is previewed and explicitly confirmed, and the confirmation executes the exact proposed payload rather than re-interpreting the original sentence. Dashboard-only behavior remains model-independent wherever possible so basic newsroom operation stays fast.

**Tech Stack:** Python 3.12, Flask 3.1, pytest, vanilla JavaScript, existing editorial JSON repository, existing V3 newsroom command queue, GitHub Builder/CI, existing `src.services.translate_to_fa` network translation pipeline, existing Luna Responses client.

**Spec:** `docs/superpowers/specs/2026-09-19-luna-control-center-design.md`

## Global Constraints

- Luna is a natural-language control surface, not an unrestricted shell.
- Read-only inspection/diagnosis may execute immediately.
- Every mutation of newsroom state, source state, publication state, settings, code, UI, or deployment state requires explicit user confirmation immediately before execution.
- Confirmation executes the exact frozen proposal payload; it must not re-interpret the original user sentence.
- Publishing must continue through the existing `v3_publish` command path.
- Code/UI changes must remain Builder-gated: branch → tests → Draft PR → CI → merge confirmation → merge → existing production promotion.
- Luna must never claim success unless an executor returned a successful result.
- Do not expose arbitrary shell commands, arbitrary SQL, arbitrary filesystem access, arbitrary environment-variable mutation, secret retrieval, unrestricted HTTP proxying, direct Telegram writes, or direct production code editing.
- Incoming non-Persian live stories must receive persisted machine Persian copy and show it as primary card content.
- Dashboard must offer distinct `انتشار مستقیم` and `ترجمه با Luna` actions.
- New-story alert plays once for newly appearing IDs after browser audio unlock, not on initial load and not repeatedly for the same story.
- A card leaves the active dashboard only after terminal successful publication state is observed.
- Simple read-only Luna actions target 3–5 seconds under normal provider/network conditions.

## Review Focus

- Ambiguous source/story references must never mutate the wrong target; resolver must ask for clarification when more than one candidate remains.
- A proposal that has expired or whose target version changed must fail closed and require a fresh proposal.
- Machine translation failure must not produce an English card that is accidentally publishable; the card remains visibly pending/non-publishable until Persian copy is persisted.
- Queued or failed publication must not remove a card from the live dashboard; only terminal success may remove it.
- Browser autoplay restrictions must not cause repeated alarm retries or console-error loops; alarm waits for a user interaction unlock and then alerts only on subsequent new IDs.

---

## File Structure

### New files

- `panel/luna_capabilities.py` — capability metadata, validation policy, tool-schema generation, confirmation classification, and registry lookup.
- `panel/luna_proposals.py` — frozen mutation proposal envelope, optimistic target fingerprint/version handling, expiry, completion/cancellation helpers.
- `panel/luna_context.py` — concrete source/story resolution from IDs, normalized names/handles, and recent structured conversation context.
- `panel/luna_control_runtime.py` — single dispatcher from capability name to validated read/preview/execute path; central audit result handling.
- `tests/test_luna_capability_registry.py` — registry contracts and confirmation classification.
- `tests/test_luna_control_center.py` — proposal freezing, resolver ambiguity, source rename/policy, story actions, diagnostics, Builder integration.
- `tests/test_panel_v41_live_operator_flow.py` — extend/retain V4.1 dashboard regression coverage for persisted machine translation, direct publish, alarm, and card removal.

### Modified files

- `panel/live_api.py` — replace panel-only in-memory translation as the authoritative path with persisted publishable machine Persian copy; keep batching and no-store live feed.
- `panel/wsgi.py` — inject the existing network translator into the live-feed localization path without changing legacy translator consumers.
- `panel/luna_publish.py` — explicit `copy_mode="machine" | "luna"`, stable confirmation preview, safe `v3_publish` enqueue.
- `panel/luna_translation_api.py` — explicit machine and Luna publish endpoints for dashboard buttons.
- `panel/luna_tools.py` — expose registry-backed schemas/adapters while preserving existing tool semantics during migration.
- `panel/luna_tool_runtime.py` — route all Luna operations through the central control runtime and frozen proposal policy.
- `panel/luna_operator_api.py` — replace per-tool ad-hoc pending-action creation with unified proposals, structured context updates, and exact proposal confirmation.
- `panel/luna_conversation.py` — persist minimal structured context: last story/source/action/Builder PR identifiers.
- `panel/static/newsroom-v4-dashboard.js` — machine-localization batching, direct publish, one-shot alarm, publication-state refresh/removal.
- `panel/templates/dashboard.html` — distinct direct publish and Luna actions; no primary English fallback for publishable cards.
- `panel/static/sw.js` — bump cache key after dashboard JS/template behavior changes.
- `tests/test_panel_luna_operator_v41.py` and related current Luna tests — update expectations to registry/proposal semantics without weakening safety assertions.

---

### Task 1: Persist Machine Persian Copy for Every Live Story

**Files:**
- Modify: `panel/live_api.py`
- Modify: `panel/wsgi.py`
- Test: `tests/test_panel_v41_live_operator_flow.py`

**Interfaces:**
- Consumes: existing `current_app.config["LIVE_FEED_TRANSLATOR"]`, editorial repository `read_json/write_json`, existing live-feed story IDs.
- Produces: `persist_machine_translation(data, row, translator) -> dict`; live rows with persisted `persian_title`, `persian_body`, `machine_translation_status="passed"`; `/api/live-feed/localize` returns the persisted row.

- [ ] **Step 1: Write the failing persistence test**

```python
def test_machine_localization_persists_persian_copy_for_dashboard_and_publish():
    data = MemoryData()
    app = _app(data)
    app.config["LIVE_FEED_TRANSLATOR"] = lambda text: {
        "Breaking update": "خبر فوری تازه",
        "Body text": "متن فارسی تازه",
    }.get(text, text)

    response = app.test_client().post(
        "/api/live-feed/localize",
        json={"ids": ["story-1"]},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["items"][0]["title"] == "خبر فوری تازه"
    saved = data.mapping["data/panel_live_feed.json"][0]
    assert saved["persian_title"] == "خبر فوری تازه"
    assert saved["persian_body"] == "متن فارسی تازه"
    assert saved["machine_translation_status"] == "passed"
```

- [ ] **Step 2: Add the failure-safety test**

```python
def test_machine_translation_failure_stays_pending_and_not_publishable():
    data = MemoryData()
    app = _app(data)
    app.config["LIVE_FEED_TRANSLATOR"] = lambda _text: ""

    response = app.test_client().post(
        "/api/live-feed/localize",
        json={"ids": ["story-1"]},
    )

    assert response.status_code == 200
    assert response.get_json()["items"] == []
    feed = app.test_client().get("/api/live-feed").get_json()["items"]
    assert feed[0]["needs_localization"] is True
    assert feed[0]["can_publish"] is False
```

- [ ] **Step 3: Run the focused tests and confirm RED**

Run:

```bash
python -m pytest -q tests/test_panel_v41_live_operator_flow.py -k "machine_localization or machine_translation_failure"
```

Expected: persistence assertion fails because the current path only caches panel-local translation, and/or `can_publish` is still true for untranslated rows.

- [ ] **Step 4: Implement repository persistence with optimistic retry**

Add a focused helper in `panel/live_api.py`:

```python
def _persist_machine_translation(row_id: str, title_fa: str, body_fa: str) -> dict | None:
    data = current_app.extensions["editorial_data"]
    for attempt in range(3):
        rows, sha = data.read_json("data/panel_live_feed.json", [])
        rows = [dict(row) for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []
        updated = None
        for row in rows:
            if _row_id(row) != row_id:
                continue
            row["persian_title"] = title_fa
            row["persian_body"] = body_fa
            row["machine_translation_status"] = "passed"
            row["machine_translation_mode"] = "network"
            row["machine_translated_at"] = datetime.now(timezone.utc).isoformat()
            updated = dict(row)
            break
        if updated is None:
            return None
        try:
            data.write_json(
                "data/panel_live_feed.json",
                rows,
                sha,
                "panel v4.1: persist machine Persian copy",
            )
            return updated
        except requests.HTTPError as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if attempt < 2 and status in {409, 422}:
                continue
            raise
    return None
```

Update `/api/live-feed/localize` to call the injected `LIVE_FEED_TRANSLATOR`, require Persian output, persist title/body, then rebuild the public row from the saved record. Set `can_publish` false when no Persian machine/final title exists.

- [ ] **Step 5: Keep translator wiring network-backed**

In `panel/wsgi.py`, retain:

```python
from src.services import translate_to_fa
config["LIVE_FEED_TRANSLATOR"] = translate_to_fa
```

Do not switch the authoritative machine copy back to the in-memory offline cache.

- [ ] **Step 6: Run focused and legacy live-feed tests**

Run:

```bash
python -m pytest -q tests/test_panel_v41_live_operator_flow.py tests/test_panel_live_feed.py
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add panel/live_api.py panel/wsgi.py tests/test_panel_v41_live_operator_flow.py
git commit -m "fix: persist machine Persian live copy"
```

---

### Task 2: Separate Direct Machine Publish from Luna Publish

**Files:**
- Modify: `panel/luna_publish.py`
- Modify: `panel/luna_translation_api.py`
- Modify: `panel/templates/dashboard.html`
- Test: `tests/test_panel_v41_live_operator_flow.py`

**Interfaces:**
- Consumes: persisted `persian_title/body`, passed `final_persian_title/body`, existing `_enqueue("v3_publish", ...)`.
- Produces: `publish_story(..., copy_mode: str = "machine") -> dict`; endpoints `/api/panel/luna/publish-machine/<story_id>` and `/api/panel/luna/publish-final/<story_id>`.

- [ ] **Step 1: Write failing machine-vs-Luna selection tests**

```python
def test_publish_mode_machine_uses_machine_copy_even_when_luna_copy_exists():
    data = MemoryData.with_story(
        persian_title="ترجمه ماشینی مورد تأیید",
        persian_body="متن ماشینی.",
        final_persian_title="نسخه لونا",
        final_persian_body="متن لونا.",
        luna_translation_status="passed",
    )
    captured = {}

    def enqueue(command, **kwargs):
        captured["command"] = command
        captured.update(kwargs)
        return "cmd-machine"

    result = publish_story(data, "story-1", enqueue=enqueue, confirmed=True, copy_mode="machine")
    assert result["ok"] is True
    assert captured["command"] == "v3_publish"
    assert captured["title"] == "ترجمه ماشینی مورد تأیید"


def test_publish_mode_luna_requires_passed_luna_copy_and_uses_it():
    data = MemoryData.with_story(
        persian_title="ترجمه ماشینی",
        final_persian_title="نسخه لونا",
        luna_translation_status="passed",
    )
    captured = {}
    result = publish_story(
        data,
        "story-1",
        enqueue=lambda command, **kw: captured.update(command=command, **kw) or "cmd-luna",
        confirmed=True,
        copy_mode="luna",
    )
    assert result["ok"] is True
    assert captured["title"] == "نسخه لونا"
```

- [ ] **Step 2: Run tests and confirm RED**

Run:

```bash
python -m pytest -q tests/test_panel_v41_live_operator_flow.py -k "publish_mode"
```

Expected: FAIL because `copy_mode` is not yet supported.

- [ ] **Step 3: Implement explicit copy selection**

In `panel/luna_publish.py`:

```python
def _persian_copy(row: dict, copy_mode: str) -> tuple[str, str]:
    if copy_mode == "machine":
        return (
            str(row.get("persian_title") or "").strip(),
            str(row.get("persian_body") or "").strip(),
        )
    if copy_mode == "luna":
        if str(row.get("luna_translation_status") or "") != "passed":
            return "", ""
        return (
            str(row.get("final_persian_title") or "").strip(),
            str(row.get("final_persian_body") or "").strip(),
        )
    raise ValueError("unsupported_copy_mode")
```

Change the public function signature to:

```python
def publish_story(data, story_id: str, *, enqueue, confirmed: bool = False, copy_mode: str = "machine") -> dict:
```

Include `copy_mode` in the pending payload and in safe command metadata, while still enqueuing only `v3_publish`.

- [ ] **Step 4: Add explicit dashboard endpoints**

In `panel/luna_translation_api.py`:

```python
@bp.post("/api/panel/luna/publish-machine/<story_id>")
def publish_machine(story_id: str):
    result = publish_story(_data(), story_id, enqueue=_enqueue, confirmed=True, copy_mode="machine")
    return jsonify(result), (202 if result.get("ok") else 409)


@bp.post("/api/panel/luna/publish-final/<story_id>")
def publish_final(story_id: str):
    result = publish_story(_data(), story_id, enqueue=_enqueue, confirmed=True, copy_mode="luna")
    return jsonify(result), (202 if result.get("ok") else 409)
```

- [ ] **Step 5: Render distinct actions in the card template**

Ensure `panel/templates/dashboard.html` contains distinct operator labels:

```html
<button type="button" data-action="publish-machine">انتشار مستقیم</button>
<button type="button" data-action="translate-luna">ترجمه با Luna</button>
<button type="button" data-action="publish-luna" hidden>انتشار نسخه Luna</button>
```

The machine button is enabled only when persisted machine Persian exists. The Luna publish button becomes available only after a passed Luna translation.

- [ ] **Step 6: Run focused tests**

```bash
python -m pytest -q tests/test_panel_v41_live_operator_flow.py tests/test_panel_luna_publish_v41.py
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add panel/luna_publish.py panel/luna_translation_api.py panel/templates/dashboard.html tests/test_panel_v41_live_operator_flow.py
git commit -m "feat: add direct and Luna publish modes"
```

---

### Task 3: One-Shot New-Story Alarm and Terminal-Success Card Removal

**Files:**
- Modify: `panel/static/newsroom-v4-dashboard.js`
- Modify: `panel/static/sw.js`
- Test: `tests/test_panel_v41_live_operator_flow.py`

**Interfaces:**
- Consumes: `/api/live-feed` `items`, item IDs, `panel_status`, `needs_localization`; publish API responses.
- Produces: `refreshLiveFeed()`, `unlockNewsroomAudio()`, `notifyNewIds(ids)`, `removeTerminalPublishedCards(items)` browser behavior.

- [ ] **Step 1: Add JS contract assertions**

```python
def test_v4_dashboard_has_direct_publish_alarm_auto_localize_and_terminal_removal():
    js = Path("panel/static/newsroom-v4-dashboard.js").read_text(encoding="utf-8")
    template = Path("panel/templates/dashboard.html").read_text(encoding="utf-8")

    assert "انتشار مستقیم" in template
    assert "/api/live-feed/localize" in js
    assert "knownStoryIds" in js
    assert "audioUnlocked" in js
    assert "playNewStoryAlarm" in js
    assert "setInterval" in js
    assert "published_manual" in js
    assert "card.remove()" in js
```

- [ ] **Step 2: Run contract test and confirm RED**

```bash
python -m pytest -q tests/test_panel_v41_live_operator_flow.py -k "dashboard_has_direct_publish"
```

- [ ] **Step 3: Implement first-load-safe story-ID tracking**

Use module state in `panel/static/newsroom-v4-dashboard.js`:

```javascript
const knownStoryIds = new Set();
let feedInitialized = false;
let audioUnlocked = false;
let audioContext = null;
const terminalPublished = new Set(['published_manual', 'published_auto', 'auto_published', 'reconciled_published']);

function recordAndDetectNewIds(items) {
  const incoming = items.map(item => String(item.id || item.item_id || '')).filter(Boolean);
  if (!feedInitialized) {
    incoming.forEach(id => knownStoryIds.add(id));
    feedInitialized = true;
    return [];
  }
  const fresh = incoming.filter(id => !knownStoryIds.has(id));
  incoming.forEach(id => knownStoryIds.add(id));
  return fresh;
}
```

- [ ] **Step 4: Implement browser-safe audio unlock and a short synthetic ding**

```javascript
function unlockNewsroomAudio() {
  if (audioUnlocked) return;
  const Ctx = window.AudioContext || window.webkitAudioContext;
  if (!Ctx) return;
  audioContext = audioContext || new Ctx();
  audioContext.resume().then(() => { audioUnlocked = true; }).catch(() => {});
}

document.addEventListener('pointerdown', unlockNewsroomAudio, { once: true });
document.addEventListener('keydown', unlockNewsroomAudio, { once: true });

function playNewStoryAlarm() {
  if (!audioUnlocked || !audioContext) return;
  const oscillator = audioContext.createOscillator();
  const gain = audioContext.createGain();
  oscillator.frequency.value = 880;
  gain.gain.setValueAtTime(0.0001, audioContext.currentTime);
  gain.gain.exponentialRampToValueAtTime(0.12, audioContext.currentTime + 0.01);
  gain.gain.exponentialRampToValueAtTime(0.0001, audioContext.currentTime + 0.18);
  oscillator.connect(gain).connect(audioContext.destination);
  oscillator.start();
  oscillator.stop(audioContext.currentTime + 0.2);
}
```

If an existing mute setting is available in the page state, guard `playNewStoryAlarm()` with it rather than creating a parallel preference.

- [ ] **Step 5: Auto-request localization for pending IDs in small batches**

```javascript
async function localizePending(items) {
  const ids = items.filter(item => item.needs_localization).map(item => item.id).slice(0, 12);
  if (!ids.length) return [];
  const response = await fetch('/api/live-feed/localize', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ids }),
  });
  if (!response.ok) return [];
  const payload = await response.json();
  return Array.isArray(payload.items) ? payload.items : [];
}
```

Do not block rendering while localization runs; patch returned localized cards after the fetch completes.

- [ ] **Step 6: Remove only terminal-success cards**

```javascript
function removeTerminalPublishedCards(items) {
  items.forEach(item => {
    if (!terminalPublished.has(String(item.panel_status || ''))) return;
    const card = document.querySelector(`[data-story-id="${CSS.escape(String(item.id))}"]`);
    if (card) card.remove();
  });
}
```

A successful publish button response should mark the card `در صف انتشار`; it must not immediately remove it.

- [ ] **Step 7: Poll and alert**

```javascript
async function refreshLiveFeed() {
  const response = await fetch('/api/live-feed', { cache: 'no-store' });
  if (!response.ok) return;
  const payload = await response.json();
  const items = Array.isArray(payload.items) ? payload.items : [];
  const newIds = recordAndDetectNewIds(items);
  renderOrPatchCards(items);
  removeTerminalPublishedCards(items);
  if (newIds.length) playNewStoryAlarm();
  void localizePending(items).then(localized => localized.forEach(patchStoryCard));
}

setInterval(refreshLiveFeed, 5000);
```

Reuse existing render/patch function names where present; do not duplicate card rendering.

- [ ] **Step 8: Bump service-worker cache**

Change:

```javascript
const CACHE = 'bikhabar-newsroom-v4-1-2';
```

- [ ] **Step 9: Run JS syntax and focused tests**

```bash
node --check panel/static/newsroom-v4-dashboard.js
python -m pytest -q tests/test_panel_v41_live_operator_flow.py
```

Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add panel/static/newsroom-v4-dashboard.js panel/static/sw.js panel/templates/dashboard.html tests/test_panel_v41_live_operator_flow.py
git commit -m "feat: add live alarm and published-card cleanup"
```

---

### Task 4: Central Capability Registry

**Files:**
- Create: `panel/luna_capabilities.py`
- Test: `tests/test_luna_capability_registry.py`
- Modify: `panel/luna_tools.py`

**Interfaces:**
- Produces: `Capability`, `CapabilityRegistry`, `build_capability_registry()`, `registry.tool_schemas()`, `registry.get(name)`.
- Consumes later: all control-center runtime and operator API tool-schema exposure.

- [ ] **Step 1: Write registry contract tests**

```python
from panel.luna_capabilities import build_capability_registry


def test_registry_marks_reads_and_mutations_explicitly():
    registry = build_capability_registry()
    assert registry.get("search_stories").mutates is False
    assert registry.get("inspect_panel_state").requires_confirmation is False
    assert registry.get("rename_source").mutates is True
    assert registry.get("rename_source").requires_confirmation is True
    assert registry.get("publish_story").requires_confirmation is True


def test_registry_emits_provider_tool_schema_from_same_metadata():
    registry = build_capability_registry()
    names = {schema["name"] for schema in registry.tool_schemas()}
    assert {"search_stories", "rename_source", "publish_story", "builder_prepare_merge"} <= names
```

- [ ] **Step 2: Run test and confirm RED**

```bash
python -m pytest -q tests/test_luna_capability_registry.py
```

Expected: import failure because the registry does not exist.

- [ ] **Step 3: Implement immutable capability metadata**

```python
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class Capability:
    name: str
    domain: str
    description: str
    parameters: dict
    mutates: bool
    requires_confirmation: bool
    executor_name: str

    def tool_schema(self) -> dict:
        return {
            "type": "function",
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }


class CapabilityRegistry:
    def __init__(self, capabilities: list[Capability]) -> None:
        self._by_name = {cap.name: cap for cap in capabilities}

    def get(self, name: str) -> Capability:
        if name not in self._by_name:
            raise KeyError(name)
        return self._by_name[name]

    def tool_schemas(self) -> list[dict]:
        return [cap.tool_schema() for cap in self._by_name.values()]
```

- [ ] **Step 4: Register initial capability set**

`build_capability_registry()` must explicitly register at least:

```python
Capability("search_stories", "stories", "جست‌وجوی خبرهای پنل...", SEARCH_SCHEMA, False, False, "search_stories")
Capability("get_story", "stories", "دریافت خبر مشخص...", STORY_ID_SCHEMA, False, False, "get_story")
Capability("translate_story", "stories", "ساخت نسخه Luna...", STORY_ID_SCHEMA, True, True, "translate_story")
Capability("publish_story", "stories", "انتشار نسخه فارسی مشخص...", PUBLISH_SCHEMA, True, True, "publish_story")
Capability("reject_and_block_story", "stories", "رد و مسدودسازی...", REJECT_SCHEMA, True, True, "reject_and_block_story")
Capability("list_sources", "sources", "فهرست منابع...", SOURCE_SEARCH_SCHEMA, False, False, "list_sources")
Capability("rename_source", "sources", "تغییر نام نمایشی منبع...", RENAME_SOURCE_SCHEMA, True, True, "rename_source")
Capability("enable_source", "sources", "فعال‌سازی منبع...", SOURCE_TARGET_SCHEMA, True, True, "enable_source")
Capability("disable_source", "sources", "غیرفعال‌سازی منبع...", SOURCE_TARGET_SCHEMA, True, True, "disable_source")
Capability("set_source_review_only", "sources", "تغییر مسیر منبع به فقط بررسی...", REVIEW_POLICY_SCHEMA, True, True, "set_source_review_only")
Capability("inspect_panel_state", "diagnostics", "خلاصه وضعیت پنل...", EMPTY_SCHEMA, False, False, "inspect_panel_state")
Capability("diagnose_newsroom", "diagnostics", "تشخیص مشکل اتاق خبر...", EMPTY_SCHEMA, False, False, "diagnose_newsroom")
Capability("builder_ci_status", "builder", "وضعیت CI تغییر Builder...", BUILDER_PR_SCHEMA, False, False, "builder_ci_status")
Capability("builder_prepare_merge", "builder", "merge تغییر Builder با CI سبز...", BUILDER_PR_SCHEMA, True, True, "builder_prepare_merge")
```

- [ ] **Step 5: Make `panel/luna_tools.py` delegate schema generation**

Keep `LunaToolbox` executors temporarily, but replace duplicated `tool_schemas()` metadata with:

```python
def tool_schemas() -> list[dict]:
    from .luna_capabilities import build_capability_registry
    return build_capability_registry().tool_schemas()
```

If Builder schemas are still separate during migration, merge them into the registry in Task 9 and keep compatibility until then.

- [ ] **Step 6: Run registry and existing Luna schema tests**

```bash
python -m pytest -q tests/test_luna_capability_registry.py tests/test_panel_luna_operator_v41.py
```

- [ ] **Step 7: Commit**

```bash
git add panel/luna_capabilities.py panel/luna_tools.py tests/test_luna_capability_registry.py
git commit -m "refactor: centralize Luna capability metadata"
```

---

### Task 5: Frozen Mutation Proposals with Expiry and Target Fingerprints

**Files:**
- Create: `panel/luna_proposals.py`
- Test: `tests/test_luna_control_center.py`

**Interfaces:**
- Produces: `ProposalStore.create(...)`, `ProposalStore.get_pending(action_id)`, `ProposalStore.complete(...)`, `proposal_fingerprint(value) -> str`.
- Consumes: editorial JSON repository; UTC timestamps.

- [ ] **Step 1: Write frozen-payload and expiry tests**

```python
def test_confirmation_executes_frozen_payload_not_new_user_text():
    store = ProposalStore(data, ttl_minutes=15)
    proposal = store.create(
        capability="rename_source",
        target={"type": "source", "id": "src-1"},
        payload={"source_id": "src-1", "display_name": "کلش ریپورتز"},
        summary_fa="نام منبع تغییر کند؟",
        before={"display_name": "ClashReports"},
        after={"display_name": "کلش ریپورتز"},
        target_fingerprint="abc",
    )
    loaded = store.get_pending(proposal["id"])
    assert loaded["payload"] == {"source_id": "src-1", "display_name": "کلش ریپورتز"}


def test_expired_proposal_is_not_executable():
    store = ProposalStore(data, ttl_minutes=-1)
    proposal = store.create(
        capability="disable_source",
        target={"type": "source", "id": "src-1"},
        payload={"source_id": "src-1"},
        summary_fa="خاموش شود؟",
        before={},
        after={},
        target_fingerprint="abc",
    )
    assert store.get_pending(proposal["id"])["status"] == "expired"
```

- [ ] **Step 2: Run and confirm RED**

```bash
python -m pytest -q tests/test_luna_control_center.py -k "frozen_payload or expired_proposal"
```

- [ ] **Step 3: Implement proposal envelope**

```python
def proposal_fingerprint(value: dict) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ProposalStore:
    PATH = "data/panel_pending_actions.json"

    def __init__(self, data, ttl_minutes: int = 15) -> None:
        self.data = data
        self.ttl_minutes = ttl_minutes

    def create(self, *, capability: str, target: dict, payload: dict, summary_fa: str,
               before: dict, after: dict, target_fingerprint: str) -> dict:
        now = datetime.now(timezone.utc)
        record = {
            "id": uuid4().hex,
            "capability": capability,
            "target": dict(target),
            "payload": dict(payload),
            "summary_fa": summary_fa,
            "before": dict(before),
            "after": dict(after),
            "target_fingerprint": target_fingerprint,
            "status": "pending",
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(minutes=self.ttl_minutes)).isoformat(),
        }
        self._prepend(record)
        return record
```

Implement `get_pending()` so expired pending rows are returned as `status="expired"` and cannot execute. Implement `complete(action_id, status, result)` with compare/retry behavior matching existing repository writers.

- [ ] **Step 4: Add changed-target rejection test**

```python
def test_changed_target_after_proposal_fails_closed():
    runtime = _runtime_with_source("src-1", display_name="ClashReports")
    proposal = runtime.propose("rename_source", {"source_id": "src-1", "display_name": "کلش ریپورتز"})
    runtime.toolbox.force_source_display_name("src-1", "نام جدید بیرونی")

    result = runtime.confirm(proposal["id"])

    assert result["ok"] is False
    assert result["error"] == "target_changed"
```

- [ ] **Step 5: Run proposal tests**

```bash
python -m pytest -q tests/test_luna_control_center.py -k "proposal or target_changed"
```

- [ ] **Step 6: Commit**

```bash
git add panel/luna_proposals.py tests/test_luna_control_center.py
git commit -m "feat: add frozen Luna mutation proposals"
```

---

### Task 6: Structured Context Resolver for Story and Source References

**Files:**
- Create: `panel/luna_context.py`
- Modify: `panel/luna_conversation.py`
- Test: `tests/test_luna_control_center.py`

**Interfaces:**
- Produces: `LunaContextResolver.resolve_source(args, context)`, `resolve_story(args, context)`, structured context keys `last_story_id`, `last_source_id`, `last_action_id`, `last_builder_pr`.
- Consumes: `LunaToolbox._sources()`, story rows, normalized names/handles.

- [ ] **Step 1: Write exact and ambiguous resolver tests**

```python
def test_source_resolver_matches_normalized_display_name_or_handle():
    resolver = LunaContextResolver(toolbox)
    result = resolver.resolve_source({"query": "ClashReports"}, {})
    assert result["ok"] is True
    assert result["source"]["id"] == "src-clash"


def test_source_resolver_refuses_ambiguous_mutation_target():
    resolver = LunaContextResolver(toolbox_with_two_clash_sources())
    result = resolver.resolve_source({"query": "clash"}, {})
    assert result["ok"] is False
    assert result["error"] == "ambiguous_source"
    assert len(result["matches"]) == 2


def test_pronoun_story_resolution_uses_structured_last_story_id():
    resolver = LunaContextResolver(toolbox)
    result = resolver.resolve_story({}, {"last_story_id": "story-9"})
    assert result["ok"] is True
    assert result["story"]["id"] == "story-9"
```

- [ ] **Step 2: Run and confirm RED**

```bash
python -m pytest -q tests/test_luna_control_center.py -k "resolver"
```

- [ ] **Step 3: Implement resolver precedence**

In `panel/luna_context.py`, enforce:

```python
SOURCE_KEYS = ("source_id", "query")
STORY_KEYS = ("story_id",)

class LunaContextResolver:
    def __init__(self, toolbox) -> None:
        self.toolbox = toolbox

    def resolve_source(self, args: dict, context: dict) -> dict:
        if str(args.get("source_id") or "").strip():
            return self._source_by_id(str(args["source_id"]).strip())
        query = str(args.get("query") or "").strip()
        if query:
            return self._source_by_normalized_query(query)
        if str(context.get("last_source_id") or "").strip():
            return self._source_by_id(str(context["last_source_id"]))
        return {"ok": False, "error": "source_target_required", "message": "منبع دقیق مشخص نیست."}
```

Exact normalized name/handle/ID match wins. Substring/fuzzy results are allowed only for discovery; more than one candidate returns `ambiguous_source` and no mutation proposal is created.

- [ ] **Step 4: Extend conversation store with structured context**

Add methods with backward-compatible storage:

```python
def get_context(self, conversation_id: str) -> dict:
    record = self._conversation_record(conversation_id)
    value = record.get("context") if isinstance(record, dict) else {}
    return dict(value) if isinstance(value, dict) else {}


def update_context(self, conversation_id: str, **values) -> dict:
    allowed = {"last_story_id", "last_source_id", "last_action_id", "last_builder_pr"}
    clean = {k: v for k, v in values.items() if k in allowed and v not in (None, "")}
    return self._mutate_context(conversation_id, clean)
```

Do not store secrets or provider payloads in context.

- [ ] **Step 5: Run resolver/conversation tests**

```bash
python -m pytest -q tests/test_luna_control_center.py -k "resolver or structured_context"
```

- [ ] **Step 6: Commit**

```bash
git add panel/luna_context.py panel/luna_conversation.py tests/test_luna_control_center.py
git commit -m "feat: add structured Luna entity context"
```

---

### Task 7: Unified Control Runtime and Audited Confirmation

**Files:**
- Create: `panel/luna_control_runtime.py`
- Modify: `panel/luna_tool_runtime.py`
- Modify: `panel/luna_operator_api.py`
- Test: `tests/test_luna_control_center.py`
- Test: `tests/test_panel_luna_operator_v41.py`

**Interfaces:**
- Produces: `LunaControlRuntime.invoke(name, args, context) -> dict`, `confirm(action_id) -> dict`.
- Consumes: capability registry, resolver, proposal store, existing `LunaToolbox`, translator client, Builder release adapters.

- [ ] **Step 1: Write read-vs-mutation runtime tests**

```python
def test_read_only_capability_executes_immediately_without_proposal():
    runtime = _runtime()
    result = runtime.invoke("inspect_panel_state", {}, {})
    assert result["ok"] is True
    assert result.get("confirmation_required") is not True


def test_mutation_returns_frozen_proposal_before_execution():
    runtime = _runtime_with_source("src-clash", display_name="ClashReports")
    result = runtime.invoke(
        "rename_source",
        {"source_id": "src-clash", "display_name": "کلش ریپورتز"},
        {},
    )
    assert result["ok"] is True
    assert result["confirmation_required"] is True
    assert result["summary_fa"] == "نام نمایشی ClashReports به «کلش ریپورتز» تغییر کند؟"
    assert _source_name(runtime, "src-clash") == "ClashReports"
```

- [ ] **Step 2: Run and confirm RED**

```bash
python -m pytest -q tests/test_luna_control_center.py -k "read_only_capability or mutation_returns_frozen"
```

- [ ] **Step 3: Implement registry-driven invoke path**

```python
class LunaControlRuntime:
    def __init__(self, *, registry, toolbox, resolver, proposals, provider_client=None, audit=None) -> None:
        self.registry = registry
        self.toolbox = toolbox
        self.resolver = resolver
        self.proposals = proposals
        self.provider_client = provider_client
        self.audit = audit

    def invoke(self, name: str, args: dict, context: dict) -> dict:
        capability = self.registry.get(name)
        resolved = self._resolve(capability, dict(args or {}), context)
        if not resolved["ok"]:
            return resolved
        if not capability.mutates:
            result = self._execute(capability, resolved["args"], confirmed=True)
            self._audit(capability, "success" if result.get("ok") else "failed", resolved, result)
            return result
        preview = self._preview(capability, resolved["args"])
        proposal = self.proposals.create(
            capability=capability.name,
            target=preview["target"],
            payload=preview["payload"],
            summary_fa=preview["summary_fa"],
            before=preview["before"],
            after=preview["after"],
            target_fingerprint=preview["target_fingerprint"],
        )
        return {
            "ok": True,
            "confirmation_required": True,
            "action_id": proposal["id"],
            "summary_fa": proposal["summary_fa"],
        }
```

- [ ] **Step 4: Implement exact confirmation path**

```python
def confirm(self, action_id: str) -> dict:
    proposal = self.proposals.get_pending(action_id)
    if proposal.get("status") != "pending":
        return {"ok": False, "error": "proposal_not_pending", "message": "این تأیید دیگر معتبر نیست."}
    current = self._current_target_snapshot(proposal)
    if proposal_fingerprint(current) != proposal["target_fingerprint"]:
        self.proposals.complete(action_id, "failed", {"error": "target_changed"})
        return {"ok": False, "error": "target_changed", "message": "هدف از زمان پیشنهاد تغییر کرده؛ دوباره دستور بده."}
    capability = self.registry.get(proposal["capability"])
    result = self._execute(capability, dict(proposal["payload"]), confirmed=True)
    self.proposals.complete(action_id, "success" if result.get("ok") else "failed", result)
    self._audit(capability, "success" if result.get("ok") else "failed", proposal, result)
    return result
```

- [ ] **Step 5: Route `execute_luna_tool` through runtime**

Keep its external signature for compatibility, but make it a thin adapter that calls `runtime.invoke(...)` or `runtime.confirm(...)`. Remove per-tool duplicated confirmation policy once the registry owns it.

- [ ] **Step 6: Replace ad-hoc pending creation in operator endpoint**

In `panel/luna_operator_api.py`, the tool-call loop should call the control runtime. If a result includes `confirmation_required`, return the action ID and summary without creating a second pending action.

The existing stateless continuation logic must remain unchanged: never reintroduce `previous_response_id` while `store:false` is used.

- [ ] **Step 7: Add false-success regression test**

```python
def test_operator_does_not_claim_success_when_executor_failed(client, fake_luna):
    fake_luna.queue_tool_call("disable_source", {"source_id": "missing"})
    response = client.post("/api/panel/luna/operator-chat", json={"message": "این منبع رو خاموش کن"})
    payload = response.get_json()
    assert payload["ok"] is True
    assert any(event["ok"] is False for event in payload["tool_events"])
    assert "انجام شد" not in payload["reply_fa"]
```

- [ ] **Step 8: Run operator/control tests**

```bash
python -m pytest -q tests/test_luna_control_center.py tests/test_panel_luna_operator_v41.py tests/test_panel_luna_stateless_continuation_v41.py
```

- [ ] **Step 9: Commit**

```bash
git add panel/luna_control_runtime.py panel/luna_tool_runtime.py panel/luna_operator_api.py tests/test_luna_control_center.py tests/test_panel_luna_operator_v41.py
git commit -m "feat: route Luna through confirmed control runtime"
```

---

### Task 8: Source Rename and Review-Only Policy Capabilities

**Files:**
- Modify: `panel/luna_tools.py`
- Modify: `panel/luna_control_runtime.py`
- Test: `tests/test_luna_control_center.py`

**Interfaces:**
- Produces: executors `rename_source`, `set_source_review_only`; source display overrides persist without mutating external identity/handle.
- Consumes: existing system-source overrides and custom-source repository paths.

- [ ] **Step 1: Write the ClashReports acceptance test**

```python
def test_clashreports_can_be_renamed_to_persian_after_confirmation():
    runtime = _runtime_with_source("src-clash", display_name="ClashReports", identity="ClashReports")
    proposal = runtime.invoke(
        "rename_source",
        {"query": "ClashReports", "display_name": "کلش ریپورتز"},
        {},
    )
    assert proposal["confirmation_required"] is True
    assert "ClashReports" in proposal["summary_fa"]
    assert "کلش ریپورتز" in proposal["summary_fa"]

    result = runtime.confirm(proposal["action_id"])

    assert result["ok"] is True
    source = runtime.toolbox._resolve_source({"source_id": "src-clash"})[0]
    assert source["name"] == "کلش ریپورتز"
    assert source["identity"] == "ClashReports"
```

- [ ] **Step 2: Write review-only policy test**

```python
def test_source_review_only_policy_requires_confirmation_and_persists():
    runtime = _runtime_with_source("src-1", display_name="Source One")
    proposal = runtime.invoke("set_source_review_only", {"source_id": "src-1", "enabled": True}, {})
    assert proposal["confirmation_required"] is True
    result = runtime.confirm(proposal["action_id"])
    assert result["ok"] is True
    assert _source_policy(runtime, "src-1")["review_only"] is True
```

- [ ] **Step 3: Run and confirm RED**

```bash
python -m pytest -q tests/test_luna_control_center.py -k "clashreports or review_only"
```

- [ ] **Step 4: Implement safe source display-name persistence**

For custom sources, update only `display_name`/`name`. For system sources, store a display-name override in `data/source_overrides.json` alongside existing active/hidden state, for example:

```json
{
  "src-clash": {
    "active": true,
    "display_name": "کلش ریپورتز"
  }
}
```

Update `_sources()` to apply `display_name` override to the public `name` while leaving `handle`, `channel`, URL, and identity untouched.

- [ ] **Step 5: Implement review-only policy persistence**

Persist `review_only: true|false` in the same source override/custom-source record and expose it through `_source_public()` so ingestion/routing code can consume the exact policy. If a current routing hook already reads source overrides, wire the flag there; otherwise add the smallest adapter at the existing source routing decision point and cover it with a focused policy test.

- [ ] **Step 6: Run source tests**

```bash
python -m pytest -q tests/test_luna_control_center.py tests/test_panel_luna_tools_v41.py tests/test_source_manager.py
```

- [ ] **Step 7: Commit**

```bash
git add panel/luna_tools.py panel/luna_control_runtime.py tests/test_luna_control_center.py
git commit -m "feat: let Luna rename and route sources safely"
```

---

### Task 9: Story Mutation Capabilities Use the Same Confirmed Runtime

**Files:**
- Modify: `panel/luna_control_runtime.py`
- Modify: `panel/luna_publish.py`
- Modify: `panel/luna_translation.py`
- Test: `tests/test_luna_control_center.py`

**Interfaces:**
- Produces: registry actions for `translate_story`, `publish_story(copy_mode)`, `move_story_to_review`, `reject_and_block_story`.
- Consumes: existing guarded Luna translation pipeline, persisted machine Persian copy, V3 publish queue, existing block/review mechanisms.

- [ ] **Step 1: Write natural story-action confirmation tests**

```python
def test_publish_machine_capability_freezes_copy_mode_and_story_id():
    runtime = _runtime_with_story("story-1", persian_title="تیتر ماشینی")
    proposal = runtime.invoke(
        "publish_story",
        {"story_id": "story-1", "copy_mode": "machine"},
        {},
    )
    assert proposal["confirmation_required"] is True
    saved = runtime.proposals.get_pending(proposal["action_id"])
    assert saved["payload"]["story_id"] == "story-1"
    assert saved["payload"]["copy_mode"] == "machine"


def test_luna_translation_is_a_mutation_and_requires_confirmation_to_save():
    runtime = _runtime_with_story("story-1", original_title="Breaking update")
    proposal = runtime.invoke("translate_story", {"story_id": "story-1"}, {})
    assert proposal["confirmation_required"] is True
```

- [ ] **Step 2: Run and confirm RED where current tools execute early**

```bash
python -m pytest -q tests/test_luna_control_center.py -k "publish_machine_capability or translation_is_a_mutation"
```

- [ ] **Step 3: Ensure translation proposal means “generate/save Luna copy”**

Preview text must be explicit, for example:

```python
summary_fa = f"Luna این خبر را ترجمه و نسخه ویرایش‌شده را روی کارت ذخیره کند؟ «{original_title[:120]}»"
```

After confirmation, call `translate_story_in_repository(...)` exactly once and audit the returned validation status.

- [ ] **Step 4: Ensure publish preview identifies selected copy**

For machine:

```python
summary_fa = f"همین ترجمه ماشینی منتشر شود؟ «{machine_title}»"
```

For Luna:

```python
summary_fa = f"نسخه Luna منتشر شود؟ «{luna_title}»"
```

The confirmed executor calls `publish_story(..., copy_mode=...)` through `v3_publish` only.

- [ ] **Step 5: Keep block/review semantics traceable**

`reject_and_block_story` must retain the story in history/audit while removing it from future publication cycle. `move_story_to_review` must not publish or block. Both mutations require a proposal before execution.

- [ ] **Step 6: Run full story capability tests**

```bash
python -m pytest -q tests/test_luna_control_center.py tests/test_panel_luna_translation_v41.py tests/test_panel_luna_publish_v41.py
```

- [ ] **Step 7: Commit**

```bash
git add panel/luna_control_runtime.py panel/luna_publish.py panel/luna_translation.py tests/test_luna_control_center.py
git commit -m "feat: unify confirmed Luna story actions"
```

---

### Task 10: Diagnostics and Safe Operator Settings

**Files:**
- Modify: `panel/luna_capabilities.py`
- Modify: `panel/luna_control_runtime.py`
- Modify: `panel/luna_tools.py`
- Test: `tests/test_luna_control_center.py`

**Interfaces:**
- Produces: immediate read-only diagnostic capabilities; narrowly-scoped mutating settings such as newsroom alarm mute and machine-translation behavior.
- Does not produce: generic environment-variable editor or arbitrary process control.

- [ ] **Step 1: Write diagnosis-no-confirmation test**

```python
def test_diagnose_newsroom_runs_without_confirmation():
    runtime = _runtime()
    result = runtime.invoke("diagnose_newsroom", {}, {})
    assert result["ok"] is True
    assert result.get("confirmation_required") is not True
    assert "queues" in result
```

- [ ] **Step 2: Write setting-confirmation test**

```python
def test_alarm_mute_setting_requires_confirmation():
    runtime = _runtime()
    proposal = runtime.invoke("set_newsroom_alarm", {"enabled": False}, {})
    assert proposal["confirmation_required"] is True
    result = runtime.confirm(proposal["action_id"])
    assert result["ok"] is True
    assert result["enabled"] is False
```

- [ ] **Step 3: Add only narrow setting schemas**

Register:

```python
Capability(
    name="set_newsroom_alarm",
    domain="settings",
    description="فعال یا بی‌صدا کردن آلارم خبر جدید پنل.",
    parameters={
        "type": "object",
        "properties": {"enabled": {"type": "boolean"}},
        "required": ["enabled"],
        "additionalProperties": False,
    },
    mutates=True,
    requires_confirmation=True,
    executor_name="set_newsroom_alarm",
)
```

Store it in the existing operator-facing settings JSON used by the panel. Do not add a generic “set env var” capability.

- [ ] **Step 4: Keep diagnosis factual**

Return queue counts, recent command failures, translation failures, source health available to application code, and Builder status. Any proposed fix is a separate mutation proposal; diagnosis itself never silently edits data.

- [ ] **Step 5: Run tests**

```bash
python -m pytest -q tests/test_luna_control_center.py -k "diagnose or alarm_mute"
```

- [ ] **Step 6: Commit**

```bash
git add panel/luna_capabilities.py panel/luna_control_runtime.py panel/luna_tools.py tests/test_luna_control_center.py
git commit -m "feat: add Luna diagnostics and safe settings"
```

---

### Task 11: Bring Builder Into the Same Capability/Confirmation Contract

**Files:**
- Modify: `panel/luna_capabilities.py`
- Modify: `panel/luna_control_runtime.py`
- Modify: `panel/luna_operator_api.py`
- Modify: `panel/luna_builder.py`
- Modify: `panel/luna_builder_tools.py`
- Test: `tests/test_luna_control_center.py`
- Test: existing Builder tests

**Interfaces:**
- Produces: `builder_prepare`, `builder_ci_status`, `builder_prepare_merge` as registry capabilities.
- Preserves: branch/test/Draft PR/CI/confirmed merge flow; no direct production edits.

- [ ] **Step 1: Write Builder confirmation boundary test**

```python
def test_builder_code_change_requires_confirmation_before_branch_creation():
    runtime = _runtime_with_fake_builder()
    proposal = runtime.invoke(
        "builder_prepare",
        {"request": "این دکمه رو ببر سمت راست"},
        {},
    )
    assert proposal["confirmation_required"] is True
    assert runtime.fake_builder.created_branches == []

    result = runtime.confirm(proposal["action_id"])
    assert result["ok"] is True
    assert len(runtime.fake_builder.created_branches) == 1
```

- [ ] **Step 2: Write CI-green merge guard test**

```python
def test_builder_merge_refuses_non_green_ci_even_after_confirmation():
    runtime = _runtime_with_fake_builder(ci_green=False)
    proposal = runtime.invoke("builder_prepare_merge", {"pr_number": 123}, {})
    result = runtime.confirm(proposal["action_id"])
    assert result["ok"] is False
    assert result["error"] == "builder_ci_not_green"
```

- [ ] **Step 3: Run and confirm RED if Builder still bypasses unified proposals**

```bash
python -m pytest -q tests/test_luna_control_center.py -k "builder_code_change or builder_merge"
```

- [ ] **Step 4: Register Builder capabilities**

Make `builder_ci_status` read-only. Make `builder_prepare` and `builder_prepare_merge` mutations requiring confirmation. The merge proposal must freeze both `pr_number` and `expected_head_sha`.

- [ ] **Step 5: Remove special-case confirmation creation from operator endpoint**

`is_builder_request(message)` may still classify natural code/UI requests, but it should invoke the registry capability `builder_prepare` rather than writing its own pending action format.

- [ ] **Step 6: Run Builder + control tests**

```bash
python -m pytest -q tests/test_luna_control_center.py tests/test_panel_luna_builder_v41.py tests/test_github_builder.py
```

- [ ] **Step 7: Commit**

```bash
git add panel/luna_capabilities.py panel/luna_control_runtime.py panel/luna_operator_api.py panel/luna_builder.py panel/luna_builder_tools.py tests/test_luna_control_center.py
git commit -m "refactor: unify Builder under Luna control policy"
```

---

### Task 12: Operator UX, Natural Persian Behavior, and Minimal Model Rounds

**Files:**
- Modify: `panel/luna_operator_api.py`
- Modify: `panel/static/luna-assistant.js`
- Test: `tests/test_panel_luna_operator_v41.py`
- Test: `tests/test_luna_control_center.py`

**Interfaces:**
- Consumes: unified proposal payload with `action_id`, `summary_fa`, optional before/after.
- Produces: one confirmation UI for all mutations; structured context update after successful reads/proposals/executions.

- [ ] **Step 1: Add natural-language source rename integration test**

```python
def test_natural_clashreports_rename_returns_specific_confirmation(client, fake_luna):
    fake_luna.queue_tool_call(
        "rename_source",
        {"query": "ClashReports", "display_name": "کلش ریپورتز"},
    )
    response = client.post(
        "/api/panel/luna/operator-chat",
        json={"message": "لونا کلش ریپورتز رو فارسی بنویس و اصلاح کن"},
    )
    payload = response.get_json()
    assert payload["confirmation_required"] is True
    assert "ClashReports" in payload["summary_fa"]
    assert "کلش ریپورتز" in payload["summary_fa"]
```

- [ ] **Step 2: Tighten the system instruction**

Keep the prompt concise and policy-aligned:

```text
تو Luna، کنترل‌گر عملیاتی فارسی اتاق خبر بی‌خبر هستی.
برای هر درخواست از capabilityهای تعریف‌شده استفاده کن.
کارهای فقط خواندنی را مستقیم انجام بده.
هر کاری که داده، تنظیمات، انتشار، منبع، کد، UI یا deployment را تغییر می‌دهد باید به proposal تأیید برسد و قبل از تأیید اجرا نشود.
اگر هدف مبهم است، یک سؤال کوتاه بپرس و هیچ mutation نساز.
موفقیت را فقط وقتی اعلام کن که executor نتیجه ok داده باشد.
```

- [ ] **Step 3: Avoid unnecessary model continuation after a pending mutation**

When a tool returns a confirmation proposal, the server already has the exact `summary_fa`. Return that concise confirmation immediately instead of paying another provider round solely to paraphrase it. Continue model rounds only when another read-only tool result is needed to answer the user.

This is the main latency reduction for simple mutating commands.

- [ ] **Step 4: Use one generic confirmation renderer in `luna-assistant.js`**

```javascript
function renderPendingAction(payload) {
  confirmationBox.hidden = false;
  confirmationText.textContent = payload.summary_fa || 'این تغییر انجام شود؟';
  confirmButton.dataset.actionId = payload.action_id || '';
}
```

All mutation types use the same action ID confirmation endpoint.

- [ ] **Step 5: Update structured context only from concrete results**

After a successful story/source lookup, proposal, Builder status, or execution, update the corresponding `last_*` IDs server-side. Do not infer IDs from assistant prose.

- [ ] **Step 6: Run operator tests**

```bash
node --check panel/static/luna-assistant.js
python -m pytest -q tests/test_panel_luna_operator_v41.py tests/test_luna_control_center.py tests/test_panel_luna_stateless_continuation_v41.py
```

- [ ] **Step 7: Commit**

```bash
git add panel/luna_operator_api.py panel/static/luna-assistant.js tests/test_panel_luna_operator_v41.py tests/test_luna_control_center.py
git commit -m "feat: streamline Luna operator confirmations"
```

---

### Task 13: Full Regression, Security Checks, and Production-Safe Release

**Files:**
- Modify only if regressions require fixes in files owned by Tasks 1–12.
- Test: full repository suite and JS syntax checks.

**Interfaces:**
- Produces: merge-ready branch with green `Pull Request Check` and `Telegram News Agent CI`.

- [ ] **Step 1: Run all JavaScript syntax checks used by CI**

```bash
node --check docs/newsroom-v1.js
node --check panel/static/newsroom-ui.js
node --check panel/static/newsroom-live.js
node --check panel/static/newsroom-actions.js
node --check panel/static/newsroom-editor.js
node --check panel/static/newsroom-v4.js
node --check panel/static/newsroom-v4-dashboard.js
node --check panel/static/luna-assistant.js
```

Expected: all exit 0.

- [ ] **Step 2: Run the complete Python regression suite**

```bash
python -m pytest -q
```

Expected: all tests pass except any pre-existing intentionally skipped tests.

- [ ] **Step 3: Add/verify explicit security regression assertions**

Ensure tests assert that no registered capability is named or described as arbitrary shell/SQL/filesystem/env access:

```python
def test_registry_exposes_no_generic_dangerous_capability():
    names = {cap.name for cap in build_capability_registry().all()}
    forbidden = {"shell", "exec", "run_command", "sql", "set_env", "read_secret", "http_proxy"}
    assert not names.intersection(forbidden)
```

Also verify publishing tests only observe `v3_publish`, never a direct Telegram send call.

- [ ] **Step 4: Verify dashboard behavior contract**

Run:

```bash
python -m pytest -q tests/test_panel_v41_live_operator_flow.py
```

Expected coverage includes machine persistence, direct/Luna copy choice, one-shot alarm contract, and terminal-success card removal.

- [ ] **Step 5: Verify Luna control-center acceptance tests**

```bash
python -m pytest -q tests/test_luna_capability_registry.py tests/test_luna_control_center.py tests/test_panel_luna_operator_v41.py
```

Expected: PASS.

- [ ] **Step 6: Open Draft PR and wait for both required CI workflows**

Create one implementation PR against `main`. Required checks:

```text
Pull Request Check
Telegram News Agent CI
```

Do not merge while either is queued, running, skipped unexpectedly, or failed.

- [ ] **Step 7: Whole-branch review against the spec**

Reviewer verifies:

```text
- every mutation is proposal-gated
- confirmation executes frozen payload
- ambiguous target fails closed
- machine and Luna publishing remain distinct
- v3_publish remains authoritative
- Builder remains CI-gated
- no direct production edit path exists
- live dashboard does not hide queued/failed publications
- no provider key/secret is logged or audited
```

- [ ] **Step 8: Merge only after green CI and explicit operator approval**

Use squash merge to `main`. Let the existing main CI promote the exact tested SHA to `production`.

- [ ] **Step 9: Verify deployed SHA and panel service on VPS**

Operator command, one command at a time:

```bash
sudo systemctl start bikhabar-deploy.service && sleep 5 && echo "HEAD=$(git -C /opt/bikhabar/app rev-parse HEAD)" && echo "PANEL=$(systemctl is-active bikhabar-panel.service)"
```

Expected: `HEAD` equals the promoted production SHA and `PANEL=active`.

- [ ] **Step 10: Live smoke in this order**

```text
1. New English story appears → machine Persian becomes primary card copy.
2. A subsequent new story after first browser interaction → one short alarm.
3. Direct publish machine copy → card stays while queued, disappears only after terminal success.
4. Luna translate → passed Luna copy → publish Luna copy after confirmation.
5. Luna: «ClashReports رو فارسی بنویس و اصلاح کن» → specific rename proposal → confirm → visible source name changes.
6. Luna read-only diagnosis → immediate result without confirmation.
7. Luna code/UI request → Builder proposal only; no branch before confirmation.
8. Builder CI merge request → merge blocked unless CI is fully green.
```

- [ ] **Step 11: Final commit for any review-only fixes, rerun full suite, and update PR**

```bash
python -m pytest -q
```

Expected: green before final merge.
