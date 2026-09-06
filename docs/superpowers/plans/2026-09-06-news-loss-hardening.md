# Zero-Loss News Delivery Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent an important Iran/security story from being silently lost, permanently marked seen, or starved by an unrelated source/translation/format/send failure.

**Architecture:** Keep the existing `runtime_v10 -> v9 -> v8 -> v7 -> ... -> main` stack, but make publication transactional at the story level: only successful sends become seen/published, retryable defects remain retryable, and one bad item cannot abort the rest of a scan. Restore a current-day web-news fallback beside fresh X, improve semantic-dedup material-fact detection, harden state writes, and lock the latest native-car requirement with production-level tests.

**Tech Stack:** Python 3.12, pytest, GitHub Actions, Telegram Bot API, FxTwitter v2 timeline proxy, Google News RSS fallback.

**Spec:** User requirement on 2026-09-06: any stuck item could be the most important story; audit and eliminate news-loss bugs without weakening semantic duplicate suppression, Persian-only output, direct X links, or immediate same-scan publication.

## Global Constraints

- Every publishable story in a scan is eligible for immediate publication; no intentional holding/batching.
- Same underlying event remains deduplicated across outlets; materially new facts must survive.
- A source, detail, translation, formatter, photo, or Telegram error for one story must not permanently lose that story.
- A story is added to `news_seen` only after a successful send or a genuinely terminal editorial rejection.
- Retryable ingestion defects (`invalid_publish_time`, missing direct X link, translation/format/send failure) are never marked seen.
- Visible news text remains Persian-only.
- X photo failure falls back to text.
- Fresh X remains primary, but same-day web news is a fallback so a broken X handle cannot create a coverage hole.
- Car prices remain native Telegram text; no Telegraph/Instant View regression.
- Market schedule, holiday policy, clean `بی‌خبر` footer, and semantic dedup baseline stay unchanged.

---

### Task 1: Make news publication transactional and failure-isolated

**Files:**
- Modify: `src/main.py`
- Modify: `tests/test_main.py`
- Modify or create focused regression tests under `tests/`

**Interfaces:**
- Consumes: existing `fetch_news_items`, `_news_rejection_reason`, `_select_top_stories`, `translate_to_fa`, `fetch_news_detail`, `format_news`, `send_telegram`.
- Produces: helper classification for retryable rejections and story-level processing where `news_seen` changes only after terminal rejection or successful send.

- [ ] Add failing tests proving an empty formatted message is not marked seen and is retried later.
- [ ] Add a failing test proving a formatter failure on story A does not prevent story B from publishing in the same scan.
- [ ] Add a failing test proving a Telegram-send failure for story A does not mark A seen and does not permanently suppress B.
- [ ] Add failing tests proving `invalid_publish_time` and `missing_direct_source_link` remain retryable instead of entering `news_seen`.
- [ ] Add a failing test proving an empty/missing `news_seen` state does not silently mark the whole current scan as seen without publication.
- [ ] Implement per-story `try/continue`, explicit formatted-message validation, retryable-rejection classification, and post-send-only seen updates.
- [ ] Run the focused tests and full suite.

### Task 2: Add independent current-day web fallback for X/source outages

**Files:**
- Modify: `src/runtime_v2.py`
- Modify: `src/sources.py`
- Modify: `tests/test_expanded_x_monitoring.py`
- Add focused fallback tests under `tests/`

**Interfaces:**
- Consumes: `fetch_fresh_x_news_items`, original `sources.fetch_news_items`, `fetch_priority_news_items`, normal freshness/rejection pipeline.
- Produces: merged fresh-X + web candidate stream; semantic dedup later collapses the same event.

- [ ] Add a failing test proving web Reuters/AP/BBC candidates remain available when an X timeline source fails.
- [ ] Add a failing test proving stale web candidates are still rejected by the existing Tehran-day gate.
- [ ] Add source-specific error logging instead of silent `except: continue` in generic web fetches.
- [ ] Change runtime integration from X-only to X-primary + original web fallback.
- [ ] Re-enable priority web queries instead of replacing them with `_no_priority_web_news`.
- [ ] Verify a single source failure does not abort other sources.

### Task 3: Stop suppressing factual X posts merely because the post references video

**Files:**
- Modify: `src/fresh_x.py`
- Modify: `tests/test_fresh_x.py`

**Interfaces:**
- Consumes: parsed X text, `_VIDEO_DEPENDENT_RE`, `_PROMO_CTA_RE`.
- Produces: pure video/CTA fragments may still be rejected, but self-contained factual claims publish as text even without channel video attachment.

- [ ] Replace the existing regression expectation that every `video/footage/clip` mention is suppressed.
- [ ] Add a test where `Video shows an Iranian tanker was struck near Kharg Island` survives because the factual claim is self-contained.
- [ ] Add a test where `Watch this video` remains suppressed as promotional/non-news.
- [ ] Implement minimal factual-action detection and preserve photo extraction/fallback behavior.

### Task 4: Make semantic dedup preserve materially new operational facts

**Files:**
- Modify: `src/editorial_rules.py`
- Modify: `src/dedup_strict.py` only if needed
- Modify: `tests/test_editorial_rules.py`
- Modify/add: strict-dedup tests

**Interfaces:**
- Consumes: `_specific_facts`, `_tokens`, `is_strict_duplicate_story`.
- Produces: contextual facts for casualty counts, missile/drone/vessel counts, and key operational locations.

- [ ] Add failing tests proving the same attack with a changed casualty count is new.
- [ ] Add failing tests proving the same attack with a newly named target/location is new.
- [ ] Keep a control test proving source/wording changes without new facts remain duplicate.
- [ ] Extract only contextual material numbers/locations so years/irrelevant numbers do not defeat dedup.
- [ ] Run all duplicate-regression tests.

### Task 5: Harden state integrity against partial/corrupt writes

**Files:**
- Modify: `src/services.py`
- Modify: `tests/test_services.py` or add state-integrity tests

**Interfaces:**
- Consumes: `load_state(path)`, `save_state(state, path)`.
- Produces: atomic temp-file + `os.replace` persistence and graceful recovery/defaults on malformed JSON.

- [ ] Add a failing test proving malformed `state.json` does not crash the entire news runner.
- [ ] Add a failing test proving `save_state` uses an atomic replacement path and leaves valid JSON.
- [ ] Implement safe defaults on `JSONDecodeError`/`OSError` with an explicit stderr warning.
- [ ] Implement atomic state writes with flush/fsync/replace.
- [ ] Verify state behavior under existing workflow tests.

### Task 6: Lock production regressions and observability

**Files:**
- Modify: `src/runtime_v9.py`
- Modify: `tests/test_car_runtime_telegraph.py`
- Modify/add: production policy tests

**Interfaces:**
- Consumes: production installer in `runtime_v9` and `runtime_v10`.
- Produces: native Telegram car formatter and explicit fatal-news-pipeline logging.

- [ ] Add/restore a production test proving `runtime_v9` installs `_format_car_for_telegram`, not `_format_car_via_telegraph`.
- [ ] Add a test proving native car output contains no `telegra.ph` URL.
- [ ] Restore native car production formatter and normal daily due policy without old one-off Telegraph republish paths controlling production.
- [ ] Add an unmistakable `NEWS_PIPELINE_FATAL` log/return path for a total news-pipeline exception so CI cannot look healthy while news is dead.
- [ ] Preserve non-news tasks where safe, but make workflow outcome nonzero for a total newsroom failure.

### Task 7: Verification and production rollout

**Files:**
- No new production files unless a test fixture is required.

- [ ] Run full pytest on the hardening branch.
- [ ] Re-run the critical transactional/dedup/source tests repeatedly to catch state/order leakage.
- [ ] Compare branch against main and review for baseline regressions: Persian-only, semantic dedup, current-day freshness, clean footer, X photo fallback, market hours/holiday, native cars.
- [ ] Merge only after all tests are green.
- [ ] Observe one full production `runtime_v10 --monitor` session and inspect logs for source failures, fatal pipeline errors, incorrect low-value suppression, and Telegram send failures.
- [ ] Confirm production workflow success and persisted runtime state.