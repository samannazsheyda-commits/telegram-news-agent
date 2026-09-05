# Persian News Editor Design

## Goal
Add a deterministic Persian editorial layer that turns source text into clean, complete, newsroom-style Persian without changing factual meaning, while preserving strong filtering, cross-source deduplication, Persian-only presentation, and bottom-only topic emojis.

## Editorial contract
1. Never invent a fact, number, actor, location, quote, or causal claim.
2. Prefer complete source text. If a source item is truncated, publish only complete sentences; never end on a fragment.
3. Remove promotional calls-to-action, event plugs, podcast/video invitations, newsletter language, and other non-news boilerplate.
4. Keep newsworthy facts even when wording is cautious (may, could, considering) if the source is credible and the statement itself is news.
5. Reject pure commentary, opinion, generic discussion, and promotional interviews unless they contain a concrete new factual statement relevant to Iran.
6. Normalize Persian spelling, punctuation, spacing, half-spaces, common proper-name spellings, and idiomatic Persian. Avoid literal Google-Translate phrasing.
7. Do not allow visible Latin-script words in the final headline/body except unavoidable source links; known acronyms and names must be rendered in Persian where a conventional form exists.
8. Preserve quotes semantically. Paraphrase only for grammar/clarity, never to strengthen or soften the original claim.
9. Deduplicate by event/claim across outlets and across runs. A later story with only extra wording is not a new post; a genuinely new development is.
10. Telegram source labels must use «تلگرام», never «Telegram».
11. No neutral circle marker at the start of ordinary headlines. Critical/security markers may remain only where explicitly warranted by policy.
12. Country flags and topic emojis must appear only on the final line of the post.
13. Source-provided leading emoji sequences are stripped from the headline/body and re-derived from the normalized news content for the bottom metadata line.

## Pipeline
source fetch -> source cleanup -> factual sentence extraction -> translation -> Persian editing -> fidelity validation -> editorial relevance gate -> cross-run dedup -> formatting -> optional X image attachment -> Telegram publish

## Components
### `src/persian_editor.py`
Pure functions for source cleanup, complete-sentence trimming, Persian normalization, literal-translation repair, Latin-token cleanup, promotional-text detection, and final fidelity-safe editing.

### `src/editorial_rules.py`
Keeps event importance/relevance and duplicate-event logic. The new editor feeds normalized text into these rules; dedup must not collapse distinct developments merely because they share Iran/US/war vocabulary.

### `src/runtime_v7.py`
Orchestrates the editor before selection and formatting. It must withhold any item whose edited text is empty, incomplete, non-Persian, or fails fidelity checks.

### `src/custom_sources.py`
Telegram parser preserves full source text, trims only to complete sentences when needed, labels sources with «تلگرام», and removes source-leading emoji noise before editorial processing.

### `src/fresh_x.py`
Keeps direct X source acquisition. Promotional event/session posts remain rejected. Media metadata may be exposed for image attachment where available.

### Formatting
Normal news cards start directly with the Persian source label and headline. Topic icons and flags are appended once, on the last line only. Links and timestamps remain above that final emoji line.

## Fidelity validation
The editor is fail-closed. If a transformation cannot confidently preserve the source claim, return an empty result so the item is withheld rather than guessed. Numbers, named entities, negation, attribution, and modal strength are protected fields and must survive editing.

## Testing
Regression fixtures must cover:
- FT festival promo rejected while real FT breaking news passes.
- Bolton Telegram quote never ends mid-sentence.
- «above the Strait of Hormuz» is not rendered as «بالای تنگه هرمز» in shipping context.
- `Telegram` becomes «تلگرام» in source labels.
- leading source emojis are removed from headline and appear only on bottom metadata line.
- ordinary news has no leading ⚪️ marker.
- no visible Latin words remain in Persian headline/body.
- same Trump quote from France24/ABC/NBC publishes once across runs.
- distinct Iran developments are not falsely deduplicated.
- numbers, attribution and negation remain unchanged through editing.
