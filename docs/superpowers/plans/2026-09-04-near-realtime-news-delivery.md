# Near-Realtime News Delivery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver newly discoverable important Iran-related news close to source visibility while keeping market cadence unchanged and making posts slightly more complete.

**Architecture:** Keep the existing one-iteration `run()` behavior as the unit of work, add a bounded monitor loop that invokes it roughly once per minute, and run that loop in overlapping-resistant GitHub Actions sessions. Remove the per-run eight-story throttle so each poll can send every newly eligible story while preserving duplicate and quality filters. Formatting remains headline plus at most one non-redundant detail sentence.

**Tech Stack:** Python 3.12, pytest, GitHub Actions, Telegram Bot API, RSS/Google News polling.

**Spec:** `docs/superpowers/specs/2026-09-04-near-realtime-news-delivery-design.md`

## Global Constraints

- Poll target: about 60 seconds while the runtime is alive.
- Same-day Tehran freshness remains required.
- Important-news-only, approved-source and duplicate rules remain.
- Military/security events stay highest priority.
- Market remains every 2 hours and suppressed 00:00–07:59 Tehran.
- Truth Social stays Iran-related only; X monitors remain best-effort public indexing.
- Telegram send failures must not mark an item delivered.
- Manual workflow dispatch remains available.

---

### Task 1: Polling iteration and no batch cap

**Files:**
- Modify: `src/main.py`
- Test: `tests/test_main.py`

**Interfaces:**
- Consumes: existing `run(now: datetime | None) -> int`
- Produces: `monitor_loop(poll_seconds: int = 60, session_seconds: int = 210) -> int`

- [ ] Add failing tests proving a new story on a second iteration is sent and that more than eight newly eligible stories are not held back.
- [ ] Run the focused tests and observe failure.
- [ ] Remove the `MAX_NEWS_PER_RUN` throttle from the send path and add the bounded polling loop.
- [ ] Re-run focused tests and then the full suite.

### Task 2: Slightly richer normal-news output

**Files:**
- Modify: `src/formatters.py`
- Test: `tests/test_formatters.py`

**Interfaces:**
- Consumes: `format_news(...)`
- Produces: headline plus at most one useful non-redundant summary sentence.

- [ ] Add/retain regression tests for one useful detail sentence, at-most-one sentence, and redundant-summary omission.
- [ ] Ensure formatting uses the first useful summary sentence without inventing context.
- [ ] Run formatter tests and full suite.

### Task 3: Bounded near-realtime GitHub Actions session

**Files:**
- Modify: `.github/workflows/agent.yml`
- Test: `tests/test_workflow.py`

**Interfaces:**
- Consumes: `python -m src.main --monitor`
- Produces: a short-lived monitor session restarted by cron, with manual dispatch preserved.

- [ ] Add a workflow regression test checking `workflow_dispatch`, monitor mode and session timeout configuration.
- [ ] Run the focused test and observe failure.
- [ ] Change the workflow to start frequently, run the monitor loop for a bounded session, and use concurrency to avoid overlapping sessions.
- [ ] Run full tests.

### Task 4: Final verification

**Files:**
- No code changes unless verification exposes a defect.

- [ ] Run `python -m pytest -q` in CI.
- [ ] Confirm workflow job reaches tests, agent execution, and state persistence successfully.
- [ ] Only then report completion.
