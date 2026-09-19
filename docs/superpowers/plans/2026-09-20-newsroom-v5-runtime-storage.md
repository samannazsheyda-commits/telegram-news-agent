# Newsroom V5 Implementation Plan 1 — Runtime Storage and Migration

**Spec:** `docs/superpowers/specs/2026-09-20-newsroom-app-luna-v5-design.md`

**Goal:** Introduce a local SQLite/WAL runtime store and a reversible migration path without changing production behavior or enabling auto-publish.

**Safety boundary:** This plan does not switch production to SQLite, does not publish news, and does not remove GitHub JSON compatibility. The cutover remains behind `NEWSROOM_STORE_BACKEND` and requires a later deployment approval.

## Task 1 — Add failing storage contract tests

**Create:** `tests/test_newsroom_v5_store.py`

Write RED tests for:

- database initialization creates the expected schema version;
- `PRAGMA journal_mode` resolves to WAL for file-backed databases;
- foreign keys are enabled;
- `stories`, `translations`, `editorial_decisions`, `publications`, `story_tombstones`, `sources`, `jobs`, `luna_conversations`, and `audit_log` exist;
- transaction rollback leaves no partial story/publication state;
- unique publication idempotency keys reject duplicate insertion;
- Review query sorts by `published_at_source DESC, id DESC`;
- Review query excludes `published`, `rejected`, `duplicate`, `irrelevant`, and non-Persian-ready records.

Run:

```bash
python -m pytest -q tests/test_newsroom_v5_store.py
```

Expected RED: imports/schema APIs do not exist yet.

## Task 2 — Implement SQLite bootstrap and transaction boundary

**Create:** `src/newsroom_v5_db.py`

Implement:

- `SCHEMA_VERSION = 1`;
- `connect(path)` with `sqlite3.Row`, `PRAGMA foreign_keys=ON`, `PRAGMA busy_timeout=5000`, WAL for file-backed DBs;
- `initialize(conn)` with an internal `schema_meta` table;
- one explicit transaction context manager;
- schema and indexes required by the approved spec.

Keep SQL local to this module. Do not mix HTTP/GitHub access into it.

Run:

```bash
python -m pytest -q tests/test_newsroom_v5_store.py
```

Expected: schema/transaction tests become GREEN; repository-level tests may remain RED until Task 3.

## Task 3 — Add the canonical V5 store API

**Create:** `src/newsroom_v5_store.py`

Expose a small runtime interface used by later plans:

- `upsert_story(...)`;
- `get_story(story_id)`;
- `set_translation(...)`;
- `set_editorial_decision(...)`;
- `transition_story(story_id, expected_states, new_state)`;
- `add_story_tombstone(...)` and `is_tombstoned(...)`;
- `list_review(limit, cursor)` returning `{items, next_cursor}`;
- `create_publication_once(...)` using unique idempotency key;
- `enqueue_job(...)`, `claim_jobs(...)`, `finish_job(...)`, `retry_job(...)`;
- source and audit helpers needed by migration.

Cursor encoding must be deterministic and based on `(published_at_source, id)`, not page offsets.

Extend `tests/test_newsroom_v5_store.py` with RED→GREEN tests for each contract, including two stories with the same timestamp.

Run:

```bash
python -m pytest -q tests/test_newsroom_v5_store.py
```

## Task 4 — Add a runtime-store selector without changing default behavior

**Create:** `src/newsroom_store_factory.py`

**Modify:** `panel/app.py`

Add `NEWSROOM_STORE_BACKEND=github|sqlite` with default `github` during migration. Add `NEWSROOM_SQLITE_PATH` with a production default under `/var/lib/bikhabar/` but use temp paths in tests.

The factory should return the new V5 store only when explicitly selected. Existing GitHub-backed code must remain untouched as the default at the end of this plan.

**Create:** `tests/test_newsroom_store_factory.py`

Test:

- missing env → legacy/GitHub selection;
- `sqlite` → V5 store;
- invalid backend → fail fast with a clear configuration error;
- test DB path is created safely.

Run:

```bash
python -m pytest -q tests/test_newsroom_store_factory.py tests/test_newsroom_v5_store.py
```

## Task 5 — Build an idempotent JSON→SQLite migration importer

**Create:** `src/newsroom_v5_migration.py`

**Create:** `scripts/migrate_newsroom_v5.py`

Importer inputs:

- `data/panel_live_feed.json`;
- `data/editorial_queue.json`;
- `data/editorial_history.json`;
- `data/custom_sources.json`;
- `state.json`.

Rules:

- preserve stable ids/news keys/source URLs where present;
- terminal history wins over active/live projections;
- published rows become `published` and retain Telegram metadata when available;
- `rejected_manual` creates an exact-story tombstone;
- Persian translations/final copy are imported when present;
- importing the same snapshot twice is idempotent;
- never infer source blocking from a rejected story.

The CLI supports:

```bash
python scripts/migrate_newsroom_v5.py --db /tmp/bikhabar-v5.db --from-local-repo . --dry-run
python scripts/migrate_newsroom_v5.py --db /tmp/bikhabar-v5.db --from-local-repo . --apply
```

`--dry-run` prints counts and conflicts but writes nothing.

**Create:** `tests/test_newsroom_v5_migration.py`

Fixtures should include: one active translated story, one untranslated story, one published story, one rejected story, one duplicate projection of the rejected story, and a later different story from the same source.

Run:

```bash
python -m pytest -q tests/test_newsroom_v5_migration.py
```

## Task 6 — Add parity verification and rollback evidence

**Create:** `scripts/verify_newsroom_v5_migration.py`

The verifier compares legacy JSON projections to SQLite and reports:

- active logical stories;
- published identities;
- rejected identities/tombstones;
- source count and enabled state;
- Persian-ready count;
- unresolved conflicts.

Exit non-zero on identity/count mismatches that would lose an eligible story or resurrect a terminal story.

**Create:** `tests/test_newsroom_v5_migration_verify.py`

Run:

```bash
python -m pytest -q tests/test_newsroom_v5_migration.py tests/test_newsroom_v5_migration_verify.py
```

## Task 7 — Regression and full-suite verification

Run focused existing tests most likely to catch compatibility damage:

```bash
python -m pytest -q \
  tests/test_ai_newsroom.py \
  tests/test_ai_newsroom_pipeline.py \
  tests/test_ai_runtime_wiring.py \
  tests/test_ai_translation_editor.py
```

Then run the complete suite:

```bash
python -m pytest -q
```

Do not claim Plan 1 complete unless both focused and full-suite commands exit 0.

## Completion gate

Plan 1 is complete only when:

- SQLite schema/store tests are green;
- migration can dry-run and apply idempotently;
- parity verifier catches deliberate mismatches;
- default runtime remains legacy/GitHub;
- no publish path has changed;
- full regression suite is green.

After this plan, create a dedicated implementation PR. Do not merge or deploy without fresh user approval.