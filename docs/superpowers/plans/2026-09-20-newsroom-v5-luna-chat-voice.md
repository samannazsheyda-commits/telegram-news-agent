# Newsroom V5 Implementation Plan 4 — Luna Operator, Chat, and Voice

**Depends on:** Plan 1 runtime store. Integrates with Plan 3 app shell; may be developed after Plan 2 APIs stabilize.

**Goal:** Make Luna behave like a competent conversational operator: context-aware Persian, one necessary tool execution per intent, no internal tool-log spam, correct confirmation boundaries, fast/simple model routing, first-class voice→text, and clean messenger UX.

## Task 1 — Freeze current behavioral failures with RED tests

**Create:** `tests/test_luna_v5_operator.py`

Build fake provider/runtime fixtures that can force repeated function calls. Required RED tests:

- model asks for identical `list_sources` twice in one user turn → executor must ultimately run once;
- different args → separate executions;
- successful read request returns useful content, not only «انجام شد»;
- successful confirmed mutation returns a short natural Persian acknowledgement;
- publish/delete/source/settings/code mutations remain confirmation-required;
- read/status/analysis operations do not require confirmation;
- executor failure cannot be described as completed;
- context reference such as «همین خبر» resolves to structured current story id.

Run:

```bash
python -m pytest -q tests/test_luna_v5_operator.py
```

## Task 2 — Add canonical per-turn tool-call deduplication

**Modify:** `panel/luna_operator_api.py`

**Create:** `panel/luna_turn_cache.py`

Canonical key:

```python
(tool_name, json.dumps(arguments, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
```

For each user turn:

- first call invokes runtime and caches the result;
- identical later call reuses cached result for the model continuation;
- duplicate call does not append another user-visible event;
- audit may record cache reuse separately if useful;
- confirmation-required mutations must not be executed by cache logic before confirmation.

Keep `_MAX_TOOL_ROUNDS` as a safety bound, not as permission to repeat work.

Run:

```bash
python -m pytest -q tests/test_luna_v5_operator.py
```

## Task 3 — Separate internal execution events from conversational output

**Modify:** `panel/luna_operator_api.py`

Response contract becomes explicit:

- `reply_fa`: normal conversational answer;
- `confirmation_required`, `action_id`, `summary_fa`: only when needed;
- `builder` result metadata when relevant;
- no normal `tool_events` payload for successful internal reads/actions.

Execution/audit events remain server-side.

Update `_SYSTEM` instructions so Luna:

- never narrates tool names/internal mechanics;
- does not repeat an identical read call;
- gives concise human success replies;
- explains errors/ambiguity when actionable;
- answers the actual content for read requests.

Do not weaken the mutation-confirmation contract.

## Task 4 — Add deterministic model routing

**Create:** `panel/luna_model_router.py`

Inputs should be explicit enough to unit-test. Prefer fast model for:

- simple read/status;
- straightforward tool operations;
- short conversational commands.

Prefer complex configured model for:

- multi-story synthesis;
- editorial reasoning with ambiguity;
- higher-stakes interpretation where tool output alone is insufficient;
- explicit deep analysis requests.

Do not expose model names in normal UI.

**Create:** `tests/test_luna_v5_model_router.py`

Run:

```bash
python -m pytest -q tests/test_luna_v5_model_router.py
```

**Modify:** `panel/luna_operator_api.py` to call the router instead of always forcing `client.fast_model`.

## Task 5 — Move conversation/context persistence to the V5 store adapter

**Modify:** `panel/luna_conversation.py`

**Modify:** `panel/luna_operator_api.py`

Add a storage adapter so conversation messages/context can use `luna_conversations` in SQLite while keeping a legacy file adapter during migration.

Context must preserve:

- current/last story id;
- current/last source id;
- pending action id;
- recent messages within a bounded context window;
- last Builder PR reference where relevant.

**Create:** `tests/test_luna_v5_conversation_store.py`

Test persistence across new HTTP requests and strict separation between two session conversation ids.

## Task 6 — Add explicit story-context handoff API

**Modify:** `panel/luna_operator_api.py`

Add a lightweight endpoint such as:

`POST /api/v5/luna/context/story/<story_id>`

It validates story visibility/access and updates structured Luna context. It does not fabricate a chat message.

**Extend:** `tests/test_luna_v5_operator.py`

Prove «تیترشو کوتاه‌تر کن» after context handoff targets the selected story without copying its text into the user prompt.

## Task 7 — Redesign Luna messenger markup and frontend behavior

**Modify:** `panel/templates/luna.html`

**Rewrite/Modify:** `panel/static/luna-assistant.js`

**Modify:** `panel/static/newsroom-v4-luna.css` or replace with V5-scoped styles used by the app shell.

Required UI behavior:

- only user/Luna messages in normal history;
- no generic green tool cards for reads/successes;
- pending sensitive action appears as one compact inline confirmation state;
- confirmed success becomes a normal Luna message;
- errors appear compactly with retry where appropriate;
- image attachment remains supported;
- composer draft persists during tab changes;
- `Ask Luna` story handoff enters this conversation with visible story context label/chip, not raw internal ids.

**Create:** `tests/test_luna_v5_frontend_contract.py`

Static assertions must reject legacy `showToolEvents`/generic success-card behavior in V5 and require the new confirmation/message paths.

## Task 8 — Make voice a first-class composer state

Backend transcription already exists; preserve the provider adapter instead of adding a parallel transcription stack.

**Modify:** `panel/static/luna-assistant.js`

Implement states:

- idle;
- recording;
- transcribing;
- transcript-ready;
- error.

UX:

- tap mic starts recording;
- second tap stops;
- show elapsed timer and lightweight waveform/level indicator;
- cancel discards recording;
- transcription is inserted into the editable composer;
- user edits then sends;
- voice progress is composer UI, not chat tool cards;
- when `MediaRecorder/getUserMedia` unavailable, use existing audio-file capture fallback.

**Modify:** `panel/templates/luna.html` for timer/cancel/status controls.

**Create:** `tests/test_luna_v5_voice_api.py`

Test supported formats, missing/empty/oversize files, provider error mapping, and successful transcript response.

**Extend:** `tests/test_luna_v5_frontend_contract.py` to assert record/stop/cancel/fallback hooks exist and old voice tool-card strings are absent from the normal conversation renderer.

Run:

```bash
python -m pytest -q tests/test_luna_v5_voice_api.py tests/test_luna_v5_frontend_contract.py
```

## Task 9 — Integrate confirmations with the app shell

Use the shared confirmation UI from Plan 3 instead of creating a second modal system.

Sensitive Luna proposal flow:

1. Luna returns proposal summary/action id;
2. UI renders one inline confirmation;
3. user accepts/rejects;
4. confirmed endpoint executes exactly once;
5. Luna renders the resulting normal message;
6. related Review/Published state changes arrive through SSE.

**Extend:** `tests/test_luna_v5_operator.py` for double-confirm idempotency and expired action behavior.

## Task 10 — Latency and failure behavior

**Create:** `tests/test_luna_v5_latency_contract.py`

Without external network calls, use fake provider timings/counters to verify:

- simple command does not invoke complex model unnecessarily;
- duplicate tool calls do not add executor latency;
- read tool result does not trigger avoidable extra model rounds once a final response is available;
- provider timeout returns a concise retryable response without losing conversation context.

Do not fake a strict OpenAI network latency SLA in CI; measure only controllable application overhead.

## Task 11 — Full Luna verification

Run focused tests:

```bash
python -m pytest -q \
  tests/test_luna_v5_operator.py \
  tests/test_luna_v5_model_router.py \
  tests/test_luna_v5_conversation_store.py \
  tests/test_luna_v5_voice_api.py \
  tests/test_luna_v5_frontend_contract.py \
  tests/test_luna_v5_latency_contract.py
```

Run relevant existing Luna tests discovered in the repository, including existing `test_air_traffic_luna.py` and panel/Luna tests found by filename, then:

```bash
python -m pytest -q
```

## Completion gate

Plan 4 is complete only when repeated identical tools execute once per turn, internal tool mechanics are absent from normal chat UI, read requests return content, successful mutations answer naturally, confirmation safety is unchanged, complex-vs-fast routing is tested, story context works, voice reliably produces editable text with fallback, and the full regression suite is green.

HTTPS remains a production precondition for reliable direct microphone capture. Do not deploy, merge, or enable new production behavior without fresh user approval.