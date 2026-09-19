# Luna Control Center Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Luna the confirmed natural-language control surface for Bikhabar while fixing the live dashboard workflow: persistent machine Persian for every incoming story, direct-vs-Luna publishing, a one-shot new-story alarm, and removal of a card only after confirmed publication success.

**Architecture:** Keep the existing V4.1 Flask operator endpoint, `v3_publish` queue, Luna translation pipeline, source manager, GitHub Builder, and 1xAI-compatible stateless Responses flow. Add one capability registry, one frozen mutation-proposal format, one structured entity resolver, and one control runtime. Dashboard mechanics that do not need language reasoning stay model-independent for speed.

**Tech Stack:** Python 3.12, Flask 3.1, pytest, vanilla JavaScript, existing editorial JSON repository, existing newsroom V3 command queue, GitHub Builder/CI, existing `src.services.translate_to_fa` network translation pipeline.

**Spec:** `docs/superpowers/specs/2026-09-19-luna-control-center-design.md`

## Global Constraints

- Read-only Luna actions execute without confirmation.
- Every mutation requires explicit operator confirmation immediately before execution.
- Confirmation executes the exact frozen proposal payload; the original sentence is not interpreted again.
- Ambiguous story/source targets never mutate; Luna asks one short clarification question.
- Publishing always uses the existing `v3_publish` queue; Luna never sends directly to Telegram.
- Code/UI changes always use Builder branch → tests → Draft PR → CI → merge confirmation → merge → existing production promotion.
- Luna never reports success unless the executor returned `ok=true` or the command poll returned terminal publication success.
- No arbitrary shell, SQL, filesystem, environment-variable, secret, generic HTTP proxy, or direct production-edit capability is exposed.
- Incoming non-Persian stories get persisted machine Persian copy before they become directly publishable.
- The dashboard shows machine Persian as the primary copy and preserves original-language access via the source/original link.
- The dashboard has separate `انتشار مستقیم` and `ترجمه با Luna`/Luna-publish paths.
- A new-story alarm never fires for initial page contents and never repeats for the same detected arrival.
- A publish click alone never removes a card; removal happens only after the existing command poll returns `succeeded` or `reconciled`.
- Simple Luna reads target 3–5 seconds under normal provider/network conditions.

## Review Focus

- Two sources with similar names: resolver returns ambiguity and creates no proposal.
- Expired proposal or changed target: confirmation fails closed and requests a fresh proposal.
- Translation backend failure: English source text does not become a directly publishable card.
- Queued/failed publish: card stays visible; successful/reconciled publish: card is removed.
- Browser autoplay restriction: no error loop and no repeated ding; audio becomes available only after operator interaction.

---

## File Structure

### New files

- `panel/luna_capabilities.py` — capability metadata and provider tool-schema generation.
- `panel/luna_proposals.py` — frozen mutation proposals, expiry, fingerprint, completion.
- `panel/luna_context.py` — source/story resolution and structured conversation references.
- `panel/luna_control_runtime.py` — one dispatcher for read, propose, confirm, execute, and audit.
- `tests/test_luna_capability_registry.py` — registry policy tests.
- `tests/test_luna_control_center.py` — resolver, proposal, source/story, diagnostics, Builder tests.
- `tests/test_panel_v41_live_operator_flow.py` — dashboard workflow regressions.

### Modified files

- `panel/live_api.py`
- `panel/wsgi.py`
- `panel/luna_publish.py`
- `panel/luna_translation_api.py`
- `panel/luna_tools.py`
- `panel/luna_tool_runtime.py`
- `panel/luna_operator_api.py`
- `panel/luna_conversation.py`
- `panel/static/newsroom-v4-dashboard.js`
- `panel/static/luna-assistant.js`
- `panel/templates/dashboard.html`
- `panel/static/sw.js`
- existing Luna/Builder/source tests as required by changed contracts.

---

### Task 1: Persist Publishable Machine Persian for Live Stories

**Files:**
- Create: `tests/test_panel_v41_live_operator_flow.py` if it is not already present on the implementation branch.
- Modify: `panel/live_api.py`
- Verify: `panel/wsgi.py`

**Interfaces:**
- Consumes: `current_app.config["LIVE_FEED_TRANSLATOR"]`, editorial repository `read_json/write_json`.
- Produces: `_persist_machine_translation(row_id: str, title_fa: str, body_fa: str) -> dict | None`; saved `persian_title`, `persian_body`, `machine_translation_status="passed"`.

- [ ] **Step 1: Write the failing persistence test**

```python
def test_machine_localization_persists_persian_copy_for_dashboard_and_publish():
    data = MemoryData()
    app = _client_app(data)
    app.config["LIVE_FEED_TRANSLATOR"] = lambda text: {
        "Breaking update": "خبر فوری تازه",
        "Body text": "متن فارسی تازه",
    }.get(text, "")

    client = app.test_client()
    with client.session_transaction() as sess:
        sess["admin"] = True
    response = client.post("/api/live-feed/localize", json={"ids": ["story-1"]})

    assert response.status_code == 200
    assert response.get_json()["items"][0]["title"] == "خبر فوری تازه"
    saved = data.mapping["data/panel_live_feed.json"][0]
    assert saved["persian_title"] == "خبر فوری تازه"
    assert saved["persian_body"] == "متن فارسی تازه"
    assert saved["machine_translation_status"] == "passed"
```

- [ ] **Step 2: Write the fail-closed test**

```python
def test_failed_machine_translation_keeps_story_pending_and_not_publishable():
    data = MemoryData()
    app = _client_app(data)
    app.config["LIVE_FEED_TRANSLATOR"] = lambda _text: ""
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["admin"] = True

    assert client.post("/api/live-feed/localize", json={"ids": ["story-1"]}).status_code == 200
    item = client.get("/api/live-feed").get_json()["items"][0]
    assert item["needs_localization"] is True
    assert item["can_publish"] is False
```

- [ ] **Step 3: Run RED**

```bash
python -m pytest -q tests/test_panel_v41_live_operator_flow.py -k "machine_localization or failed_machine_translation"
```

Expected: at least one failure because the current live API uses a panel-only in-memory offline cache and does not persist publishable machine copy.

- [ ] **Step 4: Implement the persistence helper**

```python
def _persist_machine_translation(row_id: str, title_fa: str, body_fa: str) -> dict | None:
    data = current_app.extensions["editorial_data"]
    for attempt in range(3):
        value, sha = data.read_json("data/panel_live_feed.json", [])
        rows = [dict(row) for row in value if isinstance(row, dict)] if isinstance(value, list) else []
        saved = None
        for row in rows:
            if _row_id(row) != row_id:
                continue
            row["persian_title"] = title_fa
            row["persian_body"] = body_fa
            row["machine_translation_status"] = "passed"
            row["machine_translation_mode"] = "network"
            row["machine_translated_at"] = datetime.now(timezone.utc).isoformat()
            saved = dict(row)
            break
        if saved is None:
            return None
        try:
            data.write_json(
                "data/panel_live_feed.json",
                rows,
                sha,
                "panel v4.1: persist machine Persian copy",
            )
            return saved
        except requests.HTTPError as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if attempt < 2 and status in {409, 422}:
                continue
            raise
    return None
```

- [ ] **Step 5: Make `/api/live-feed/localize` use the injected network translator and persist**

Resolve translator exactly once:

```python
translator = current_app.config.get("LIVE_FEED_TRANSLATOR")
if not callable(translator):
    return jsonify({"ok": False, "error": "translator_unavailable"}), 503
```

For each requested row, translate raw title/body, require Persian output using `_has_persian`, call `_persist_machine_translation`, then return `_public_row(saved, queued_ids)`. Remove the in-memory cache as the authoritative publishable copy; retaining a cache only as a non-authoritative optimization is acceptable.

Set `can_publish` from presence of valid persisted/final Persian rather than merely having an ID.

- [ ] **Step 6: Verify WSGI still wires the existing network translator**

`panel/wsgi.py` must retain:

```python
from src.services import translate_to_fa
config["LIVE_FEED_TRANSLATOR"] = translate_to_fa
```

- [ ] **Step 7: Run GREEN**

```bash
python -m pytest -q tests/test_panel_v41_live_operator_flow.py tests/test_panel_live_feed.py
```

- [ ] **Step 8: Commit**

```bash
git add panel/live_api.py panel/wsgi.py tests/test_panel_v41_live_operator_flow.py
git commit -m "fix: persist machine Persian live copy"
```

---

### Task 2: Direct Machine Publish and Luna Publish Are Explicitly Separate

**Files:**
- Modify: `panel/luna_publish.py`
- Modify: `panel/luna_translation_api.py`
- Modify: `panel/templates/dashboard.html`
- Modify: `panel/static/newsroom-v4-dashboard.js`
- Test: `tests/test_panel_v41_live_operator_flow.py`

**Interfaces:**
- Produces: `publish_story(..., copy_mode: str = "machine") -> dict`.
- Machine source: persisted `persian_title/persian_body`.
- Luna source: `final_persian_title/final_persian_body` only when `luna_translation_status == "passed"`.

- [ ] **Step 1: Write machine-vs-Luna selection tests**

```python
def test_publish_machine_uses_machine_copy_even_if_luna_copy_exists():
    data = MemoryData.with_story(
        persian_title="ترجمه ماشینی",
        persian_body="متن ماشینی",
        final_persian_title="نسخه لونا",
        final_persian_body="متن لونا",
        luna_translation_status="passed",
    )
    captured = {}
    result = publish_story(
        data,
        "story-1",
        enqueue=lambda command, **kw: captured.update(command=command, **kw) or "cmd-1",
        confirmed=True,
        copy_mode="machine",
    )
    assert result["ok"] is True
    assert captured["command"] == "v3_publish"
    assert captured["title"] == "ترجمه ماشینی"


def test_publish_luna_requires_passed_luna_copy():
    data = MemoryData.with_story(persian_title="ترجمه ماشینی", luna_translation_status="pending")
    result = publish_story(data, "story-1", enqueue=lambda *_a, **_k: "x", confirmed=True, copy_mode="luna")
    assert result["ok"] is False
    assert result["error"] == "persian_copy_not_ready"
```

- [ ] **Step 2: Run RED**

```bash
python -m pytest -q tests/test_panel_v41_live_operator_flow.py -k "publish_machine or publish_luna"
```

- [ ] **Step 3: Implement explicit copy selection**

```python
def _persian_copy(row: dict, copy_mode: str) -> tuple[str, str]:
    if copy_mode == "machine":
        return str(row.get("persian_title") or "").strip(), str(row.get("persian_body") or "").strip()
    if copy_mode == "luna" and str(row.get("luna_translation_status") or "") == "passed":
        return str(row.get("final_persian_title") or "").strip(), str(row.get("final_persian_body") or "").strip()
    return "", ""


def publish_story(data, story_id: str, *, enqueue, confirmed: bool = False, copy_mode: str = "machine") -> dict:
    ...
```

The existing body remains authoritative for validation/source fields and must still enqueue only `v3_publish`.

- [ ] **Step 4: Add explicit dashboard endpoints**

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

- [ ] **Step 5: Render separate actions in the existing server-rendered card**

Replace the single publish action with:

```html
{% if item.persian_title %}
<button class="v4-button v4-button-primary" type="button" data-v4-action="publish-machine">انتشار مستقیم</button>
{% endif %}
<button class="v4-button v4-button-secondary" type="button" data-v4-action="translate-luna">{% if final_ready %}ترجمه دوباره{% else %}ترجمه با Luna{% endif %}</button>
{% if final_ready %}
<button class="v4-button v4-button-primary" type="button" data-v4-action="publish-luna">انتشار نسخه Luna</button>
{% endif %}
```

- [ ] **Step 6: Refactor existing `publishFinal` into one explicit function**

```javascript
async function publishStory(card, copyMode) {
  const id = card?.dataset.storyId;
  if (!id || card.classList.contains('is-busy')) return;
  const luna = copyMode === 'luna';
  const title = luna
    ? (card.querySelector('[data-v41-title]')?.textContent?.trim() || '')
    : (card.querySelector('[data-v41-publish-title]')?.textContent?.trim() || '');
  const body = luna
    ? (card.querySelector('[data-v41-body]')?.textContent?.trim() || '')
    : (card.querySelector('[data-v41-publish-body]')?.textContent?.trim() || '');
  const preview = [title, body].filter(Boolean).join('\n\n');
  const accepted = await V4.confirmAction({
    title: luna ? 'نسخه Luna منتشر شود؟' : 'همین ترجمه ماشینی منتشر شود؟',
    text: preview.length > 700 ? `${preview.slice(0, 700)}…` : preview,
    accept: 'تأیید و انتشار',
  });
  if (!accepted) return;
  card.classList.add('is-busy');
  try {
    const endpoint = luna ? 'publish-final' : 'publish-machine';
    const queued = await V4.requestJSON(`/api/panel/luna/${endpoint}/${encodeURIComponent(id)}`, {method: 'POST'});
    const done = await poll(queued.command_id, card);
    progress(card, done.telegram_message_id ? `منتشر شد · Message ID ${done.telegram_message_id}` : 'منتشر شد', 'success');
    card.remove();
    V4.toast('خبر منتشر شد.', 'success');
  } catch (error) {
    progress(card, error.message, 'error');
    V4.toast(error.message, 'error');
  } finally {
    card.classList.remove('is-busy');
  }
}
```

Wire actions:

```javascript
if (action === 'publish-machine') void publishStory(card, 'machine');
if (action === 'publish-luna') void publishStory(card, 'luna');
```

`card.remove()` is safe here because the existing `poll()` returns only after `succeeded` or `reconciled`; queued/processing/failure never reaches removal.

- [ ] **Step 7: Run GREEN**

```bash
node --check panel/static/newsroom-v4-dashboard.js
python -m pytest -q tests/test_panel_v41_live_operator_flow.py tests/test_panel_luna_publish_v41.py
```

- [ ] **Step 8: Commit**

```bash
git add panel/luna_publish.py panel/luna_translation_api.py panel/templates/dashboard.html panel/static/newsroom-v4-dashboard.js tests/test_panel_v41_live_operator_flow.py
git commit -m "feat: separate direct and Luna publishing"
```

---

### Task 3: Automatic Localization Polling and One-Shot New-Story Alarm

**Files:**
- Modify: `panel/static/newsroom-v4-dashboard.js`
- Modify: `panel/static/sw.js`
- Test: `tests/test_panel_v41_live_operator_flow.py`

**Interfaces:**
- Consumes: `/api/live-feed`, `/api/live-feed/localize`.
- Produces: automatic localization requests, first-load-safe arrival detection, one short audio ding, controlled page reload after a newly localized/new story so the existing Jinja renderer remains the single card renderer.

- [ ] **Step 1: Add the JS contract test**

```python
def test_dashboard_auto_localizes_polls_and_alarms_once():
    js = Path("panel/static/newsroom-v4-dashboard.js").read_text(encoding="utf-8")
    assert "/api/live-feed/localize" in js
    assert "knownStoryIds" in js
    assert "feedInitialized" in js
    assert "audioUnlocked" in js
    assert "playNewStoryAlarm" in js
    assert "setInterval(refreshLiveFeed, 5000)" in js
```

- [ ] **Step 2: Run RED**

```bash
python -m pytest -q tests/test_panel_v41_live_operator_flow.py -k "auto_localizes_polls"
```

- [ ] **Step 3: Add first-load-safe ID state and browser audio unlock**

```javascript
const knownStoryIds = new Set();
let feedInitialized = false;
let audioUnlocked = false;
let audioContext = null;
let refreshScheduled = false;

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

If the panel already exposes a mute preference, `playNewStoryAlarm()` must return immediately while muted; do not create a second competing mute store.

- [ ] **Step 4: Add a single guarded reload helper**

```javascript
function scheduleDashboardReload(delay = 350) {
  if (refreshScheduled) return;
  refreshScheduled = true;
  window.setTimeout(() => window.location.reload(), delay);
}
```

- [ ] **Step 5: Poll the API, seed initial IDs without sound, and localize pending rows**

```javascript
async function refreshLiveFeed() {
  try {
    const response = await fetch('/api/live-feed', { cache: 'no-store' });
    if (!response.ok) return;
    const payload = await response.json();
    const items = Array.isArray(payload.items) ? payload.items : [];
    const ids = items.map(item => String(item.id || item.item_id || '')).filter(Boolean);

    if (!feedInitialized) {
      ids.forEach(id => knownStoryIds.add(id));
      feedInitialized = true;
    } else {
      const fresh = ids.filter(id => !knownStoryIds.has(id));
      ids.forEach(id => knownStoryIds.add(id));
      if (fresh.length) {
        playNewStoryAlarm();
        scheduleDashboardReload();
        return;
      }
    }

    const pendingIds = items
      .filter(item => item.needs_localization)
      .map(item => String(item.id || ''))
      .filter(Boolean)
      .slice(0, 12);
    if (!pendingIds.length) return;

    const localizedResponse = await fetch('/api/live-feed/localize', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ids: pendingIds }),
    });
    if (!localizedResponse.ok) return;
    const localized = await localizedResponse.json();
    if (Array.isArray(localized.items) && localized.items.length) scheduleDashboardReload();
  } catch (_error) {
    // Live polling is best-effort; existing server-rendered controls remain usable.
  }
}

void refreshLiveFeed();
setInterval(refreshLiveFeed, 5000);
```

Because every reload starts with `feedInitialized=false`, currently visible stories seed silently and do not replay the alarm.

- [ ] **Step 6: Bump the service-worker cache**

```javascript
const CACHE = 'bikhabar-newsroom-v4-1-2';
```

- [ ] **Step 7: Run GREEN**

```bash
node --check panel/static/newsroom-v4-dashboard.js
python -m pytest -q tests/test_panel_v41_live_operator_flow.py
```

- [ ] **Step 8: Commit**

```bash
git add panel/static/newsroom-v4-dashboard.js panel/static/sw.js tests/test_panel_v41_live_operator_flow.py
git commit -m "feat: add live localization polling and alarm"
```

---

### Task 4: Central Capability Registry

**Files:**
- Create: `panel/luna_capabilities.py`
- Create: `tests/test_luna_capability_registry.py`
- Modify: `panel/luna_tools.py`

**Interfaces:**
- Produces: `Capability`, `CapabilityRegistry`, `build_capability_registry()`, `CapabilityRegistry.get(name)`, `CapabilityRegistry.tool_schemas()`, `CapabilityRegistry.all()`.

- [ ] **Step 1: Write policy tests**

```python
from panel.luna_capabilities import build_capability_registry


def test_registry_classifies_reads_and_mutations():
    registry = build_capability_registry()
    assert registry.get("search_stories").mutates is False
    assert registry.get("inspect_panel_state").requires_confirmation is False
    assert registry.get("rename_source").mutates is True
    assert registry.get("rename_source").requires_confirmation is True
    assert registry.get("publish_story").requires_confirmation is True


def test_registry_has_no_generic_dangerous_capability():
    names = {cap.name for cap in build_capability_registry().all()}
    forbidden = {"shell", "exec", "run_command", "sql", "set_env", "read_secret", "http_proxy"}
    assert not names.intersection(forbidden)
```

- [ ] **Step 2: Run RED**

```bash
python -m pytest -q tests/test_luna_capability_registry.py
```

- [ ] **Step 3: Implement immutable metadata**

```python
from dataclasses import dataclass


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
        return self._by_name[name]

    def all(self) -> list[Capability]:
        return list(self._by_name.values())

    def tool_schemas(self) -> list[dict]:
        return [cap.tool_schema() for cap in self.all()]
```

- [ ] **Step 4: Register the supported product capabilities**

At minimum register:

```text
search_stories, get_story, translate_story, publish_story,
reject_and_block_story, move_story_to_review, list_recent_published,
list_sources, add_source, rename_source, enable_source, disable_source,
delete_source, set_source_review_only, inspect_panel_state,
diagnose_newsroom, set_newsroom_alarm, builder_prepare,
builder_ci_status, builder_prepare_merge
```

Read-only: search/get/list/inspect/diagnose/builder CI status. All other entries above mutate and require confirmation.

- [ ] **Step 5: Make legacy schema exposure delegate to the registry**

```python
def tool_schemas() -> list[dict]:
    from .luna_capabilities import build_capability_registry
    return build_capability_registry().tool_schemas()
```

Preserve `LunaToolbox` execution methods until the control runtime takes over in Task 7.

- [ ] **Step 6: Run GREEN and commit**

```bash
python -m pytest -q tests/test_luna_capability_registry.py tests/test_panel_luna_operator_v41.py
git add panel/luna_capabilities.py panel/luna_tools.py tests/test_luna_capability_registry.py
git commit -m "refactor: centralize Luna capability policy"
```

---

### Task 5: Frozen Mutation Proposals

**Files:**
- Create: `panel/luna_proposals.py`
- Create: `tests/test_luna_control_center.py`

**Interfaces:**
- Produces: `proposal_fingerprint(value: dict) -> str`, `ProposalStore.create(...) -> dict`, `ProposalStore.get_pending(action_id: str) -> dict`, `ProposalStore.complete(action_id: str, status: str, result: dict) -> None`.

- [ ] **Step 1: Write frozen payload and expiry tests**

```python
def test_proposal_freezes_exact_payload():
    store = ProposalStore(data, ttl_minutes=15)
    proposal = store.create(
        capability="rename_source",
        target={"type": "source", "id": "src-1"},
        payload={"source_id": "src-1", "display_name": "کلش ریپورتز"},
        summary_fa="نام نمایشی تغییر کند؟",
        before={"display_name": "ClashReports"},
        after={"display_name": "کلش ریپورتز"},
        target_fingerprint="abc",
    )
    loaded = store.get_pending(proposal["id"])
    assert loaded["payload"] == {"source_id": "src-1", "display_name": "کلش ریپورتز"}


def test_expired_proposal_cannot_execute():
    store = ProposalStore(data, ttl_minutes=-1)
    proposal = store.create(
        capability="disable_source",
        target={"type": "source", "id": "src-1"},
        payload={"source_id": "src-1"},
        summary_fa="غیرفعال شود؟",
        before={}, after={}, target_fingerprint="abc",
    )
    assert store.get_pending(proposal["id"])["status"] == "expired"
```

- [ ] **Step 2: Run RED**

```bash
python -m pytest -q tests/test_luna_control_center.py -k "proposal or expired"
```

- [ ] **Step 3: Implement fingerprint and proposal envelope**

```python
def proposal_fingerprint(value: dict) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ProposalStore:
    PATH = "data/panel_pending_actions.json"

    def __init__(self, data, ttl_minutes: int = 15) -> None:
        self.data = data
        self.ttl_minutes = ttl_minutes

    def create(self, *, capability: str, target: dict, payload: dict,
               summary_fa: str, before: dict, after: dict,
               target_fingerprint: str) -> dict:
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

Implement `_prepend`, `get_pending`, and `complete` using the same 409/422 retry pattern already used by panel JSON writers. `get_pending` returns `status="expired"` when `expires_at <= now`.

- [ ] **Step 4: Run GREEN and commit**

```bash
python -m pytest -q tests/test_luna_control_center.py -k "proposal or expired"
git add panel/luna_proposals.py tests/test_luna_control_center.py
git commit -m "feat: add frozen Luna mutation proposals"
```

---

### Task 6: Structured Context and Safe Entity Resolution

**Files:**
- Create: `panel/luna_context.py`
- Modify: `panel/luna_conversation.py`
- Modify: `tests/test_luna_control_center.py`

**Interfaces:**
- Produces: `LunaContextResolver.resolve_source(args, context) -> dict`, `resolve_story(args, context) -> dict`, context keys `last_story_id`, `last_source_id`, `last_action_id`, `last_builder_pr`.

- [ ] **Step 1: Write exact, pronoun, and ambiguity tests**

```python
def test_source_resolver_matches_exact_normalized_name():
    resolver = LunaContextResolver(toolbox)
    result = resolver.resolve_source({"query": "ClashReports"}, {})
    assert result["ok"] is True
    assert result["source"]["id"] == "src-clash"


def test_source_resolver_refuses_ambiguous_target():
    resolver = LunaContextResolver(toolbox_with_two_clash_sources())
    result = resolver.resolve_source({"query": "clash"}, {})
    assert result["ok"] is False
    assert result["error"] == "ambiguous_source"


def test_story_pronoun_uses_structured_last_story_id():
    resolver = LunaContextResolver(toolbox)
    result = resolver.resolve_story({}, {"last_story_id": "story-9"})
    assert result["ok"] is True
    assert result["story"]["id"] == "story-9"
```

- [ ] **Step 2: Run RED**

```bash
python -m pytest -q tests/test_luna_control_center.py -k "resolver"
```

- [ ] **Step 3: Implement precedence and ambiguity policy**

```python
class LunaContextResolver:
    def __init__(self, toolbox) -> None:
        self.toolbox = toolbox

    def resolve_source(self, args: dict, context: dict) -> dict:
        source_id = str(args.get("source_id") or "").strip()
        if source_id:
            return self._source_by_id(source_id)
        query = str(args.get("query") or "").strip()
        if query:
            return self._source_by_query(query)
        previous = str(context.get("last_source_id") or "").strip()
        if previous:
            return self._source_by_id(previous)
        return {"ok": False, "error": "source_target_required", "message": "منبع دقیق مشخص نیست."}
```

`_source_by_query` checks normalized exact ID/name/handle/channel first. If there is no exact match it may gather substring candidates for clarification, but if candidate count is not exactly one it returns `ambiguous_source` or `source_not_found`; it never silently picks the first candidate.

Story resolution follows the same order: exact `story_id`, then `last_story_id`, then explicit search result chosen only when unique.

- [ ] **Step 4: Extend conversation storage with a small structured context object**

```python
def get_context(self, conversation_id: str) -> dict:
    record = self._get_conversation(conversation_id)
    value = record.get("context") if isinstance(record, dict) else {}
    return dict(value) if isinstance(value, dict) else {}


def update_context(self, conversation_id: str, **values) -> dict:
    allowed = {"last_story_id", "last_source_id", "last_action_id", "last_builder_pr"}
    clean = {key: value for key, value in values.items() if key in allowed and value not in (None, "")}
    return self._write_context(conversation_id, clean)
```

Adapt `_get_conversation`/`_write_context` to the actual existing store internals rather than adding a second conversation file.

- [ ] **Step 5: Run GREEN and commit**

```bash
python -m pytest -q tests/test_luna_control_center.py -k "resolver or context"
git add panel/luna_context.py panel/luna_conversation.py tests/test_luna_control_center.py
git commit -m "feat: add structured Luna entity context"
```

---

### Task 7: Unified Control Runtime for Source and Story Mutations

**Files:**
- Create: `panel/luna_control_runtime.py`
- Modify: `panel/luna_tools.py`
- Modify: `panel/luna_tool_runtime.py`
- Modify: `panel/luna_operator_api.py`
- Modify: `panel/luna_publish.py`
- Modify: `tests/test_luna_control_center.py`
- Modify: existing operator tests.

**Interfaces:**
- Produces: `LunaControlRuntime.invoke(name, args, context) -> dict`, `confirm(action_id) -> dict`.
- Source mutations: rename, add, enable, disable, delete/hide, review-only policy.
- Story mutations: Luna translation/save, publish machine/Luna, review, reject/block.

- [ ] **Step 1: Write read-vs-mutation and changed-target tests**

```python
def test_read_capability_executes_without_confirmation():
    runtime = _runtime()
    result = runtime.invoke("inspect_panel_state", {}, {})
    assert result["ok"] is True
    assert result.get("confirmation_required") is not True


def test_rename_source_requires_specific_confirmation():
    runtime = _runtime_with_source("src-clash", name="ClashReports")
    result = runtime.invoke(
        "rename_source",
        {"source_id": "src-clash", "display_name": "کلش ریپورتز"},
        {},
    )
    assert result["confirmation_required"] is True
    assert result["summary_fa"] == "نام نمایشی ClashReports به «کلش ریپورتز» تغییر کند؟"
    assert _source_name(runtime, "src-clash") == "ClashReports"


def test_changed_target_after_proposal_fails_closed():
    runtime = _runtime_with_source("src-clash", name="ClashReports")
    proposal = runtime.invoke("rename_source", {"source_id": "src-clash", "display_name": "کلش ریپورتز"}, {})
    _force_source_name(runtime, "src-clash", "Changed Elsewhere")
    result = runtime.confirm(proposal["action_id"])
    assert result["ok"] is False
    assert result["error"] == "target_changed"
```

- [ ] **Step 2: Write story publish freeze test**

```python
def test_publish_proposal_freezes_story_and_copy_mode():
    runtime = _runtime_with_story("story-1", persian_title="تیتر ماشینی")
    proposal = runtime.invoke("publish_story", {"story_id": "story-1", "copy_mode": "machine"}, {})
    saved = runtime.proposals.get_pending(proposal["action_id"])
    assert saved["payload"]["story_id"] == "story-1"
    assert saved["payload"]["copy_mode"] == "machine"
```

- [ ] **Step 3: Run RED**

```bash
python -m pytest -q tests/test_luna_control_center.py -k "read_capability or rename_source or changed_target or publish_proposal"
```

- [ ] **Step 4: Implement one runtime path**

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
            return self._execute(capability, resolved["args"], confirmed=True)
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

    def confirm(self, action_id: str) -> dict:
        proposal = self.proposals.get_pending(action_id)
        if proposal.get("status") != "pending":
            return {"ok": False, "error": "proposal_not_pending", "message": "این تأیید دیگر معتبر نیست."}
        current = self._current_target_snapshot(proposal)
        if proposal_fingerprint(current) != proposal["target_fingerprint"]:
            self.proposals.complete(action_id, "failed", {"error": "target_changed"})
            return {"ok": False, "error": "target_changed", "message": "هدف تغییر کرده؛ دوباره دستور بده."}
        capability = self.registry.get(proposal["capability"])
        result = self._execute(capability, dict(proposal["payload"]), confirmed=True)
        self.proposals.complete(action_id, "success" if result.get("ok") else "failed", result)
        self._audit(capability, proposal, result)
        return result
```

- [ ] **Step 5: Implement source previews/executors**

`rename_source` preview must preserve identity/handle and change only display name. System sources persist `display_name` in `data/source_overrides.json`; custom sources update their display-name field. `set_source_review_only` persists `review_only: true|false` in the corresponding safe source record/override.

Exact rename summary:

```python
summary_fa = f"نام نمایشی {before_name} به «{new_name}» تغییر کند؟"
```

- [ ] **Step 6: Implement story previews/executors**

`translate_story` is a mutation because it saves Luna copy. Its confirmed executor calls the existing `translate_story_in_repository` once. `publish_story` freezes `story_id` and `copy_mode`, and the executor calls `publish_story(..., copy_mode=...)`. `reject_and_block_story` and `move_story_to_review` use existing toolbox semantics but only after confirmation.

- [ ] **Step 7: Replace ad-hoc pending creation in operator API**

The function-call loop calls `runtime.invoke`. If it returns `confirmation_required`, return its `action_id/summary_fa`; do not create a second pending record. `/operator-confirm/<action_id>` calls `runtime.confirm(action_id)`.

Preserve the current stateless Responses continuation: keep `store:false` and local response/tool replay, and do not reintroduce `previous_response_id`.

- [ ] **Step 8: Prevent false-success prose**

Add a regression test where an executor returns `ok=false` and assert the operator reply does not contain `انجام شد`. When there is a pending mutation, the server may return `summary_fa` directly without another provider call.

- [ ] **Step 9: Run GREEN and commit**

```bash
python -m pytest -q tests/test_luna_control_center.py tests/test_panel_luna_operator_v41.py tests/test_panel_luna_stateless_continuation_v41.py tests/test_panel_luna_tools_v41.py
git add panel/luna_control_runtime.py panel/luna_tools.py panel/luna_tool_runtime.py panel/luna_operator_api.py panel/luna_publish.py tests/test_luna_control_center.py tests/test_panel_luna_operator_v41.py
git commit -m "feat: route Luna mutations through confirmed runtime"
```

---

### Task 8: Diagnostics, Safe Settings, and Builder Use the Same Policy

**Files:**
- Modify: `panel/luna_capabilities.py`
- Modify: `panel/luna_control_runtime.py`
- Modify: `panel/luna_operator_api.py`
- Modify: `panel/luna_builder.py`
- Modify: `panel/luna_builder_tools.py`
- Modify: `tests/test_luna_control_center.py`
- Existing Builder tests.

**Interfaces:**
- `diagnose_newsroom`, `inspect_panel_state`, `builder_ci_status` are read-only.
- `set_newsroom_alarm`, `builder_prepare`, `builder_prepare_merge` mutate and require proposals.

- [ ] **Step 1: Write diagnosis and setting tests**

```python
def test_diagnosis_is_read_only():
    runtime = _runtime()
    result = runtime.invoke("diagnose_newsroom", {}, {})
    assert result["ok"] is True
    assert result.get("confirmation_required") is not True


def test_alarm_setting_requires_confirmation():
    runtime = _runtime()
    proposal = runtime.invoke("set_newsroom_alarm", {"enabled": False}, {})
    assert proposal["confirmation_required"] is True
```

- [ ] **Step 2: Write Builder safety tests**

```python
def test_builder_prepare_creates_no_branch_before_confirmation():
    runtime = _runtime_with_fake_builder()
    proposal = runtime.invoke("builder_prepare", {"request": "این دکمه رو ببر سمت راست"}, {})
    assert proposal["confirmation_required"] is True
    assert runtime.fake_builder.created_branches == []


def test_builder_merge_stays_blocked_when_ci_is_not_green():
    runtime = _runtime_with_fake_builder(ci_green=False)
    proposal = runtime.invoke("builder_prepare_merge", {"pr_number": 123}, {})
    result = runtime.confirm(proposal["action_id"])
    assert result["ok"] is False
    assert result["error"] == "builder_ci_not_green"
```

- [ ] **Step 3: Run RED**

```bash
python -m pytest -q tests/test_luna_control_center.py -k "diagnosis or alarm_setting or builder"
```

- [ ] **Step 4: Register safe setting only**

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

Persist to the panel's existing operator settings store. Do not add a generic environment editor.

- [ ] **Step 5: Keep diagnosis factual and non-mutating**

Return available queue counts, source health, translation failures, recent command failures, and Builder status. A proposed fix is a separate mutation proposal.

- [ ] **Step 6: Route Builder classification to the registry**

`is_builder_request(message)` may classify natural code/UI requests, but it invokes `builder_prepare`; it must no longer write a custom pending record. `builder_prepare_merge` freezes both `pr_number` and `expected_head_sha`, and its executor rechecks CI green before merge.

- [ ] **Step 7: Run GREEN and commit**

```bash
python -m pytest -q tests/test_luna_control_center.py tests/test_panel_luna_builder_v41.py tests/test_github_builder.py
git add panel/luna_capabilities.py panel/luna_control_runtime.py panel/luna_operator_api.py panel/luna_builder.py panel/luna_builder_tools.py tests/test_luna_control_center.py
git commit -m "refactor: unify diagnostics settings and Builder policy"
```

---

### Task 9: Operator UX, Full Regression, CI, and Live Smoke

**Files:**
- Modify: `panel/static/luna-assistant.js`
- Modify: `panel/luna_operator_api.py`
- Modify: `panel/static/sw.js` if assistant JS cache changes require another cache bump.
- Tests: full suite.

**Interfaces:**
- One generic mutation confirmation UI consumes `action_id` and `summary_fa`.
- Structured context updates only from concrete tool/runtime results.

- [ ] **Step 1: Write the natural ClashReports acceptance test**

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

- [ ] **Step 2: Keep the system instruction short and policy-exact**

```text
تو Luna، کنترل‌گر عملیاتی فارسی اتاق خبر بی‌خبر هستی.
برای اطلاعات و عملیات از capabilityهای تعریف‌شده استفاده کن.
کارهای فقط خواندنی را مستقیم انجام بده.
هر کاری که داده، منبع، تنظیمات، انتشار، کد، UI یا deployment را تغییر می‌دهد باید قبل از اجرا به تأیید کاربر برسد.
اگر هدف مبهم است، یک سؤال کوتاه بپرس و هیچ تغییر یا proposal اشتباه نساز.
موفقیت را فقط وقتی اعلام کن که executor نتیجه موفق داده باشد.
```

- [ ] **Step 3: Use one generic confirmation renderer**

```javascript
function renderPendingAction(payload) {
  confirmationBox.hidden = false;
  confirmationText.textContent = payload.summary_fa || 'این تغییر انجام شود؟';
  confirmButton.dataset.actionId = payload.action_id || '';
}
```

Existing confirm button posts to `/api/panel/luna/operator-confirm/<action_id>`; all mutation types use this same endpoint.

- [ ] **Step 4: Reduce unnecessary provider rounds**

When `runtime.invoke` returns a mutation proposal, return its exact `summary_fa` immediately from the operator endpoint instead of asking the provider to paraphrase it in another response round. Continue provider rounds only when more read-only tool results are actually needed to answer the request.

- [ ] **Step 5: Run JavaScript syntax checks**

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

- [ ] **Step 6: Run the complete regression suite**

```bash
python -m pytest -q
```

Expected: all tests pass except pre-existing intentional skips.

- [ ] **Step 7: Open one implementation PR against `main` and wait for both required workflows**

Required green checks:

```text
Pull Request Check
Telegram News Agent CI
```

Do not merge while either required check is queued, running, unexpectedly skipped, or failed.

- [ ] **Step 8: Whole-branch review against security and product acceptance**

Reviewer checks exactly:

```text
- all mutations proposal-gated
- frozen payload confirmation
- ambiguous targets fail closed
- machine and Luna publishing separate
- only v3_publish performs publication enqueue
- no arbitrary dangerous capability
- Builder branch/CI/merge gate intact
- no false success message on executor failure
- initial feed makes no alarm
- new story after interaction makes one alarm
- queued/failed publish keeps card
- succeeded/reconciled publish removes card
- machine Persian persists before direct publish
```

- [ ] **Step 9: Merge only after explicit operator approval**

Squash merge to `main`; allow existing main CI to promote the exact tested SHA to `production`.

- [ ] **Step 10: Verify deployment with one Termius command**

```bash
sudo systemctl start bikhabar-deploy.service && sleep 5 && echo "HEAD=$(git -C /opt/bikhabar/app rev-parse HEAD)" && echo "PANEL=$(systemctl is-active bikhabar-panel.service)"
```

Expected: `HEAD` equals the promoted production SHA and `PANEL=active`.

- [ ] **Step 11: Live smoke in this order**

```text
1. English story arrives → within localization poll/reload its persisted machine Persian is primary.
2. After one browser interaction, a later new story triggers one short ding, then reloads into view.
3. Direct machine publish → confirmation → queue/poll → only succeeded/reconciled removes the card.
4. Luna translate → Luna copy passes quality → Luna publish confirmation → successful publication.
5. “لونا ClashReports رو فارسی بنویس و اصلاح کن” → exact rename proposal → confirm → visible source name changes to «کلش ریپورتز» while identity stays unchanged.
6. Read-only diagnosis returns without confirmation.
7. “این دکمه رو ببر سمت راست” → Builder proposal; no branch before confirmation.
8. Builder merge stays blocked unless CI is fully green.
```

- [ ] **Step 12: Commit final review-only fixes and rerun the full suite before merge**

```bash
python -m pytest -q
```

Expected: green before final merge.
