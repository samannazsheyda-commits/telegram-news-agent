# Luna Control Center Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn Luna into the confirmed natural-language control surface for the Bikhabar newsroom while fixing the live dashboard so every incoming story gets a persistent machine Persian copy, can be published directly or via Luna, plays a one-shot new-story alarm, disappears only after confirmed publication success, and can be rejected without creating any permanent block.

**Architecture:** Preserve the existing V4.1 Flask/JSON/command-queue/Builder stack and introduce a small Luna Control Center layer around it. A central capability registry describes allowed actions, a resolver maps natural references to concrete entities, and a frozen mutation-proposal service enforces confirmation and audit before any state change. Existing safe executors remain authoritative: translation uses the configured machine translator and Luna translation pipeline, publication uses `v3_publish`, and code/UI changes use Builder branch/PR/CI/merge.

**Tech Stack:** Python 3.12, Flask 3.1, Jinja2, vanilla JavaScript, pytest, requests, existing local JSON repository, existing Newsroom V3 command queue, existing GitHub Builder integration, 1xAI OpenAI-compatible Responses API.

**Spec:** `docs/superpowers/specs/2026-09-19-luna-control-center-design.md`

## Global Constraints

- Read-only inspection and diagnosis may execute immediately.
- Every mutation must stop at an explicit human-confirmation boundary immediately before execution.
- Confirmation executes the exact frozen proposal payload; it must not reinterpret the original natural-language request.
- Luna may report success only after the actual executor returns success.
- Publishing must continue through the existing `v3_publish` command path.
- Code/UI changes must continue through Builder branch → tests → Draft PR → CI → explicit merge confirmation → existing promotion.
- Luna must never receive arbitrary shell, SQL, filesystem, environment-variable, secret-retrieval, unrestricted HTTP-proxy, direct Telegram-write, or direct production-edit powers.
- Reject means **reject this story only**. It must not create an operator block, blacklist, source block, or any permanent future suppression.
- Incoming non-Persian stories must receive a persisted machine Persian title/body suitable for operator review and direct publishing.
- The original-language story remains available through the original/source view, not as the primary dashboard card copy.
- A published card leaves the active dashboard only after a terminal successful publication state, never merely after enqueue.
- New-story audio must not fire on initial page load and must not repeat for the same story ID.
- The configured 1xAI provider must keep using stateless Responses API continuation; do not restore `previous_response_id` with `store:false`.
- The active newsroom must remain usable during migration; no rewrite or flag day.

## Review Focus

1. **A story arrives while machine translation fails or times out:** keep the card visible with a retryable pending state; never publish untranslated English as Persian copy. Covered in Task 1 tests.
2. **Two sources have similar names:** do not mutate either one; Luna must ask for clarification. Covered in Task 5 resolver tests.
3. **A frozen proposal targets a record that changed before confirmation:** fail closed with a stale-proposal result and require a fresh proposal. Covered in Task 4 tests.
4. **A publish command is queued but Telegram publication fails:** keep the card on the active dashboard and show the actual error. Covered in Task 2 dashboard/publish tests.
5. **The browser has not unlocked audio yet:** polling must continue normally and the first new-story sound should only become eligible after a real user interaction. Covered in Task 3 tests.

---

## File Structure and Responsibility Map

### Existing files to modify

- `panel/live_api.py` — live-feed serialization plus persistent machine-localization endpoint; stop relying on in-memory translation as the only publishable copy.
- `panel/wsgi.py` — keep `LIVE_FEED_TRANSLATOR=translate_to_fa` as the configured machine translator consumed by `live_api.py`.
- `panel/luna_publish.py` — explicit `machine` vs `luna` copy selection before enqueueing `v3_publish`.
- `panel/luna_translation_api.py` — dashboard endpoints for machine/Luna publishing and reject-only action.
- `panel/templates/dashboard.html` — distinct direct-publish/Luna-publish buttons and reject-only copy.
- `panel/static/newsroom-v4-dashboard.js` — auto-localization batches, live polling, one-shot alarm, direct/Luna publish, reject-only, remove card after confirmed publish.
- `panel/static/sw.js` — bump cache key after dashboard JavaScript changes.
- `panel/luna_tools.py` — migrate exposed tools to registry-backed schemas; remove `reject_and_block_story`; preserve narrow source/story executors until migrated.
- `panel/luna_tool_runtime.py` — route registry capability execution to translation, publishing, source/story executors, and Builder adapters.
- `panel/luna_operator_api.py` — use resolver/registry/proposals; keep stateless 1xAI response continuation.
- `panel/source_manager.py` — honor source display-name overrides and review-only policy in the same storage read by Luna.
- `panel/luna_conversation.py` — persist bounded structured context IDs alongside recent text, if the existing store does not already expose metadata.
- `panel/luna_builder.py`, `panel/luna_builder_tools.py`, `panel/github_builder_release.py` — adapt Builder actions into the shared confirmation/proposal contract without weakening CI gates.

### New focused files

- `panel/luna_capabilities.py` — `Capability` metadata and registry; single source of truth for tool schema and confirmation classification.
- `panel/luna_proposals.py` — frozen mutation proposals, expiry, target version/hash, confirmation execution contract, audit envelope.
- `panel/luna_context.py` — exact story/source resolution and bounded conversation entity context.
- `panel/luna_story_actions.py` — reject-only story mutation and story-specific control-center executors.
- `panel/luna_source_actions.py` — source rename/state/routing mutations with system/custom source storage adapters.

### Tests

- `tests/test_panel_v41_live_operator_flow.py` — dashboard machine translation, publish modes, reject-only, alarm/removal contract.
- `tests/test_luna_capabilities.py` — registry metadata and generated schemas.
- `tests/test_luna_proposals.py` — frozen proposals, expiry, stale target, audit.
- `tests/test_luna_context.py` — exact and ambiguous story/source resolution plus recent context.
- `tests/test_luna_story_actions.py` — reject-only and story mutation semantics.
- `tests/test_luna_source_actions.py` — rename/source state/review-only semantics.
- `tests/test_luna_operator_control_center.py` — model-tool integration, proposal/confirmation flow, stateless continuation.
- Existing Builder and Luna tests remain regression coverage.

### Superseded work

Draft PR `#161` (`hotfix/v41-live-alarm-machine-publish`) must **not** be merged as-is. During implementation, reuse only reviewed tests or isolated code that matches this plan, then close #161 as superseded after equivalent behavior is green on the new implementation branch.

---

### Task 1: Persist Machine Persian Copy for Every Live Story

**Files:**
- Modify: `panel/live_api.py` (`_translate_persian`, `_public_row`, `/api/live-feed/localize`)
- Verify wiring: `panel/wsgi.py`
- Test: `tests/test_panel_v41_live_operator_flow.py`
- Test: existing live-feed tests that cover `/api/live-feed`

**Interfaces:**
- Consumes: `current_app.config["LIVE_FEED_TRANSLATOR"]: Callable[[str], str]`
- Produces: persisted `persian_title`, `persian_body`, `machine_translation_status`, `machine_translation_updated_at` on rows in `data/panel_live_feed.json`
- Produces: `/api/live-feed/localize` response containing updated public rows

- [ ] **Step 1: Write failing persistence and failure-mode tests**

Add tests that inject a deterministic translator through app config and prove the localized copy is written back to the repository, not only cached:

```python
def test_machine_localization_persists_persian_copy_for_dashboard_and_publish():
    data = MemoryData()
    app = _app(data, translator=lambda text: {
        "Fresh English headline": "تیتر فارسی تازه",
        "English body": "متن فارسی تازه",
    }.get(text, text))

    response = _client(app).post("/api/live-feed/localize", json={"ids": ["story-1"]})

    assert response.status_code == 200
    row = data.mapping["data/panel_live_feed.json"][0]
    assert row["persian_title"] == "تیتر فارسی تازه"
    assert row["persian_body"] == "متن فارسی تازه"
    assert row["machine_translation_status"] == "ready"
```

Add a failure test:

```python
def test_machine_localization_failure_keeps_story_visible_and_marks_retryable():
    data = MemoryData()
    app = _app(data, translator=lambda _text: "")

    response = _client(app).post("/api/live-feed/localize", json={"ids": ["story-1"]})

    assert response.status_code == 200
    feed = _client(app).get("/api/live-feed").get_json()["items"]
    story = next(item for item in feed if item["id"] == "story-1")
    assert story["needs_localization"] is True
    assert story["machine_translation_status"] in {"pending", "failed"}
    assert story["can_publish"] is False
```

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```bash
python -m pytest -q tests/test_panel_v41_live_operator_flow.py -k 'machine_localization'
```

Expected: persistence/status assertions fail because current localization is only in memory/offline preview.

- [ ] **Step 3: Replace panel-only translation with configured translator and atomic persistence**

Implement a helper in `panel/live_api.py`:

```python
def _machine_translator():
    translator = current_app.config.get("LIVE_FEED_TRANSLATOR")
    if not callable(translator):
        raise RuntimeError("live_feed_translator_not_configured")
    return translator


def _persist_machine_copy(item_id: str, title_fa: str, body_fa: str, *, status: str) -> None:
    data = current_app.extensions["editorial_data"]
    for attempt in range(3):
        rows, sha = data.read_json("data/panel_live_feed.json", [])
        changed = []
        for raw in rows if isinstance(rows, list) else []:
            row = dict(raw) if isinstance(raw, dict) else raw
            if isinstance(row, dict) and _row_id(row) == item_id:
                if title_fa:
                    row["persian_title"] = title_fa
                if body_fa:
                    row["persian_body"] = body_fa
                row["machine_translation_status"] = status
                row["machine_translation_updated_at"] = datetime.now(timezone.utc).isoformat()
            changed.append(row)
        try:
            data.write_json(
                "data/panel_live_feed.json",
                changed,
                sha,
                "panel v4.1: persist machine Persian copy",
            )
            return
        except requests.HTTPError as exc:
            code = getattr(getattr(exc, "response", None), "status_code", None)
            if attempt < 2 and code in {409, 422}:
                continue
            raise
```

Use the configured translator for title/body in `/api/live-feed/localize`, validate Persian output, and persist `ready` only when the title is valid Persian. On empty/failed translation, leave the story available, mark retryable state where storage permits, and never overwrite a good existing machine copy with empty text.

- [ ] **Step 4: Make `/api/live-feed` prefer persisted machine copy**

Update `_public_row()` so its stable order is:

```python
persisted machine Persian -> source Persian -> pending placeholder
```

Keep Luna final copy separate; do not let `final_persian_title` masquerade as machine translation.

- [ ] **Step 5: Run focused tests and the existing live-feed regression set**

Run:

```bash
python -m pytest -q tests/test_panel_v41_live_operator_flow.py -k 'machine_localization'
python -m pytest -q -k 'live_feed or live_panel'
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add panel/live_api.py panel/wsgi.py tests/test_panel_v41_live_operator_flow.py
git commit -m "fix: persist live machine Persian translations"
```

---

### Task 2: Split Direct Machine Publish from Luna Publish and Reject Without Blocking

**Files:**
- Modify: `panel/luna_publish.py`
- Modify: `panel/luna_translation_api.py`
- Create: `panel/luna_story_actions.py`
- Modify: `panel/templates/dashboard.html`
- Modify: `panel/static/newsroom-v4-dashboard.js`
- Test: `tests/test_panel_v41_live_operator_flow.py`
- Create: `tests/test_luna_story_actions.py`

**Interfaces:**
- Produces: `publish_story(data, story_id, *, enqueue, confirmed=False, copy_mode="machine") -> dict`
- Produces: `reject_story(data, story_id, *, confirmed=False) -> dict`
- HTTP: `POST /api/panel/luna/publish-machine/<story_id>`
- HTTP: `POST /api/panel/luna/publish-final/<story_id>` for Luna copy
- HTTP: `POST /api/panel/luna/reject-story/<story_id>`

- [ ] **Step 1: Write failing publish-mode tests**

```python
def test_publish_mode_machine_uses_machine_copy_even_when_luna_copy_exists():
    row = _story(
        persian_title="ترجمه ماشینی مورد تأیید",
        persian_body="متن ماشینی.",
        final_persian_title="نسخه متفاوت لونا",
        final_persian_body="متن لونا.",
        luna_translation_status="passed",
    )
    data = MemoryData([row])
    captured = {}

    result = publish_story(
        data,
        row["id"],
        enqueue=lambda command, **kwargs: captured.update(command=command, **kwargs) or "cmd-1",
        confirmed=True,
        copy_mode="machine",
    )

    assert result["ok"] is True
    assert captured["command"] == "v3_publish"
    assert captured["title"] == "ترجمه ماشینی مورد تأیید"
```

```python
def test_publish_mode_luna_requires_passed_luna_copy():
    row = _story(persian_title="ترجمه ماشینی", luna_translation_status="not_started")
    result = publish_story(MemoryData([row]), row["id"], enqueue=lambda *a, **k: "x", confirmed=True, copy_mode="luna")
    assert result["ok"] is False
    assert result["error"] == "luna_copy_not_ready"
```

- [ ] **Step 2: Write failing reject-only tests**

```python
def test_reject_story_marks_only_that_story_and_creates_no_operator_block(tmp_path):
    data = MemoryData([_story(id="story-1"), _story(id="story-2")])

    result = reject_story(data, "story-1", confirmed=True)

    assert result["ok"] is True
    rows = data.mapping["data/panel_live_feed.json"]
    rejected = next(row for row in rows if row["id"] == "story-1")
    untouched = next(row for row in rows if row["id"] == "story-2")
    assert rejected["panel_status"] == "rejected"
    assert untouched["panel_status"] != "rejected"
    assert "block" not in json.dumps(data.mapping, ensure_ascii=False).lower()
```

Also assert the dashboard template contains `رد` and does not contain `رد و مسدودکردن`.

- [ ] **Step 3: Run focused tests and verify RED**

```bash
python -m pytest -q tests/test_panel_v41_live_operator_flow.py tests/test_luna_story_actions.py -k 'publish_mode or reject'
```

Expected: FAIL because current publish path chooses a single visible copy and current reject path blocks.

- [ ] **Step 4: Implement explicit copy selection in `panel/luna_publish.py`**

Use a strict selector:

```python
def _copy_for_mode(row: dict, copy_mode: str) -> tuple[str, str] | None:
    if copy_mode == "machine":
        title = str(row.get("persian_title") or "").strip()
        body = str(row.get("persian_body") or "").strip()
        return (title, body) if title and _FA_RE.search(title) else None
    if copy_mode == "luna":
        if str(row.get("luna_translation_status") or "") != "passed":
            return None
        title = str(row.get("final_persian_title") or "").strip()
        body = str(row.get("final_persian_body") or "").strip()
        return (title, body) if title and _FA_RE.search(title) else None
    raise ValueError("invalid_copy_mode")
```

The confirmation proposal must preserve `copy_mode` so confirmation cannot switch copies.

- [ ] **Step 5: Implement reject-only mutation**

`panel/luna_story_actions.py` should update only the matching live/review story record with:

```python
{
    "panel_status": "rejected",
    "decision_reason": "operator_rejected",
    "rejected_at": now_iso,
}
```

Do **not** call `add_operator_block`, do not modify `operator_blocks.json`, and do not suppress future stories from the same source.

- [ ] **Step 6: Add dashboard endpoints and distinct buttons**

`dashboard.html` actions:

```html
<button data-v4-action="publish-machine">انتشار مستقیم</button>
<button data-v4-action="translate-luna">ترجمه با Luna</button>
<button data-v4-action="publish-luna" {% if not final_ready %}hidden{% endif %}>انتشار با Luna</button>
<button data-v4-action="reject-story">رد</button>
```

`newsroom-v4-dashboard.js` should call machine/Luna endpoints separately and use a shared `publishCopy(card, mode)` function.

- [ ] **Step 7: Remove card only after actual publication success**

After `poll()` returns `succeeded` or `reconciled`:

```javascript
const done = await poll(queued.command_id, card);
progress(card, 'منتشر شد', 'success');
window.setTimeout(() => card.remove(), 180);
```

On `failed`, timeout, or request error, leave the card in place and show the actual error.

- [ ] **Step 8: Run focused tests**

```bash
python -m pytest -q tests/test_panel_v41_live_operator_flow.py tests/test_luna_story_actions.py
node --check panel/static/newsroom-v4-dashboard.js
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add panel/luna_publish.py panel/luna_translation_api.py panel/luna_story_actions.py panel/templates/dashboard.html panel/static/newsroom-v4-dashboard.js tests/test_panel_v41_live_operator_flow.py tests/test_luna_story_actions.py
git commit -m "fix: add direct publish and reject-only newsroom flow"
```

---

### Task 3: Add Live Polling, Auto-Localization, and One-Shot New-Story Alarm

**Files:**
- Modify: `panel/static/newsroom-v4-dashboard.js`
- Modify: `panel/static/sw.js`
- Test: `tests/test_panel_v41_live_operator_flow.py`

**Interfaces:**
- Consumes: `GET /api/live-feed`
- Consumes: `POST /api/live-feed/localize` with `{ids: string[]}`
- Browser state: `knownStoryIds: Set<string>`, `audioUnlocked: boolean`, `alarmMuted: boolean`

- [ ] **Step 1: Write dashboard contract tests for polling/alarm**

Assert the script contains stable behavior markers rather than implementation-private minification details:

```python
def test_v4_dashboard_has_live_poll_auto_localize_and_one_shot_alarm():
    js = Path("panel/static/newsroom-v4-dashboard.js").read_text(encoding="utf-8")
    assert "/api/live-feed" in js
    assert "/api/live-feed/localize" in js
    assert "knownStoryIds" in js
    assert "audioUnlocked" in js
    assert "playNewStoryAlarm" in js
```

Add a small pure-JS helper or exported testable function if needed so repeated IDs can be tested without a browser:

```javascript
function unseenIds(previous, current) {
  return current.filter(id => !previous.has(id));
}
```

- [ ] **Step 2: Run test and verify RED**

```bash
python -m pytest -q tests/test_panel_v41_live_operator_flow.py -k 'alarm or live_poll'
```

Expected: FAIL because current dashboard has no live-feed polling/alarm state.

- [ ] **Step 3: Implement initial-ID snapshot without alarm**

On first successful feed fetch:

```javascript
let initialized = false;
const knownStoryIds = new Set();

function absorbIds(items) {
  const ids = items.map(item => String(item.id || item.item_id || '')).filter(Boolean);
  if (!initialized) {
    ids.forEach(id => knownStoryIds.add(id));
    initialized = true;
    return [];
  }
  const fresh = ids.filter(id => !knownStoryIds.has(id));
  ids.forEach(id => knownStoryIds.add(id));
  return fresh;
}
```

- [ ] **Step 4: Unlock audio only after user interaction**

Use a lightweight Web Audio beep; do not add an external media dependency:

```javascript
let audioUnlocked = false;
let audioContext = null;

function unlockAudio() {
  if (audioUnlocked) return;
  const AudioContext = window.AudioContext || window.webkitAudioContext;
  if (!AudioContext) return;
  audioContext = audioContext || new AudioContext();
  audioContext.resume().then(() => { audioUnlocked = true; }).catch(() => {});
}

document.addEventListener('pointerdown', unlockAudio, {once: true});
document.addEventListener('keydown', unlockAudio, {once: true});
```

`playNewStoryAlarm()` must no-op while locked or muted.

- [ ] **Step 5: Poll and auto-localize pending stories in bounded batches**

Every 5 seconds, fetch `/api/live-feed`; for returned items with `needs_localization`, POST up to the API batch limit. Do not block rendering or publication actions while localization runs.

Pseudo-implementation to use literally as the control flow:

```javascript
async function refreshLiveFeed() {
  const payload = await V4.requestJSON('/api/live-feed');
  const items = Array.isArray(payload.items) ? payload.items : [];
  const freshIds = absorbIds(items);
  if (freshIds.length) playNewStoryAlarm();
  renderOrPatchLiveCards(items);
  const pending = items.filter(item => item.needs_localization).map(item => item.id).filter(Boolean).slice(0, 12);
  if (pending.length) {
    await V4.requestJSON('/api/live-feed/localize', {
      method: 'POST',
      body: JSON.stringify({ids: pending}),
      headers: {'Content-Type': 'application/json'},
    });
  }
}
```

If `V4.requestJSON` already injects JSON headers, follow its existing contract instead of duplicating headers.

- [ ] **Step 6: Respect mute state**

Read the existing persisted panel mute setting if exposed in the page/settings state. If the current settings code does not expose it, add a single dashboard-level localStorage key `bikhabar-news-alarm-muted` and keep it isolated; do not introduce a second general settings system.

- [ ] **Step 7: Bump service-worker cache key**

Change:

```javascript
const CACHE = 'bikhabar-newsroom-v4-1-2';
```

so the browser cannot keep the old dashboard script.

- [ ] **Step 8: Run syntax and regression tests**

```bash
node --check panel/static/newsroom-v4-dashboard.js
node --check panel/static/sw.js
python -m pytest -q tests/test_panel_v41_live_operator_flow.py
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add panel/static/newsroom-v4-dashboard.js panel/static/sw.js tests/test_panel_v41_live_operator_flow.py
git commit -m "feat: add live dashboard polling and new-story alarm"
```

---

### Task 4: Introduce the Capability Registry and Frozen Mutation Proposals

**Files:**
- Create: `panel/luna_capabilities.py`
- Create: `panel/luna_proposals.py`
- Create: `tests/test_luna_capabilities.py`
- Create: `tests/test_luna_proposals.py`

**Interfaces:**
- Produces: `Capability`
- Produces: `CapabilityRegistry`
- Produces: `build_proposal(...) -> dict`
- Produces: `proposal_is_expired(record) -> bool`
- Produces: `target_fingerprint(value) -> str`
- Produces: `execute_frozen_proposal(...) -> dict`

- [ ] **Step 1: Write failing registry tests**

```python
def test_registry_is_single_source_of_truth_for_tool_schema_and_confirmation():
    registry = CapabilityRegistry([
        Capability(
            name="inspect_panel_state",
            domain="diagnostics",
            description_fa="وضعیت پنل را بخوان",
            parameters={"type": "object", "properties": {}, "additionalProperties": False},
            mutates=False,
            requires_confirmation=False,
            executor="toolbox",
        ),
        Capability(
            name="reject_story",
            domain="stories",
            description_fa="یک خبر را رد کن",
            parameters={"type": "object", "properties": {"story_id": {"type": "string"}}, "required": ["story_id"], "additionalProperties": False},
            mutates=True,
            requires_confirmation=True,
            executor="story",
        ),
    ])

    assert registry.get("inspect_panel_state").mutates is False
    assert registry.get("reject_story").requires_confirmation is True
    assert {tool["name"] for tool in registry.tool_schemas()} == {"inspect_panel_state", "reject_story"}
```

- [ ] **Step 2: Write failing frozen-proposal tests**

```python
def test_confirmation_executes_frozen_payload_not_new_text():
    proposal = build_proposal(
        capability="rename_source",
        target={"type": "source", "id": "clash"},
        payload={"source_id": "clash", "display_name": "کلش ریپورتز"},
        summary_fa="نام منبع تغییر کند؟",
        before={"display_name": "ClashReports"},
        after={"display_name": "کلش ریپورتز"},
        target_version="v1",
    )
    assert proposal["payload"]["display_name"] == "کلش ریپورتز"
```

Add expiry and stale-target tests:

```python
def test_stale_proposal_fails_closed():
    result = execute_frozen_proposal(
        proposal=_proposal(target_version="old"),
        current_version=lambda _target: "new",
        executor=lambda *_a, **_k: {"ok": True},
    )
    assert result["ok"] is False
    assert result["error"] == "stale_proposal"
```

- [ ] **Step 3: Run and verify RED**

```bash
python -m pytest -q tests/test_luna_capabilities.py tests/test_luna_proposals.py
```

Expected: import failures because new modules do not exist.

- [ ] **Step 4: Implement `Capability` and `CapabilityRegistry`**

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class Capability:
    name: str
    domain: str
    description_fa: str
    parameters: dict
    mutates: bool
    requires_confirmation: bool
    executor: str

    def tool_schema(self) -> dict:
        return {
            "type": "function",
            "name": self.name,
            "description": self.description_fa,
            "parameters": self.parameters,
        }


class CapabilityRegistry:
    def __init__(self, capabilities):
        self._by_name = {item.name: item for item in capabilities}

    def get(self, name: str) -> Capability:
        return self._by_name[name]

    def tool_schemas(self) -> list[dict]:
        return [item.tool_schema() for item in self._by_name.values()]
```

Reject duplicate names during construction.

- [ ] **Step 5: Implement proposal creation, expiry, fingerprint, and frozen execution**

Proposal records must include:

```python
{
    "id": uuid4().hex,
    "capability": capability,
    "target": target,
    "payload": payload,
    "summary_fa": summary_fa,
    "before": before,
    "after": after,
    "target_version": target_version,
    "status": "pending",
    "created_at": now_iso,
    "expires_at": expires_iso,
}
```

Use a deterministic SHA-256 JSON fingerprint for versioning where the repository has no native row version.

- [ ] **Step 6: Add safe audit helper to proposal service**

Audit records must include capability, target, action ID, confirmation requirement, outcome, summary, and safe result metadata. Explicitly drop keys matching `token`, `secret`, `authorization`, `api_key`, and raw provider payloads.

- [ ] **Step 7: Run focused tests**

```bash
python -m pytest -q tests/test_luna_capabilities.py tests/test_luna_proposals.py
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add panel/luna_capabilities.py panel/luna_proposals.py tests/test_luna_capabilities.py tests/test_luna_proposals.py
git commit -m "feat: add Luna capability registry and frozen proposals"
```

---

### Task 5: Add Concrete Context Resolution for Stories and Sources

**Files:**
- Create: `panel/luna_context.py`
- Modify: `panel/luna_conversation.py`
- Create: `tests/test_luna_context.py`

**Interfaces:**
- Produces: `Resolution(ok: bool, entity_type: str, entity_id: str, matches: list[dict], error: str)`
- Produces: `resolve_source(...)`
- Produces: `resolve_story(...)`
- Produces structured context keys: `last_story_id`, `last_source_id`, `last_action_id`, `last_builder_pr`

- [ ] **Step 1: Write failing exact, context, and ambiguity tests**

```python
def test_source_exact_name_resolves_to_one_id():
    result = resolve_source(_sources(), query="ClashReports")
    assert result.ok is True
    assert result.entity_id == "clashreports"
```

```python
def test_ambiguous_source_does_not_choose_for_user():
    result = resolve_source([
        {"id": "a", "name": "Clash Reports"},
        {"id": "b", "name": "ClashReports"},
    ], query="clash reports")
    assert result.ok is False
    assert result.error == "ambiguous_source"
    assert len(result.matches) == 2
```

```python
def test_this_story_uses_last_structured_story_id():
    result = resolve_story(_stories(), query="این خبر", context={"last_story_id": "story-7"})
    assert result.entity_id == "story-7"
```

- [ ] **Step 2: Run and verify RED**

```bash
python -m pytest -q tests/test_luna_context.py
```

Expected: module missing.

- [ ] **Step 3: Implement normalized exact matching before fuzzy matching**

Normalize with Unicode casefold, whitespace collapse, punctuation trimming, and leading `@` removal for handles. Resolution order must be:

```text
explicit ID → exact normalized identity/name → structured recent context → bounded search → ambiguous/not found
```

Do not silently choose among multiple matches.

- [ ] **Step 4: Extend conversation storage with bounded metadata**

Add methods such as:

```python
def get_context(self, conversation_id: str) -> dict: ...
def update_context(self, conversation_id: str, **values) -> dict: ...
```

Only allow the four approved context keys; cap textual history as it is today.

- [ ] **Step 5: Run focused tests**

```bash
python -m pytest -q tests/test_luna_context.py
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add panel/luna_context.py panel/luna_conversation.py tests/test_luna_context.py
git commit -m "feat: add Luna entity context resolver"
```

---

### Task 6: Migrate Story Capabilities to Registry and Remove Blocking Semantics

**Files:**
- Modify: `panel/luna_capabilities.py`
- Modify: `panel/luna_tools.py`
- Modify: `panel/luna_tool_runtime.py`
- Modify: `panel/luna_story_actions.py`
- Test: `tests/test_luna_story_actions.py`
- Test: existing Luna tool/runtime tests

**Interfaces:**
- Registry capabilities: `search_stories`, `get_story`, `translate_story`, `move_story_to_review`, `reject_story`, `publish_machine_copy`, `publish_luna_copy`, `list_recent_published`, `diagnose_newsroom`

- [ ] **Step 1: Write failing registry contract tests for story tools**

```python
def test_story_registry_has_reject_but_no_block_tool():
    names = {tool["name"] for tool in control_center_registry().tool_schemas()}
    assert "reject_story" in names
    assert "reject_and_block_story" not in names
```

```python
def test_reject_story_future_source_items_are_not_suppressed():
    data = MemoryData([...])
    result = execute_story_action(data, "reject_story", {"story_id": "story-1"}, confirmed=True)
    assert result["ok"] is True
    assert data.mapping.get("data/operator_blocks.json", []) in ([], None)
```

- [ ] **Step 2: Run and verify RED**

```bash
python -m pytest -q tests/test_luna_story_actions.py tests/test_luna_capabilities.py -k 'story or reject or block'
```

- [ ] **Step 3: Register story capabilities centrally**

Each mutation capability must set `mutates=True, requires_confirmation=True`. Read-only capabilities stay immediate. Translation that persists a Luna copy is a mutation and therefore must produce a proposal before saving when invoked through natural-language Control Center; the existing explicit dashboard “ترجمه با Luna” button may retain its direct operator-click semantics because the click itself is the explicit requested action, but must not silently publish.

- [ ] **Step 4: Route publish modes through `luna_tool_runtime.py`**

Map:

```python
if name == "publish_machine_copy":
    return publish_story(..., copy_mode="machine", confirmed=confirmed)
if name == "publish_luna_copy":
    return publish_story(..., copy_mode="luna", confirmed=confirmed)
if name == "reject_story":
    return reject_story(..., confirmed=confirmed)
```

- [ ] **Step 5: Remove blocking tool from model-visible schemas and system prompt**

Do not delete legacy block infrastructure if unrelated older systems still use it; only stop Luna/dashboard reject flow from invoking it.

- [ ] **Step 6: Run story and full Luna tool regressions**

```bash
python -m pytest -q tests/test_luna_story_actions.py tests/test_luna_capabilities.py -k 'story or reject or publish'
python -m pytest -q -k 'luna_tool or luna_publish or operator_block'
```

Expected: all intended legacy block tests remain valid for legacy paths, while new Luna reject tests prove no block creation.

- [ ] **Step 7: Commit**

```bash
git add panel/luna_capabilities.py panel/luna_tools.py panel/luna_tool_runtime.py panel/luna_story_actions.py tests/test_luna_story_actions.py tests/test_luna_capabilities.py
git commit -m "feat: migrate Luna story controls to capability registry"
```

---

### Task 7: Add Source Rename, State, and Review-Only Capabilities

**Files:**
- Create: `panel/luna_source_actions.py`
- Modify: `panel/source_manager.py`
- Modify: `panel/luna_capabilities.py`
- Modify: `panel/luna_tool_runtime.py`
- Create: `tests/test_luna_source_actions.py`
- Extend: existing source-manager tests

**Interfaces:**
- Capabilities: `list_sources`, `inspect_source`, `add_source`, `rename_source`, `enable_source`, `disable_source`, `delete_source`, `set_source_review_only`, `inspect_source_health`
- System-source override fields: `display_name`, `active`, `hidden`, `review_only`
- Custom-source fields: `name`/`display_name`, `active`, `deleted`, `review_only`

- [ ] **Step 1: Write failing ClashReports rename test**

```python
def test_rename_system_source_persists_display_name_override_after_confirmation():
    data = MemoryData({"data/source_overrides.json": {}})
    result = rename_source(
        data,
        source={"id": "clashreports", "system": True, "name": "ClashReports"},
        display_name="کلش ریپورتز",
        confirmed=True,
    )
    assert result["ok"] is True
    assert data.mapping["data/source_overrides.json"]["clashreports"]["display_name"] == "کلش ریپورتز"
```

- [ ] **Step 2: Write failing review-only and custom-source tests**

```python
def test_set_source_review_only_preserves_other_override_fields():
    data = MemoryData({"data/source_overrides.json": {"clashreports": {"active": True}}})
    result = set_source_review_only(data, "clashreports", True, confirmed=True)
    state = data.mapping["data/source_overrides.json"]["clashreports"]
    assert state == {"active": True, "review_only": True}
```

- [ ] **Step 3: Run and verify RED**

```bash
python -m pytest -q tests/test_luna_source_actions.py
```

- [ ] **Step 4: Implement storage adapters for system and custom sources**

For system sources, merge into `source_overrides.json` without replacing unrelated keys. For custom sources, update only the matched record in `custom_sources.json` with optimistic-retry writes.

- [ ] **Step 5: Make `source_manager.py` render display-name overrides**

When building system rows:

```python
row_name = str(override.get("display_name") or _source_name(source)).strip()
```

Expose `review_only` in the row so the UI and ingestion policy can use the same truth.

- [ ] **Step 6: Connect review-only routing at the existing ingestion decision point**

Find the code that converts source items into Ready/review decisions and add one narrow check:

```python
if source_policy.review_only:
    panel_status = "needs_review"
```

Do not create a second ingest pipeline. Add a focused test around the existing decision function proving only that source is routed to review.

- [ ] **Step 7: Register source capabilities and route through runtime**

Every source mutation returns a preview/proposal when `confirmed=False`; read-only list/inspect/health returns immediately.

- [ ] **Step 8: Run focused and source-manager regressions**

```bash
python -m pytest -q tests/test_luna_source_actions.py -k 'rename or review_only or enable or disable'
python -m pytest -q -k 'source_manager or custom_source or managed_source'
```

- [ ] **Step 9: Commit**

```bash
git add panel/luna_source_actions.py panel/source_manager.py panel/luna_capabilities.py panel/luna_tool_runtime.py tests/test_luna_source_actions.py
git commit -m "feat: add confirmed Luna source controls"
```

---

### Task 8: Integrate Unified Proposal/Confirmation Flow into Luna Operator Chat

**Files:**
- Modify: `panel/luna_operator_api.py`
- Modify: `panel/luna_tool_runtime.py`
- Modify: `panel/luna_capabilities.py`
- Modify: `panel/luna_proposals.py`
- Modify: `panel/luna_context.py`
- Create: `tests/test_luna_operator_control_center.py`

**Interfaces:**
- `POST /api/panel/luna/operator-chat`
- `POST /api/panel/luna/operator-confirm/<action_id>`
- Registry-generated function tools
- Proposal records in `data/panel_pending_actions.json`
- Audit records in `data/panel_audit_log.json`

- [ ] **Step 1: Write failing read-only vs mutation integration tests**

Use a fake provider that emits function calls deterministically:

```python
def test_read_only_tool_executes_without_confirmation(client, fake_provider):
    fake_provider.queue_function_call("inspect_panel_state", {})
    response = client.post("/api/panel/luna/operator-chat", json={"message": "وضعیت پنل چطوره؟"})
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["confirmation_required"] is False
```

```python
def test_rename_source_requires_confirmation_and_freezes_payload(client, fake_provider):
    fake_provider.queue_function_call("rename_source", {"query": "ClashReports", "display_name": "کلش ریپورتز"})
    proposal = client.post("/api/panel/luna/operator-chat", json={"message": "ClashReports رو فارسی کن"}).get_json()
    assert proposal["confirmation_required"] is True
    action_id = proposal["action_id"]

    confirmed = client.post(f"/api/panel/luna/operator-confirm/{action_id}").get_json()
    assert confirmed["ok"] is True
```

- [ ] **Step 2: Add a regression test for stateless 1xAI continuation**

The fake provider should assert the second model call contains the previous response `output` plus `function_call_output` in `input_items` and does **not** rely on `previous_response_id`.

- [ ] **Step 3: Run and verify RED**

```bash
python -m pytest -q tests/test_luna_operator_control_center.py
```

- [ ] **Step 4: Replace hand-maintained tool lists with registry schemas**

In operator chat:

```python
registry = control_center_registry()
tools = registry.tool_schemas() + builder_tool_schemas()
```

Resolve concrete target IDs before creating mutation proposals where the capability needs a story/source target.

- [ ] **Step 5: Use one proposal service for all mutations**

When a capability returns a mutation intent:

```python
proposal = proposal_store.create(
    capability=capability.name,
    target=resolved_target,
    payload=validated_args,
    summary_fa=summary,
    before=before,
    after=after,
    target_version=fingerprint,
)
```

Return `action_id`, `summary_fa`, and `confirmation_required=True`. Do not execute mutation in the same request.

- [ ] **Step 6: Confirmation loads and executes the frozen proposal**

`operator-confirm/<action_id>` must:

1. load pending proposal by ID,
2. reject expired proposal,
3. verify target fingerprint/version,
4. call the registry-selected executor with frozen payload and `confirmed=True`,
5. write audit outcome,
6. mark proposal complete/failed,
7. return actual executor result.

- [ ] **Step 7: Update structured conversation context after successful resolution/action**

Store concrete `last_story_id`, `last_source_id`, `last_action_id`, `last_builder_pr` so later phrases like «این خبر» resolve without model guesswork.

- [ ] **Step 8: Update system prompt to reflect reject-only and registry policy**

Prompt must say mutations require confirmation, but policy enforcement must live in code/registry; prompt text is not the security boundary.

- [ ] **Step 9: Run focused tests**

```bash
python -m pytest -q tests/test_luna_operator_control_center.py tests/test_luna_proposals.py tests/test_luna_context.py
```

Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add panel/luna_operator_api.py panel/luna_tool_runtime.py panel/luna_capabilities.py panel/luna_proposals.py panel/luna_context.py tests/test_luna_operator_control_center.py
git commit -m "feat: unify Luna confirmation and context flow"
```

---

### Task 9: Adapt Builder to the Same Confirmed Control-Center Contract

**Files:**
- Modify: `panel/luna_builder.py`
- Modify: `panel/luna_builder_tools.py`
- Modify: `panel/luna_operator_api.py`
- Modify: `panel/luna_capabilities.py`
- Modify: `panel/github_builder_release.py` only if needed to expose current target SHA cleanly
- Test: existing Builder tests
- Extend: `tests/test_luna_operator_control_center.py`

**Interfaces:**
- Capability: `builder_prepare_change`
- Capability: `builder_ci_status` (read-only)
- Capability: `builder_prepare_merge` (mutation, confirmed)

- [ ] **Step 1: Write failing Builder confirmation tests**

```python
def test_builder_change_requires_confirmation_before_branch_or_pr(client, fake_builder):
    response = client.post("/api/panel/luna/operator-chat", json={"message": "این دکمه رو ببر سمت راست"})
    payload = response.get_json()
    assert payload["confirmation_required"] is True
    assert fake_builder.created_branches == []
```

```python
def test_builder_merge_requires_green_ci_and_confirmation(fake_release):
    fake_release.status_result = {"ok": True, "ci_green": False, "head_sha": "abc"}
    result = execute_builder_capability("builder_prepare_merge", {"pr_number": 12}, confirmed=True)
    assert result["ok"] is False
    assert result["error"] == "builder_ci_not_green"
```

- [ ] **Step 2: Run and verify RED where contract differs**

```bash
python -m pytest -q -k 'builder and luna'
```

- [ ] **Step 3: Register Builder capabilities without granting generic GitHub/shell access**

Builder request remains narrow: user-request text → confirmed Builder branch/PR preparation. `builder_ci_status` is read-only. Merge uses the frozen `pr_number` and expected head SHA from proposal.

- [ ] **Step 4: Preserve existing CI gate and promotion flow**

No new deploy endpoint. The implementation ends at controlled merge; existing main CI promotion remains authoritative.

- [ ] **Step 5: Run Builder regressions**

```bash
python -m pytest -q -k 'builder or github_builder'
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add panel/luna_builder.py panel/luna_builder_tools.py panel/luna_operator_api.py panel/luna_capabilities.py panel/github_builder_release.py tests/test_luna_operator_control_center.py
git commit -m "feat: align Builder with Luna confirmation registry"
```

---

### Task 10: Full Regression, PR Supersession, and Production Smoke Tests

**Files:**
- No product-code changes unless a regression fix is required and separately tested.
- Update docs only if final behavior differs from the approved spec.

**Interfaces:**
- CI workflows: `Pull Request Check`, `Telegram News Agent CI`
- Production deployment: existing main → production promotion and VPS deploy service

- [ ] **Step 1: Run static checks**

```bash
node --check panel/static/newsroom-v4-dashboard.js
node --check panel/static/luna-assistant.js
node --check panel/static/sw.js
```

Expected: no output, exit 0.

- [ ] **Step 2: Run focused control-center suite**

```bash
python -m pytest -q \
  tests/test_panel_v41_live_operator_flow.py \
  tests/test_luna_capabilities.py \
  tests/test_luna_proposals.py \
  tests/test_luna_context.py \
  tests/test_luna_story_actions.py \
  tests/test_luna_source_actions.py \
  tests/test_luna_operator_control_center.py
```

Expected: PASS.

- [ ] **Step 3: Run full regression suite**

```bash
python -m pytest -q
```

Expected: all tests pass; known intentional skips are acceptable only if unchanged from baseline.

- [ ] **Step 4: Open implementation PR and wait for both CI workflows**

The PR description must list:

- persistent machine Persian translation,
- direct vs Luna publish,
- reject-only behavior,
- one-shot alarm,
- published-card removal after confirmed success,
- Capability Registry,
- frozen proposals,
- source rename/review-only,
- Builder confirmation integration,
- explicit statement that no arbitrary shell/direct production access was added.

- [ ] **Step 5: Close superseded PR #161 after equivalent tests are present and green**

Comment that its bounded hotfix was superseded by the approved Luna Control Center implementation and that no blocking semantics were carried forward.

- [ ] **Step 6: Merge only after both PR workflows are green**

Use the repository's normal squash-merge flow. Verify main CI promotes the exact tested main SHA to `production`.

- [ ] **Step 7: Deploy production using the existing updater**

On VPS, use the existing deploy service rather than editing files directly:

```bash
sudo systemctl start bikhabar-deploy.service
```

Then verify:

```bash
echo "HEAD=$(git -C /opt/bikhabar/app rev-parse HEAD)" && echo "PANEL=$(systemctl is-active bikhabar-panel.service)"
```

Expected: HEAD equals promoted production SHA and `PANEL=active`.

- [ ] **Step 8: Live-smoke the dashboard in this order**

1. Hard refresh once so the bumped service-worker cache loads.
2. Confirm existing cards do not trigger an alarm on initial load.
3. Wait for a genuinely new story; after first browser interaction, confirm one short alarm plays once.
4. Confirm non-Persian story receives machine Persian copy and English is not primary card text.
5. Publish one fluent machine translation with «انتشار مستقیم»; confirm Telegram succeeds and card disappears only after success.
6. Translate a second story with Luna and publish with «انتشار با Luna»; confirm final Luna copy is used.
7. Reject one story with «رد»; confirm card leaves active flow and no future story from that source is blocked.
8. Tell Luna: «ClashReports رو فارسی بنویس و اصلاح کن»; confirm Luna proposes the exact rename, waits for approval, applies it, and reports verified success.
9. Tell Luna a read-only request such as «وضعیت اتاق خبر رو بررسی کن»; confirm no approval prompt appears.
10. Tell Luna a UI request such as «این دکمه رو ببر سمت راست»; confirm Builder proposal appears and no production edit occurs before approval/CI.

- [ ] **Step 9: Verify audit records contain outcomes but no secrets**

Inspect the panel audit view/data through the existing application-safe path and confirm action IDs, targets, outcomes, and summaries are present while API keys/auth headers are absent.

- [ ] **Step 10: Final completion commit only if documentation needed**

If smoke testing reveals no spec/documentation changes, do not create a meaningless commit. If operator-facing docs changed, commit only those exact docs with:

```bash
git commit -m "docs: finalize Luna Control Center rollout"
```

---

## Self-Review

### Spec coverage

- Natural Persian control surface: Tasks 5–9.
- Read-only immediate vs mutation confirmation: Tasks 4 and 8.
- Frozen payload confirmation: Tasks 4 and 8.
- Source rename example (`ClashReports` → `کلش ریپورتز`): Task 7 and Task 10 smoke test.
- Machine and Luna publish modes through `v3_publish`: Task 2 and Task 6.
- Reject-only, no permanent block: Tasks 2 and 6.
- Source enable/disable/delete/review-only: Task 7.
- Diagnostics and context resolution: Tasks 5, 6, and 8.
- Builder branch/PR/CI/merge-confirmation: Task 9.
- Persistent machine translation: Task 1.
- One-shot new-story alarm: Task 3.
- Remove cards only after confirmed publication: Task 2.
- Audit and no false success: Tasks 4 and 8.
- No arbitrary shell/direct production access: Global Constraints and Task 9.
- Incremental migration/no rewrite: task ordering preserves working V4.1 paths.

### Placeholder scan

The plan contains no `TBD`, no implementation `TODO`, no “implement later”, and no unspecified “add error handling” steps. All error cases named in Review Focus map to explicit tests/tasks.

### Type/interface consistency

- Registry names are stable across Tasks 4, 6, 7, 8, and 9.
- `copy_mode` values are exactly `machine` and `luna` throughout.
- Reject capability is exactly `reject_story`; `reject_and_block_story` is explicitly excluded.
- Proposal execution always uses frozen `payload` and target version/fingerprint.
- Builder merge uses frozen `pr_number` plus expected head SHA.

### Review Focus coverage

- Translation failure: Task 1.
- Ambiguous source names: Task 5.
- Stale proposal: Task 4.
- Publish failure leaves card visible: Task 2.
- Audio locked before interaction: Task 3.
