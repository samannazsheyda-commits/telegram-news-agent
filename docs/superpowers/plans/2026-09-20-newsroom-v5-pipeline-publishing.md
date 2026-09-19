# Newsroom V5 Implementation Plan 2 — Translation, Editorial Routing, and Publishing

**Depends on:** Plan 1 runtime storage and migration.

**Goal:** Make the canonical pipeline translation-first, preserve every eligible unpublished story for Review, add durable exact-story rejection, and move Telegram sends behind an idempotent outbox. Auto-publish remains OFF by default.

## Task 1 — Lock the pipeline contract with RED tests

**Create:** `tests/test_newsroom_v5_pipeline.py`

Cover these invariants before implementation:

1. untranslated English story is stored but never returned by Review;
2. successful translation advances `received → translated`;
3. relevant nonduplicate story not selected for auto-publish advances to `review`;
4. critical/high-confidence story with auto-publish disabled still advances to `review`;
5. duplicate/irrelevant story does not enter Review;
6. a translation provider failure leaves the raw story durable and schedules retry;
7. same source can produce a new later story even if an older story was rejected;
8. source timestamp is preserved through all stages.

Run:

```bash
python -m pytest -q tests/test_newsroom_v5_pipeline.py
```

Expected RED: V5 pipeline coordinator does not exist.

## Task 2 — Implement durable jobs and worker claim semantics

**Create:** `src/newsroom_v5_jobs.py`

Implement job kinds:

- `translate_story`;
- `editorial_story`;
- `publish_story`;
- `reconcile_publication`.

Job claims must be atomic. A crashed worker must not permanently strand a job: use lease timestamps/attempt counters and deterministic retry scheduling with bounded exponential backoff plus jitter.

Extend `tests/test_newsroom_v5_store.py` or create `tests/test_newsroom_v5_jobs.py` for:

- only one worker claims a job;
- expired lease becomes claimable;
- retry increments attempts and keeps story durable;
- terminal failure records an error without deleting story.

Run:

```bash
python -m pytest -q tests/test_newsroom_v5_jobs.py
```

## Task 3 — Build translation-first worker with AI fallback

**Create:** `src/newsroom_v5_translation.py`

Reuse the existing `src/services.py::translate_to_fa` as tier 1. Add an injected AI translation fallback built around the existing newsroom AI/provider abstraction rather than making HTTP calls directly from this module.

Rules:

- already-Persian source copy is normalized and accepted if QC passes;
- lightweight translator success is stored with backend metadata;
- if lightweight stack returns empty/unpublishable, try AI fallback;
- if all providers fail, schedule retry and keep story internal;
- never mark a failed translation as seen/gone;
- no page request may invoke translation synchronously.

**Create:** `tests/test_newsroom_v5_translation.py`

Test lightweight success, lightweight fail→AI success, all fail→retry, source Persian, and QC rejection.

Run:

```bash
python -m pytest -q tests/test_newsroom_v5_translation.py
```

Also run existing translator regression:

```bash
python -m pytest -q tests/test_ai_translation_editor.py
```

## Task 4 — Add durable exact-story tombstones before dedup retry logic

**Create:** `src/newsroom_v5_identity.py`

Define canonical rejection identity in this order:

1. stable `source_item_id`/`news_key` when present;
2. exact canonical `source_url` fallback.

Do not use broad topic/title similarity for manual rejection.

**Create:** `tests/test_newsroom_v5_tombstones.py`

Required regression cases:

- reject story A → rescan identical A → A never returns;
- reject A → source item id changes but exact canonical URL is same → suppressed;
- reject A from source X → new story B from source X → B remains eligible;
- duplicate engine must not reinterpret a rejected unpublished event as retryable content.

Run:

```bash
python -m pytest -q tests/test_newsroom_v5_tombstones.py
```

## Task 5 — Implement editorial routing

**Create:** `src/newsroom_v5_editorial.py`

Reuse `src/ai_newsroom.py` decision contracts. Keep editorial Luna separate from operator Luna.

Routing function takes a Persian-ready story plus dedup/tombstone/source state and returns one explicit outcome:

- `review`;
- `auto_publish_candidate`;
- `duplicate`;
- `irrelevant`;
- `failed`.

Auto-publish eligibility requires every spec gate. Add configuration:

- `NEWSROOM_AUTO_PUBLISH_ENABLED=false` default;
- confidence/importance thresholds with safe defaults;
- anti-flood pacing settings.

If auto-publish is OFF or any auto gate fails but the story remains relevant/nonduplicate, route to `review`.

**Create:** `tests/test_newsroom_v5_editorial.py`

Test critical/high/normal/low, concrete new fact vs routine statement, auto-publish OFF, missing QC, disabled source, stale story, and relevant fallback to Review.

Run:

```bash
python -m pytest -q tests/test_newsroom_v5_editorial.py tests/test_ai_newsroom.py
```

## Task 6 — Implement the end-to-end coordinator

**Create:** `src/newsroom_v5_pipeline.py`

Coordinator responsibilities:

- accept normalized ingest records;
- persist before external processing;
- tombstone/exact-identity check;
- dedup/event relation;
- enqueue translation;
- enqueue editorial after translation;
- transition eligible story to Review or publication outbox candidate.

Avoid hidden side effects: each state transition must be explicit and testable.

Wire a shadow-mode entry from the existing ingest path without changing production output yet.

**Modify:** `src/panel_command_file.py`

Add a feature flag such as `NEWSROOM_V5_SHADOW_PIPELINE=false`. When enabled in tests/shadow runs, V5 consumes the same fresh inputs but must not publish Telegram messages.

Run:

```bash
python -m pytest -q tests/test_newsroom_v5_pipeline.py
```

## Task 7 — Add transactional publication outbox

**Create:** `src/newsroom_v5_publish.py`

A publish request must, in one DB transaction:

1. ensure story is publishable and not terminal;
2. materialize the exact Persian copy to send;
3. create a publication row with unique idempotency key;
4. set story to `publishing`;
5. enqueue `publish_story`;
6. commit.

Double-click/retry must return the existing publication rather than create a second send.

**Create:** `tests/test_newsroom_v5_publish.py`

Test:

- same idempotency key twice → one publication;
- story already published → no second send;
- transaction failure → neither `publishing` nor outbox partial state remains;
- exact Persian payload is frozen before send.

Run:

```bash
python -m pytest -q tests/test_newsroom_v5_publish.py
```

## Task 8 — Telegram send worker and ambiguous-timeout reconciliation

Reuse existing Telegram formatting/sending code through injected adapters; do not duplicate Telegram API logic inside the store.

**Modify or adapt:** `src/services.py` and existing command/publish adapter only as needed.

**Create:** `tests/test_newsroom_v5_publish_reconcile.py`

Cases:

- successful send records `telegram_message_id` and transitions story to `published`;
- hard failure schedules retry according to policy;
- ambiguous timeout schedules reconciliation, not blind immediate resend;
- reconciled success does not send again;
- published event becomes available for SSE in Plan 3.

Run:

```bash
python -m pytest -q tests/test_newsroom_v5_publish.py tests/test_newsroom_v5_publish_reconcile.py
```

## Task 9 — Anti-flood behavior and quota compatibility

Do not silently discard stories when a daily limit or pacing threshold is reached.

**Create:** `tests/test_newsroom_v5_antiflood.py`

Prove:

- burst pacing serializes auto-publication jobs;
- a blocked/paused auto-publication candidate lands in Review;
- any legacy daily limit condition cannot make an eligible story disappear;
- Review retains all eligible stories logically.

Run:

```bash
python -m pytest -q tests/test_newsroom_v5_antiflood.py
```

## Task 10 — Full verification in shadow mode

Run:

```bash
NEWSROOM_STORE_BACKEND=sqlite \
NEWSROOM_V5_SHADOW_PIPELINE=true \
NEWSROOM_AUTO_PUBLISH_ENABLED=false \
python -m pytest -q \
  tests/test_newsroom_v5_pipeline.py \
  tests/test_newsroom_v5_translation.py \
  tests/test_newsroom_v5_tombstones.py \
  tests/test_newsroom_v5_editorial.py \
  tests/test_newsroom_v5_publish.py \
  tests/test_newsroom_v5_publish_reconcile.py \
  tests/test_newsroom_v5_antiflood.py
```

Then:

```bash
python -m pytest -q
```

## Completion gate

Plan 2 is complete only when translation failures cannot leak English or lose stories, rejection is durable and source-scoped correctly, unpublished eligible stories always reach Review, publishing is idempotent/reconcilable, auto-publish defaults OFF, and the full regression suite is green.

Do not enable auto-publish, merge, or deploy without separate explicit approval.