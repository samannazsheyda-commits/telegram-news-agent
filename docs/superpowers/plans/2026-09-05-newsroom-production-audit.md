# Newsroom Production Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the Iran-news Telegram agent so only current, Iran-related, Persian, source-linked news is published, one successful item per monitor cycle, without stale-item or translation-failure starvation, while protecting production state from tests.

**Architecture:** Keep the existing X-first runtime stack, but move rate limiting to a successful-send guard in `src/main.py`, let `runtime_v7` return the full eligible queue, and restore same-day freshness for X. Add last-mile output checks and isolate test/runtime state so CI cannot mutate production state.

**Tech Stack:** Python 3.12, pytest, GitHub Actions, Telegram Bot API, FxTwitter v2 timeline proxy.

**Spec:** User-approved newsroom behavior in the active conversation.

## Global Constraints

- Newsroom remains Iran-only.
- X items require direct `x.com/.../status/...` source links.
- Foreign-language bodies never publish when translation fails.
- Distinct X status IDs are not semantically deduplicated; exact previously-seen posts remain blocked.
- At most one successfully published news item per monitor cycle.
- A failed translation or formatter must not block later eligible items in the same cycle.
- X posts must be current Tehran-local day, with existing post-midnight grace.
- Production state must never be mutated by tests.

---

### Task 1: Add regression tests for stale X, successful-send limiting, and state isolation

**Files:**
- Modify: `tests/test_easy_news_flow.py`
- Modify: `tests/test_main.py`
- Modify: `tests/test_workflow.py`
- Modify: `tests/conftest.py`

- [ ] Add a test proving an old X post is rejected with `not_today_tehran`.
- [ ] Add a test proving one translation failure does not prevent a later eligible story from being sent in the same run.
- [ ] Add a test proving only one successful news item is sent per cycle.
- [ ] Add workflow assertions that runtime state is restored after tests and persisted only when the monitor step ran.
- [ ] Isolate `STATE_PATH` and editorial queue/history to temporary paths for every test.

### Task 2: Harden newsroom freshness and queue behavior

**Files:**
- Modify: `src/runtime_v7.py`
- Modify: `src/main.py`

- [ ] Restore timestamp validity and Tehran-day freshness checks for X items.
- [ ] Replace one-item selector with deterministic newest-first queue ordering while preserving distinct X posts.
- [ ] Add a runtime-configurable successful-news-per-cycle limit and set it to 1 in runtime v7.
- [ ] Continue past translation/formatting failures until one story is actually sent.
- [ ] Never mark an empty/invalid formatted message as seen.

### Task 3: Protect production state in CI

**Files:**
- Modify: `.github/workflows/agent.yml`
- Modify: `tests/test_workflow.py`

- [ ] Give the monitor step an id.
- [ ] Restore tracked runtime-state files after pytest and before starting the monitor.
- [ ] Persist runtime data only when the monitor step actually executed.
- [ ] Preserve seven-minute timeout, 60-second polling, and 240-second session.

### Task 4: Verification stress pass

**Files:**
- Create temporarily: `.github/workflows/audit-ci.yml`

- [ ] Run the full test suite.
- [ ] Run critical newsroom tests 10 consecutive times to catch state/order leakage.
- [ ] Verify no live Telegram publishing occurs in audit CI.
- [ ] Remove temporary audit workflow after a green run.
- [ ] Merge only after the production workflow is green and the monitor step starts.