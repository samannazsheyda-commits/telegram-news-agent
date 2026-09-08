# بی‌خبر Newsroom V2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a traceable newsroom pipeline that never silently drops important Iran-related news, deduplicates by event rather than topic overlap, keeps a live panel feed populated independently of auto-publish, and preserves Telegram idempotency.

**Architecture:** V2 introduces focused modules for normalization, event fingerprinting, event ledger persistence, decisioning, live-feed persistence, and orchestration. `runtime_v13.py` remains production during shadow verification; `runtime_v2.py` runs the new pipeline in shadow mode first, then becomes the workflow entrypoint only after regression, integration, panel, and Telegram verification gates pass.

**Tech Stack:** Python 3.12, pytest 8.4.2, requests, existing GitHub Actions workflow, Telegram Bot API, JSON-backed local/GitHub stores.

**Spec:** `docs/superpowers/specs/2026-09-07-newsroom-v2-design.md`

## Global Constraints

- Existing `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID=@bikhabaar` remain unchanged.
- No source adapter may perform final dedup/editorial suppression.
- Topic similarity alone may never suppress a protected/priority story.
- Every duplicate decision must include `duplicate_of=<event_id>` and a concrete reason.
- `panel_live_feed.json` must update even when `auto_publish=true`.
- `editorial_queue.json` is only for human-review/retry/paused-publication items.
- Telegram success requires `ok=true` and a `message_id` before marking a story published.
- `runtime_v13` stays available for rollback until V2 production verification succeeds.
- No VPS migration in this implementation phase.

---

## File Structure

**Create**
- `src/newsroom_models.py` — typed V2 item/event/decision/feed records.
- `src/newsroom_normalize.py` — actor/location/action/fact extraction and source normalization.
- `src/newsroom_fingerprint.py` — structural event fingerprint generation.
- `src/event_ledger.py` — JSON event ledger storage, updates, idempotency lookup.
- `src/newsroom_decision.py` — `new_event/material_update/duplicate_exact/duplicate_same_claim/needs_editorial_review` logic.
- `src/panel_live_feed.py` — live-feed store and freshness pruning.
- `src/newsroom_v2.py` — one-cycle V2 orchestration without CLI concerns.
- `src/runtime_v2.py` — CLI/monitor wrapper and shadow/production switches.
- `data/event_ledger.json` — initial empty ledger.
- `data/panel_live_feed.json` — initial empty live feed.
- `tests/test_newsroom_normalize.py`
- `tests/test_newsroom_fingerprint.py`
- `tests/test_event_ledger.py`
- `tests/test_newsroom_decision.py`
- `tests/test_panel_live_feed.py`
- `tests/test_newsroom_v2_integration.py`
- `tests/fixtures/newsroom_v2_regressions.json`

**Modify**
- `src/editorial_store.py` — add read/write support for live feed where panel backend needs it; preserve queue/history semantics.
- `src/panel_command_file.py` — refresh path uses V2 live snapshot and queues only reviewable items.
- panel backend/view files that currently read only queue/history — add live-feed read and three-section contract.
- `src/persist_merge.py` — merge/persist `event_ledger.json` and `panel_live_feed.json` safely.
- `.github/workflows/agent.yml` — add shadow phase first, later switch entrypoint to V2 after gates.
- tests around panel/persistence/workflow as required by touched code.

---

### Task 1: Define V2 Data Contracts

**Files:**
- Create: `src/newsroom_models.py`
- Test: `tests/test_newsroom_models.py`

**Interfaces:**
- Produces: `RawNewsItem`, `NormalizedNewsItem`, `EventFingerprint`, `DecisionResult`, `EventRecord`, `LiveFeedRecord` dataclasses.

- [ ] **Step 1: Write failing serialization and required-field tests** for all six dataclasses, including `DecisionResult.duplicate_of` being mandatory when decision starts with `duplicate_`.
- [ ] **Step 2: Run** `pytest tests/test_newsroom_models.py -v` and confirm failure because module/classes do not exist.
- [ ] **Step 3: Implement minimal frozen dataclasses** with `to_dict()`/`from_dict()` helpers and validation in `DecisionResult.__post_init__`.
- [ ] **Step 4: Run** `pytest tests/test_newsroom_models.py -v` and confirm pass.
- [ ] **Step 5: Commit** `feat: define newsroom v2 data contracts`.

### Task 2: Normalize News Into Structured Facts

**Files:**
- Create: `src/newsroom_normalize.py`
- Test: `tests/test_newsroom_normalize.py`

**Interfaces:**
- Consumes: `RawNewsItem`
- Produces: `normalize_item(item: RawNewsItem) -> NormalizedNewsItem`

- [ ] **Step 1: Add failing tests** for canonical actors (`Donald Trump`, `CENTCOM`, `White House`, `Mohsen Rezaei`, `Abbas Araghchi`), locations (`Strait of Hormuz`, Iran, Spain, Jordan), actions (`strike`, `close_airspace`, `reopen_airspace`, `intercept`, `announce_restricted_zone`, `redirect_vessels`) and numeric facts (`92`, `3`, `2`).
- [ ] **Step 2: Add failing test** proving normalization never returns `None` or suppresses an item.
- [ ] **Step 3: Run** `pytest tests/test_newsroom_normalize.py -v` and verify failures.
- [ ] **Step 4: Implement alias tables and extraction helpers** using deterministic regex/token rules; preserve original text and source identity.
- [ ] **Step 5: Run tests** and confirm pass.
- [ ] **Step 6: Commit** `feat: normalize newsroom actors actions and facts`.

### Task 3: Build Structural Event Fingerprints

**Files:**
- Create: `src/newsroom_fingerprint.py`
- Test: `tests/test_newsroom_fingerprint.py`

**Interfaces:**
- Consumes: `NormalizedNewsItem`
- Produces: `build_fingerprint(item) -> EventFingerprint`, `fingerprint_similarity(a, b) -> float`

- [ ] **Step 1: Add failing tests** proving AP/CNN/NYT three-tanker reports share the same structural core.
- [ ] **Step 2: Add failing tests** proving White House control of Hormuz, Iran restricted zone, and CENTCOM 92/3/2 are different fingerprints.
- [ ] **Step 3: Add failing tests** for airspace close vs reopen and Jordan missile interception vs Spain airspace closure.
- [ ] **Step 4: Implement fingerprint from canonical actor/action/object/location/key facts/time bucket**, with text similarity used only as a secondary score.
- [ ] **Step 5: Run** `pytest tests/test_newsroom_fingerprint.py -v` and confirm pass.
- [ ] **Step 6: Commit** `feat: add structural event fingerprints`.

### Task 4: Add Persistent Event Ledger

**Files:**
- Create: `src/event_ledger.py`
- Create: `data/event_ledger.json`
- Test: `tests/test_event_ledger.py`

**Interfaces:**
- Produces: `EventLedger(path)`, `find_candidates(fingerprint)`, `create_event(...)`, `add_variant(...)`, `mark_published(event_id, message_id, facts)`, `update_material_facts(...)`.

- [ ] **Step 1: Write failing tests** for empty ledger creation, deterministic persistence, source variants, message IDs, restart readback, and atomic write behavior.
- [ ] **Step 2: Run** ledger tests and verify failure.
- [ ] **Step 3: Implement JSON store** using atomic temp-file replacement patterned after `editorial_store.py`.
- [ ] **Step 4: Run tests** and confirm pass.
- [ ] **Step 5: Commit** `feat: add persistent newsroom event ledger`.

### Task 5: Replace Topic Dedup With Decision Engine

**Files:**
- Create: `src/newsroom_decision.py`
- Create: `tests/fixtures/newsroom_v2_regressions.json`
- Test: `tests/test_newsroom_decision.py`

**Interfaces:**
- Consumes: normalized item, fingerprint, ledger candidates.
- Produces: `decide_item(item, fingerprint, candidates) -> DecisionResult`.

- [ ] **Step 1: Encode real regression fixtures** for: CENTCOM 92/3/2; White House total Hormuz control; Iran restricted zone; Spain airspace closure; Iran partial reopen; Jordan intercept; IAEA/UNSC referral; airline restore/return; AP/CNN/NYT three tanker strike; two independent Trump Truth posts.
- [ ] **Step 2: Add parameterized failing tests** asserting exact expected decisions.
- [ ] **Step 3: Add protected-source test**: low-confidence match must become `needs_editorial_review`, never auto-duplicate.
- [ ] **Step 4: Implement exact/same-claim/material-update/new/review rules** with explicit `reason`, confidence, and `duplicate_of`.
- [ ] **Step 5: Run** `pytest tests/test_newsroom_decision.py -v` and confirm pass.
- [ ] **Step 6: Commit** `feat: implement event-aware newsroom decisions`.

### Task 6: Create Independent Panel Live Feed

**Files:**
- Create: `src/panel_live_feed.py`
- Create: `data/panel_live_feed.json`
- Test: `tests/test_panel_live_feed.py`

**Interfaces:**
- Produces: `LiveFeedStore(path)`, `upsert(record)`, `prune(now, freshness_hours, max_records)`, `records()`.

- [ ] **Step 1: Add failing tests** for statuses `new/auto_published/waiting/duplicate/rejected/failed`, upsert by item ID, update by event ID, freshness pruning, and record cap.
- [ ] **Step 2: Add failing test** proving an auto-published item remains visible in live feed but not pending queue.
- [ ] **Step 3: Implement atomic store** and pruning.
- [ ] **Step 4: Run tests** and confirm pass.
- [ ] **Step 5: Commit** `feat: add independent panel live feed`.

### Task 7: Build One-Cycle V2 Orchestrator

**Files:**
- Create: `src/newsroom_v2.py`
- Test: `tests/test_newsroom_v2_integration.py`

**Interfaces:**
- Produces: `run_cycle(fetcher, ledger, live_feed, editorial_store, publisher, settings, now, shadow=False) -> CycleSummary`.

- [ ] **Step 1: Add failing integration test** `fetch -> normalize -> fingerprint -> decision -> ledger -> live feed` with three independent Hormuz stories and one true duplicate.
- [ ] **Step 2: Add failing test** that `auto_publish=true` still yields non-empty live feed.
- [ ] **Step 3: Add failing test** that `needs_editorial_review` enters `editorial_queue.json` while `auto_published` does not.
- [ ] **Step 4: Add failing test** that one source exception increments `sources_failed` but does not abort other sources.
- [ ] **Step 5: Implement orchestration** with per-item trace logging and `CycleSummary` counters.
- [ ] **Step 6: Run integration tests** and confirm pass.
- [ ] **Step 7: Commit** `feat: orchestrate newsroom v2 intake and decisions`.

### Task 8: Harden Publication and Telegram Idempotency

**Files:**
- Modify: `src/newsroom_v2.py`
- Reuse/modify: existing Telegram service/publish helpers only where needed.
- Test: `tests/test_newsroom_v2_integration.py`

**Interfaces:**
- Publication must return/record Telegram `message_id` only after `ok=true`.

- [ ] **Step 1: Add failing test** where Telegram returns HTTP success but `ok=false`; event must stay retryable and feed status becomes `failed`.
- [ ] **Step 2: Add failing test** where Telegram returns `ok=true,message_id=777`; ledger stores 777 and feed becomes `auto_published`.
- [ ] **Step 3: Add failing restart test** proving published event does not send again.
- [ ] **Step 4: Implement minimal publisher integration and idempotency check** against ledger + existing published source URL/news key compatibility.
- [ ] **Step 5: Run tests** and confirm pass.
- [ ] **Step 6: Commit** `fix: verify telegram delivery before publication state`.

### Task 9: Enforce Truth Social Media Identity Rules

**Files:**
- Modify: source adapter(s) that create Trump Truth items.
- Modify: `src/newsroom_normalize.py`, `src/newsroom_decision.py` if necessary.
- Test: existing Truth tests + `tests/test_newsroom_decision.py`.

**Interfaces:**
- Truth `source_item_id` is post ID; media URL stays attached to the same item.

- [ ] **Step 1: Add failing test** for two different Truth IDs in same minute with similar “Iran’s Navy” imagery: both must be independent source items.
- [ ] **Step 2: Add failing exact-repost test** where same Truth ID is fetched twice: second is duplicate/idempotent.
- [ ] **Step 3: Add failing media test** requiring photo to reach publication payload when source post contains image.
- [ ] **Step 4: Implement source identity/media preservation** without special manual recovery workflow.
- [ ] **Step 5: Run Truth + decision tests** and confirm pass.
- [ ] **Step 6: Commit** `fix: preserve trump truth post identity and media`.

### Task 10: Integrate Live Feed With Panel Backend

**Files:**
- Modify: `src/editorial_store.py`
- Modify: `src/panel_command_file.py`
- Modify: panel backend/view files discovered by existing panel routes.
- Test: existing panel tests + new live-feed tests.

**Interfaces:**
- Panel data contract exposes three collections: `live`, `pending`, `published`.

- [ ] **Step 1: Add failing panel backend test** where queue is empty but live feed has 5 items; response/UI model must show 5 live items and 0 pending.
- [ ] **Step 2: Add failing refresh test** proving refresh updates live feed first and only queues `needs_editorial_review`/paused items.
- [ ] **Step 3: Add `GitHubEditorialStore.read_live_feed()`** and local read support without changing queue/history meaning.
- [ ] **Step 4: Update panel data assembly** to expose «ورودی زنده»، «در انتظار»، «منتشرشده».
- [ ] **Step 5: Run relevant panel tests** and confirm pass.
- [ ] **Step 6: Commit** `feat: show live newsroom intake in panel`.

### Task 11: Persist V2 State Safely Across GitHub Actions

**Files:**
- Modify: `src/persist_merge.py`
- Modify: `.github/workflows/agent.yml`
- Test: persistence/workflow tests.

**Interfaces:**
- Runtime snapshot includes `state.json`, queue/history, `event_ledger.json`, `panel_live_feed.json`.

- [ ] **Step 1: Add failing merge tests** for concurrent ledger/feed snapshots and terminal queue cleanup.
- [ ] **Step 2: Modify persist merge** so ledger events merge by `event_id/last_updated` and live feed by `item_id/updated_at`.
- [ ] **Step 3: Update workflow snapshot/copy/git-add paths** for both new JSON files.
- [ ] **Step 4: Run persistence tests and full suite**.
- [ ] **Step 5: Commit** `feat: persist newsroom v2 ledger and live feed`.

### Task 12: Add Shadow Runtime

**Files:**
- Create: `src/runtime_v2.py`
- Modify: `.github/workflows/agent.yml`
- Test: `tests/test_runtime_v2.py`

**Interfaces:**
- CLI: `python -m src.runtime_v2 --shadow` and `python -m src.runtime_v2 --monitor`.

- [ ] **Step 1: Add failing tests** verifying `--shadow` never calls Telegram sender but writes ledger/live-feed shadow decisions.
- [ ] **Step 2: Implement runtime wrapper** reusing current source fetching/settings while keeping V13 untouched.
- [ ] **Step 3: Add workflow shadow step after tests** with no Telegram publishing side effects.
- [ ] **Step 4: Run runtime tests and full suite**.
- [ ] **Step 5: Commit** `feat: run newsroom v2 in shadow mode`.

### Task 13: Production Verification Gate

**Files:**
- Add/modify verification tests/scripts only as needed.
- Do not switch production entrypoint yet.

- [ ] **Step 1: Run** `python -m pytest -q`; require all tests green.
- [ ] **Step 2: Run multiple V2 shadow cycles** and inspect logs for `sources_failed`, `new_events`, `material_updates`, duplicate references, and `panel_feed_count`.
- [ ] **Step 3: Verify regression fixture decisions** match expected outcomes with no broad `duplicate_event` reason.
- [ ] **Step 4: Verify `data/panel_live_feed.json` is non-empty when current fresh intake exists, even with `auto_publish=true`.
- [ ] **Step 5: Compare V1 vs V2 decisions** for recent production examples; document any intentionally different decisions in the PR.
- [ ] **Step 6: Commit only verification fixtures/log-format changes if required**.

### Task 14: Controlled Production Cutover

**Files:**
- Modify: `.github/workflows/agent.yml`
- Keep: `src/runtime_v13.py` unchanged and callable for rollback.

- [ ] **Step 1: Change workflow production command** from `python -m src.runtime_v13 --monitor` to `python -m src.runtime_v2 --monitor` only after Task 13 passes.
- [ ] **Step 2: Run full CI** and require green.
- [ ] **Step 3: Inspect first production job logs** for source success, event decisions, panel feed count, and zero silent suppressions.
- [ ] **Step 4: Verify one allowed real fresh story reaches Telegram and returns a concrete `message_id`.
- [ ] **Step 5: Verify same story is not republished on next cycle.
- [ ] **Step 6: Verify panel live feed contains current intake and pending is semantically separate.
- [ ] **Step 7: If any gate fails, immediately revert workflow command to `runtime_v13` without deleting V2 code.
- [ ] **Step 8: Commit** `release: switch production newsroom to v2` only after all gates pass.

### Task 15: Final Cleanup and Documentation

**Files:**
- Modify: README/ops docs if present.
- Do not remove V13 yet.

- [ ] **Step 1: Document V2 decisions, panel statuses, ledger files, shadow mode, and rollback command.
- [ ] **Step 2: Search repository for temporary/manual recovery workflows added for one-off publication and remove only those proven obsolete after V2 handles the same path.
- [ ] **Step 3: Run `python -m pytest -q` one final time.
- [ ] **Step 4: Inspect Git diff for accidental secrets, generated junk, or stale trigger files.
- [ ] **Step 5: Commit** `docs: document newsroom v2 operations and rollback`.

---

## Self-Review Results

- Spec coverage: Source intake, normalization, fingerprint, event ledger, decision engine, priority guardrails, live panel feed, editorial queue semantics, Telegram verification, Truth media, freshness, observability, panel contract, migration/shadow mode, regression tests, production gate, and rollback are each mapped to explicit tasks.
- Placeholder scan: no `TBD`, `TODO`, “implement later”, or unspecified testing steps remain.
- Type consistency: the planned pipeline consistently uses `RawNewsItem -> NormalizedNewsItem -> EventFingerprint -> DecisionResult -> EventRecord/LiveFeedRecord`, with `run_cycle(...) -> CycleSummary` as the orchestration boundary.
