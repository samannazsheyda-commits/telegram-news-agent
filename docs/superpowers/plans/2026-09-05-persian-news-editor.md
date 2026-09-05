# Persian News Editor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic Persian newsroom editor that produces complete, natural, source-faithful Persian news, blocks junk/promos and duplicates, and formats emojis only on the final line.

**Architecture:** Introduce a pure `persian_editor` module between raw source acquisition and final selection/formatting. Existing runtime and source parsers call it; it fails closed when meaning preservation is uncertain. Formatting becomes presentation-only and dedup remains claim/event based rather than broad-topic based.

**Tech Stack:** Python 3.12, pytest, requests, BeautifulSoup, existing GitHub Actions runtime.

**Spec:** `docs/superpowers/specs/2026-09-05-persian-news-editor-design.md`

## Global Constraints
- No invented facts.
- No incomplete final sentences.
- Final visible headline/body must be Persian-script newsroom prose.
- Telegram labels use «تلگرام».
- Ordinary news has no leading neutral-circle marker.
- Country/topic emojis appear only on the last line.
- Dedup must remove same claims across outlets/runs without suppressing distinct developments.

---

### Task 1: Pure Persian editor core

**Files:**
- Create: `src/persian_editor.py`
- Create: `tests/test_persian_editor.py`

**Interfaces:**
- Produces: `edit_news_text(source_text: str, translated_text: str) -> str`
- Produces: `trim_to_complete_sentences(text: str, max_chars: int | None = None) -> str`
- Produces: `is_promotional_news_text(text: str) -> bool`
- Produces: `strip_leading_decorative_emoji(text: str) -> str`
- Produces: `has_forbidden_latin_body(text: str) -> bool`

- [ ] Write failing tests for incomplete Bolton sentence, FT promo language, leading emoji removal, Persian punctuation normalization, Latin-word rejection, and shipping phrase repair.
- [ ] Run `python -m pytest -q tests/test_persian_editor.py` and confirm RED.
- [ ] Implement minimal pure transformations. Protect numbers, negation, quoted attribution, and modal words; if protected facts are lost, return empty string.
- [ ] Run focused tests to GREEN.
- [ ] Commit `feat: add Persian newsroom editor core`.

### Task 2: Telegram source integrity

**Files:**
- Modify: `src/custom_sources.py`
- Modify: `tests/test_custom_sources.py`
- Modify: `tests/test_telegram_complete_sentence.py`

**Interfaces:**
- Consumes `trim_to_complete_sentences` and `strip_leading_decorative_emoji`.
- Telegram `NewsItem.source` becomes `"<name> / تلگرام"`.
- Telegram `NewsItem.title` must never end with an artificial `...` fragment.

- [ ] Add failing regression tests for Bolton long quote and Persian source label.
- [ ] Run focused tests and confirm RED.
- [ ] Replace 240-character blind truncation with sentence-aware trimming; preserve full summary for downstream editing.
- [ ] Run focused tests to GREEN.
- [ ] Commit `fix: keep Telegram news complete and Persian-labelled`.

### Task 3: Runtime editorial integration

**Files:**
- Modify: `src/runtime_v7.py`
- Modify: `tests/test_easy_news_flow.py`
- Create: `tests/test_persian_editor_runtime.py`

**Interfaces:**
- Runtime calls `edit_news_text(raw, translated)` before candidate selection and formatting.
- Empty edit result means withhold item.
- Promotional X posts remain rejected before publication.

- [ ] Add failing tests showing a real Iran security item passes, FT festival promo fails, Bolton fragment is removed/withheld, and literal shipping wording is repaired.
- [ ] Run focused runtime tests and confirm RED.
- [ ] Integrate editor into translation cache/selection path without changing source facts.
- [ ] Run focused tests to GREEN.
- [ ] Commit `feat: run Persian editor before publication`.

### Task 4: Persian-only presentation and bottom-only emojis

**Files:**
- Modify: `src/formatters.py`
- Modify: `src/runtime_v7.py`
- Create: `tests/test_news_presentation_policy.py`

**Interfaces:**
- Ordinary `format_news` output begins with `<b>source: headline</b>` and no `⚪️`.
- Critical/notam markers are explicit policy exceptions.
- `_format_news_with_footer_icons` appends all flags/topic icons to the final line only.

- [ ] Add failing tests for no leading neutral marker, no source emoji in headline, `تلگرام` label, and a single final emoji line.
- [ ] Run focused tests and confirm RED.
- [ ] Implement formatter changes and source-label normalization.
- [ ] Run focused tests to GREEN.
- [ ] Commit `fix: standardize Persian newsroom presentation`.

### Task 5: Dedup safety regression suite

**Files:**
- Modify: `tests/test_cross_run_dedup.py`
- Modify: `tests/test_dedup_strict.py`
- Modify: `src/editorial_rules.py` only if tests expose a remaining defect.

**Interfaces:**
- Same quote/claim across France24, ABC, NBC -> duplicate.
- Distinct Israel attack-preparation, IAEA resolution, Netanyahu statement -> not duplicates solely due to common Iran/US/war vocabulary.

- [ ] Add paired duplicate/non-duplicate fixtures.
- [ ] Run focused tests and confirm current behavior.
- [ ] If RED, make smallest rule change needed; avoid broad semantic topic keys.
- [ ] Run focused tests to GREEN.
- [ ] Commit `test: harden claim-level dedup boundaries` or `fix: harden claim-level dedup boundaries`.

### Task 6: Full verification and production merge

**Files:**
- No new files unless a regression is discovered.

- [ ] Run `python -m pytest -q` and require zero failures.
- [ ] Run workflow on feature branch or open PR and verify GitHub Actions tests.
- [ ] Review representative generated cards for Telegram source, X source, critical security news, and ordinary news.
- [ ] Merge/update `main` only after verification.
- [ ] Verify the first production workflow run: tests success, monitor success, persistence success.
- [ ] Report exact run number and any remaining limitations; do not claim perfection without evidence.
