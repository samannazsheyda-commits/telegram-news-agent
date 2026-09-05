# Expanded X Monitoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand «بی‌خبر» X monitoring for Iran/security coverage, harden cross-source semantic deduplication, and add country flags plus a follow arrow to every news item while preserving market/weather/NOTAM/Hormuz/car services.

**Architecture:** Extend the existing `newsroom_x.py` source registry and topic query; keep `runtime_v2.py` as the X-only newsroom gate. Strengthen story canonicalization in editorial dedup so paraphrases from different sources collapse to one event. Add presentation-only country-flag inference and footer arrow in `formatters.py`.

**Tech Stack:** Python 3.12, requests, pytest, GitHub Actions.

**Spec:** approved in chat on 2026-09-05.

## Global Constraints

- Newsroom media monitoring remains X-only; no generic website-news feeds are reintroduced.
- Only Iran/security-relevant X posts may publish.
- Iranian commentators are excluded; Tasnim is included as a news source.
- Existing special sources and market/weather/NOTAM/Hormuz/car features remain enabled.
- Same event from multiple outlets must publish once even if paraphrased.

---

### Task 1: Expand X sources and topic vocabulary

**Files:**
- Modify: `src/newsroom_x.py`
- Test: `tests/test_x_priority_sources.py`

- [ ] Add failing tests for required official/media/analyst handles and naval/nuclear/sanctions vocabulary.
- [ ] Run focused tests and confirm failure.
- [ ] Add verified handles and expanded query terms; exclude Iranian commentators.
- [ ] Run focused tests and confirm pass.

### Task 2: Harden semantic event deduplication

**Files:**
- Modify: `src/editorial_rules.py`
- Test: `tests/test_editorial_rules.py`

- [ ] Add failing tests showing Israel Katz/France24/AP paraphrases are duplicates while materially new facts remain distinct.
- [ ] Run focused tests and confirm failure.
- [ ] Normalize attribution/synonym noise and compare event anchors/entities more strongly.
- [ ] Run focused tests and confirm pass.

### Task 3: Add country flags and follow arrow

**Files:**
- Modify: `src/formatters.py`
- Test: `tests/test_formatters.py`

- [ ] Add failing tests for Iran/Israel/US flags and `👉🏻` before the «بی‌خبر» channel link.
- [ ] Run focused tests and confirm failure.
- [ ] Add deterministic country inference from title/summary and update the footer.
- [ ] Run focused tests and confirm pass.

### Task 4: Full verification and merge

- [ ] Run `python -m pytest -q` in GitHub Actions.
- [ ] Confirm all tests pass.
- [ ] Remove temporary branch-only CI workflow if used.
- [ ] Open PR, inspect changed files, and merge to `main`.
