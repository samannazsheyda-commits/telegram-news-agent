# AI Newsroom Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add semantic 72-hour event dedup, an AI senior editor, a Hugging Face translation stage, and a source-aware Persian editor before automatic Telegram publication.

**Architecture:** Keep existing deterministic freshness/fingerprint/eligibility checks as the cheap first layer. Add a focused Hugging Face client module, a senior-editor gate invoked from `newsroom_v2.run_cycle`, and an AI-backed translation/editor path invoked by the strict publisher. Use remote inference so the VPS does not load multi-gigabyte model weights.

**Tech Stack:** Python 3.12, `requests`, Hugging Face Inference Providers, BAAI/bge-m3, Qwen/Qwen3-4B-Instruct-2507, optional dedicated MADLAD-400 endpoint, pytest.

**Spec:** `docs/superpowers/specs/2026-09-11-ai-newsroom-pipeline-design.md`

## Global Constraints

- Event memory is 72 hours.
- AI newsroom never edits/deletes already-published Telegram posts.
- Auto-publication fails closed in `required` mode.
- No model weights are downloaded to the VPS.
- No Hugging Face token is committed to Git.
- Original source facts, actors, numbers, locations, and direction of action must be preserved.
- Existing hard news priority and hourly critical-bypass logic remains intact.

---

### Task 1: Hugging Face AI client

**Files:**
- Create: `src/ai_newsroom.py`
- Test: `tests/test_ai_newsroom.py`

**Interfaces:**
- Produces `AIConfig.from_env()`.
- Produces `HuggingFaceNewsAI.embed_texts(texts) -> list[list[float]]`.
- Produces `HuggingFaceNewsAI.judge_relation(new_text, prior_text) -> RelationDecision`.
- Produces `HuggingFaceNewsAI.score_story(source_text) -> EditorialDecision`.
- Produces `HuggingFaceNewsAI.translate_to_fa(source_text) -> TranslationDraft`.
- Produces `HuggingFaceNewsAI.edit_persian(source_text, draft_text) -> PersianEditDecision`.

- [ ] **Step 1: Write failing tests**

Tests cover environment parsing, BGE response parsing, Qwen JSON-only parsing, malformed JSON failure, MADLAD endpoint parsing, Qwen translation fallback, and deterministic cosine similarity.

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest tests/test_ai_newsroom.py -q`
Expected: FAIL because `src.ai_newsroom` does not exist.

- [ ] **Step 3: Implement minimal client**

Use `requests.Session` with `Authorization: Bearer <HF_TOKEN>` and bounded timeouts. Chat calls use `https://router.huggingface.co/v1/chat/completions`. BGE uses `https://router.huggingface.co/hf-inference/models/BAAI/bge-m3/pipeline/feature-extraction`. MADLAD uses only `HF_MADLAD_ENDPOINT` because the shared provider does not currently serve that model. Qwen translation is the configured fallback.

- [ ] **Step 4: Run focused tests**

Run: `python -m pytest tests/test_ai_newsroom.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

Commit message: `feat: add Hugging Face newsroom AI client`

### Task 2: 72-hour semantic duplicate and senior-editor gate

**Files:**
- Modify: `src/event_ledger.py`
- Modify: `src/newsroom_v2.py`
- Modify: `src/newsroom_runtime_v2.py`
- Test: `tests/test_ai_newsroom_pipeline.py`

**Interfaces:**
- Add `EventLedger.recent_records(now, hours=72) -> list[EventRecord]`.
- Extend `run_cycle(..., ai=None)` with an optional AI collaborator.
- AI decision reasons are recorded in live feed/review queue; Telegram publication still flows through the existing publisher.

- [ ] **Step 1: Write failing integration tests**

Tests prove: cross-source paraphrase is suppressed; a material update is not suppressed; a routine diplomatic call is review-only; a critical missile event survives the AI gate; AI outage in required mode routes to review; the 72-hour cutoff excludes older events.

- [ ] **Step 2: Run integration tests and verify RED**

Run: `python -m pytest tests/test_ai_newsroom_pipeline.py -q`
Expected: FAIL because the AI gate is not wired.

- [ ] **Step 3: Implement recent-event retrieval and AI gate**

Run existing exact/deterministic dedup first. For candidates from the previous 72 hours, compare embeddings and call Qwen relation judge only for the closest event above the configured similarity threshold. Then call the senior editor. `publish=false`, malformed output, or AI failure in required mode routes the item to review without Telegram writes.

- [ ] **Step 4: Run focused and existing newsroom tests**

Run: `python -m pytest tests/test_ai_newsroom_pipeline.py tests/test_news_quality_regressions.py tests/test_user_reported_news_quality_0911.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

Commit message: `feat: add semantic senior editor gate`

### Task 3: AI translator and Persian editor in strict publisher

**Files:**
- Modify: `src/strict_translation.py`
- Modify: `src/newsroom_publisher.py`
- Modify: `src/persian_editor.py`
- Test: `tests/test_ai_translation_editor.py`

**Interfaces:**
- `StrictTelegramNewsroomPublisher(..., ai=None, ai_mode="optional")`.
- In AI mode, title and summary translation call `ai.translate_to_fa`, then `ai.edit_persian`, then deterministic validation.
- Legacy Google translation remains only when AI mode is off/optional without credentials.

- [ ] **Step 1: Write failing regression tests**

Tests use the user-reported AP/Mokha sentence and require natural Persian such as `فرودگاه المخا را هدف حملات هوایی قرار داده است`; reject `حملات هوایی ... زده است`; reject changed numbers/names; reject `faithful=false`; never send Telegram if editor fails.

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest tests/test_ai_translation_editor.py -q`
Expected: FAIL because AI editor is not connected.

- [ ] **Step 3: Implement source-aware translation/editing**

MADLAD endpoint is preferred when configured. Qwen translation is fallback. The Qwen Persian editor sees both original English and draft Persian and returns JSON `{text, faithful, natural, reason}`. The deterministic layer still applies glossary/number/critical-term checks before formatting.

- [ ] **Step 4: Run focused translation tests**

Run: `python -m pytest tests/test_ai_translation_editor.py tests/test_strict_translation.py tests/test_persian_editor.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

Commit message: `feat: add AI Persian translation and editing gate`

### Task 4: Runtime configuration, deploy example, and full verification

**Files:**
- Modify: `deploy/agent.env.example`
- Modify: `src/newsroom_runtime_v2.py`
- Test: existing full suite

**Interfaces:**
- Runtime constructs `HuggingFaceNewsAI` only when `HF_TOKEN` is set and AI mode is not off.
- `AI_NEWSROOM_MODE=required` requires successful AI decisions before auto-publish.

- [ ] **Step 1: Add configuration tests**

Verify defaults: event memory 72 hours, duplicate threshold 0.87, importance threshold 70, and optional rollout mode.

- [ ] **Step 2: Update deploy environment example**

Document `AI_NEWSROOM_MODE`, `HF_TOKEN`, model IDs, `HF_MADLAD_ENDPOINT`, thresholds, and 72-hour memory.

- [ ] **Step 3: Run full regression suite**

Run: `python -m pytest -q`
Expected: all tests pass with no network calls.

- [ ] **Step 4: Open PR and wait for both repository checks**

Do not merge while any required check is pending/failing.

- [ ] **Step 5: Merge, verify main CI, and exact production promotion**

Verify `production` points to the exact tested main SHA before claiming deployment.

- [ ] **Step 6: Credential activation**

The code can merge without secrets. Actual Hugging Face inference requires `HF_TOKEN` in `/etc/bikhabar/agent.env`; MADLAD primary translation additionally requires a deployed `HF_MADLAD_ENDPOINT`. Until credentials are present, optional mode keeps legacy publishing available and emits degraded-mode logs.
