# News Pipeline Reliability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop credible Iran news from disappearing silently, preserve a human-readable rejection audit, and make risky idiom repair preserve the original subject and object.

**Architecture:** Replace the single boolean news eligibility gate with a reasoned classification that separates publishable stories from terminal rejects and low-signal rejects. Persist compact rejection records in `state.json` for later inspection. Keep semantic duplicate suppression unchanged. Repair `walked back` at phrase level instead of inserting a whole duplicated object phrase.

**Tech Stack:** Python 3.12, pytest, GitHub Actions, Telegram Bot API.

**Spec:** Current conversation requirements for `@bikhabaar`.

## Global Constraints

- Iran-related news only, except market/weather/car scheduled posts.
- Approved major sources may publish factual Iran reports even when a fixed event keyword is absent.
- Analysis/opinion/SEO/bundled/old/undated items remain blocked.
- Every rejected story must be inspectable by source, title, key, published time, and rejection reason.
- No source-backed detail may be invented.
- Existing duplicate suppression and Trump distinct-statement behavior remain intact.

---

### Task 1: Reasoned news eligibility and rejection audit

**Files:**
- Modify: `src/main.py`
- Test: `tests/test_news_pipeline_regressions.py`

**Interfaces:**
- Produces: `_news_eligibility(item: NewsItem, now: datetime) -> tuple[bool, str]`
- Produces: `_record_news_rejection(state: dict, item: NewsItem, reason: str) -> bool`

- [x] **Step 1: Write failing tests** for trusted factual NYT coverage and rejection audit records.
- [x] **Step 2: Run tests to verify RED**. Expected failures: trusted report not sent; `news_rejections` absent.
- [ ] **Step 3: Implement minimal classification and audit persistence**.
- [ ] **Step 4: Run full pytest and verify GREEN**.

### Task 2: Safe idiom repair

**Files:**
- Modify: `src/services.py`
- Test: `tests/test_idiom_regressions.py`

**Interfaces:**
- Keeps: `translate_to_fa(text, session=requests) -> str`

- [x] **Step 1: Write failing regression test** for `walked back` object duplication and subject preservation.
- [x] **Step 2: Run tests to verify RED**. Expected failure: duplicated `اظهارات قبلی خود`.
- [ ] **Step 3: Replace the literal whole fragment with a context-preserving phrase repair**.
- [ ] **Step 4: Run full pytest and verify GREEN**.

### Task 3: Automatic verification on code changes

**Files:**
- Modify: `.github/workflows/agent.yml`

**Interfaces:**
- Pushes touching `src/**`, `tests/**`, requirements, or the workflow trigger CI.
- `state.json` bot commits do not trigger push CI.

- [x] **Step 1: Add a scoped `push` trigger**.
- [x] **Step 2: Confirm a push run starts on the test commit head**.
- [ ] **Step 3: Confirm the final production head passes the full workflow**.
