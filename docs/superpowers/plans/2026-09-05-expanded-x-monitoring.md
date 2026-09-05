# Expanded X Monitoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand «بی‌خبر» X monitoring for Iran/security coverage, harden cross-source semantic deduplication, add Persian source labels and country flags, and add global crude-oil tracking without removing existing utilities.

**Architecture:** Keep the existing X-only newsroom runtime and special monitoring paths. Expand `newsroom_x.py` as the account/topic registry, strengthen `editorial_rules.py` for event-level deduplication, add output/market wrappers in `runtime_v2.py`, and isolate Brent/WTI retrieval in `oil.py`.

**Tech Stack:** Python 3.12, requests, pytest, GitHub Actions.

**Spec:** approved in chat on 2026-09-05.

## Global Constraints

- Newsroom media monitoring remains X-only; generic website-news feeds stay disabled.
- Only Iran/security-relevant X posts may publish.
- Iranian commentators are excluded; Tasnim is included as a newsroom.
- Existing markets, weather, NOTAM, Hormuz, car prices and special sources remain enabled.
- Same event from multiple outlets must publish once even when paraphrased.
- Materially new facts can pass as a genuine update.
- Every monitored X source is rendered with a Persian display name.
- News includes flags for countries materially involved in the story.
- `👉🏻` appears before the clickable «بی‌خبر» footer.
- Brent and WTI appear in the market block and daily change summary when reliable data is available; missing oil data is never invented.

---

### Task 1: Expand X sources and topic vocabulary

**Files:**
- Modify: `src/newsroom_x.py`
- Test: `tests/test_expanded_x_monitoring.py`

- [x] Add required global media, Israeli channels/officials, US officials and foreign analysts/reporters.
- [x] Exclude Iranian commentators and retain Tasnim as an Iranian newsroom.
- [x] Add naval, Hormuz, base, nuclear, sanctions and frozen-funds vocabulary.
- [x] Add Persian display names for all monitored X sources.

### Task 2: Harden semantic event deduplication

**Files:**
- Modify: `src/editorial_rules.py`
- Test: `tests/test_expanded_x_monitoring.py`

- [x] Canonicalize outlet-independent wording and entity aliases.
- [x] Suppress paraphrases of the same claim/event across outlets.
- [x] Preserve updates with materially new time/day/site facts.

### Task 3: Add country flags and follow cue

**Files:**
- Modify: `src/runtime_v2.py`
- Test: `tests/test_expanded_x_monitoring.py`

- [x] Infer involved-country flags from original and Persian story text.
- [x] Add `👉🏻` before the clickable «بی‌خبر» footer.

### Task 4: Add global crude-oil tracking

**Files:**
- Create: `src/oil.py`
- Modify: `src/runtime_v2.py`
- Test: `tests/test_expanded_x_monitoring.py`

- [x] Fetch Brent and WTI benchmark prices in USD/barrel on a best-effort basis.
- [x] Add current benchmark prices to the regular market output.
- [x] Record first/last daily prices and report amount/percentage change in daily summary.
- [x] Skip unavailable benchmark values without fabricating data.

### Task 5: Full verification and merge

- [x] Run focused regression tests successfully.
- [x] Run full `python -m pytest -q` successfully in GitHub Actions.
- [x] Remove temporary branch-only CI workflow.
- [ ] Open PR, inspect changed files, merge to `main`, and verify production workflow.
