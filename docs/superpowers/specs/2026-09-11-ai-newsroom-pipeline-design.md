# AI Newsroom Pipeline Design

## Goal

Replace the fragile rule-only path for automatic Telegram publishing with a fail-closed newsroom pipeline that understands event similarity, editorial importance, translation quality, and Persian news style before anything reaches the public channel.

## Scope

This change adds three AI-backed stages to the existing Newsroom V2 path:

1. **Senior editor / event gate** — semantic duplicate detection plus editorial importance scoring.
2. **Translator** — English-to-Persian translation using MADLAD-400 when a dedicated endpoint is configured; Qwen translation is the operational fallback because `google/madlad400-3b-mt` is not currently served by Hugging Face shared Inference Providers.
3. **Persian editor / fact-preserving validator** — Qwen rewrites the translation into natural Persian news copy while preserving the source facts; deterministic validation rejects unsafe output.

The existing fingerprint/rule system remains as the first cheap filter and as a safety layer. AI does not replace source freshness, URL dedup, event ledger, Telegram publication accounting, or hard breaking-news priority rules.

## Deployment model

The VPS remains lightweight. Large model weights are **not downloaded to the VPS**.

- Hugging Face Inference Providers are called over HTTPS using `HF_TOKEN`.
- `BAAI/bge-m3` is used through HF Inference for embeddings.
- `Qwen/Qwen3-4B-Instruct-2507` is used through the Hugging Face OpenAI-compatible router for senior-editor and Persian-editor decisions.
- MADLAD is called through `HF_MADLAD_ENDPOINT` when available. This endpoint must expose `google/madlad400-3b-mt` or a compatible deployment. The input is prefixed with `<2fa>`.
- If `HF_MADLAD_ENDPOINT` is absent but `HF_TOKEN` is available, Qwen performs the translation step and the runtime records `translator=qwen_fallback`.
- If AI newsroom mode is `required` and the required AI service is unavailable or returns invalid output, automatic publication fails closed and the item is sent to review instead of Telegram.

## Configuration

Environment variables:

- `AI_NEWSROOM_MODE=off|optional|required` — default `optional` during rollout.
- `HF_TOKEN` — Hugging Face token with Inference Providers permission.
- `HF_EMBEDDING_MODEL=BAAI/bge-m3`
- `HF_EDITORIAL_MODEL=Qwen/Qwen3-4B-Instruct-2507:fastest`
- `HF_PERSIAN_EDITOR_MODEL=Qwen/Qwen3-4B-Instruct-2507:fastest`
- `HF_TRANSLATION_MODEL=google/madlad400-3b-mt`
- `HF_MADLAD_ENDPOINT=` — optional dedicated MADLAD endpoint.
- `AI_EVENT_MEMORY_HOURS=72`
- `AI_DUPLICATE_THRESHOLD=0.87`
- `AI_IMPORTANCE_THRESHOLD=70`

No token or endpoint is committed to GitHub.

## Data flow

For each fresh normalized item:

1. Existing exact URL dedup and deterministic fingerprint candidate search run first.
2. Candidate events are limited to the last **72 hours**.
3. If `HF_TOKEN` is available, BGE-M3 embeds the incoming item and candidate canonical event texts. Cosine similarity identifies semantically related events even when sources paraphrase the story.
4. If similarity is above the duplicate threshold, Qwen receives the new item plus the closest prior event and decides one of:
   - `duplicate_same_event`
   - `material_update`
   - `different_event`
5. Qwen senior editor scores the item from 0–100 and returns structured JSON with:
   - `importance`
   - `topic`
   - `publish`
   - `reason`
   - `new_fact`
   - `priority_class`
6. Auto-publication requires both deterministic eligibility and senior-editor approval. Low-value commentary, routine diplomatic calls/meetings, and repeated statements remain review-only even when they mention Iran, Trump, Hormuz, Houthis, or another high-profile actor.
7. Translation runs only after the item passes the editorial gate.
8. MADLAD translates to Persian when a dedicated endpoint is configured. Otherwise Qwen translates with a strict translation-only prompt.
9. Qwen Persian editor receives the original English source text and the Persian draft. It must return a concise, natural Persian news version without adding or removing facts.
10. Deterministic validation checks numbers, named entities/critical terms, Persian body quality, forbidden mechanical fragments, and source/translation semantic anchors.
11. Only validated copy is formatted and published to Telegram.

## Editorial priority policy

The senior editor must follow Bikhabar's locked order:

1. Missile launched from Iran toward any country/location.
2. Missile launched toward Iran.
3. Direct kinetic attack / active war event.
4. Strait of Hormuz operational event.
5. Explosion.
6. Drone attack/interception.
7. Warship/naval operation.
8. Tanker / seizure / sinking.
9. Nuclear operational development.
10. Military / airspace operational development.

Routine diplomacy, meetings, phone calls, generic political commentary, analysis, warnings, threats, predictions, and repeated opinions are not auto-published unless they contain a concrete new operational fact.

## Duplicate semantics

Duplicate detection is event-level, not text-level.

Examples:

- Reuters and AP both say Houthis reached Dhubab: duplicate same event.
- A later AP report says Saudi airstrikes hit Mokha airport: new material event, not duplicate merely because Houthis/Yemen are mentioned.
- Three sources quote Trump saying he has no regrets about the Iran war: one low-value event; after the first match, later versions are duplicates.
- A foreign minister phone call about Hormuz is not auto-published unless it announces a concrete closure, attack, seizure, reopening, or similar operational change.

## Senior-editor JSON contract

The model must return JSON only:

```json
{
  "importance": 0,
  "topic": "routine_diplomacy",
  "publish": false,
  "reason": "routine diplomatic contact with no operational development",
  "new_fact": false,
  "priority_class": "low"
}
```

Allowed `priority_class` values: `critical`, `high`, `normal`, `low`.

Malformed JSON is a failure. In `required` mode it cannot auto-publish.

## Duplicate-judge JSON contract

```json
{
  "relation": "duplicate_same_event",
  "confidence": 0.94,
  "new_fact": false,
  "reason": "same Houthi advance reported by another source"
}
```

Allowed `relation` values: `duplicate_same_event`, `material_update`, `different_event`.

## Persian-editor contract

The model receives both source English and draft Persian and returns JSON only:

```json
{
  "text": "شبکه تلویزیونی حوثی‌ها اعلام کرد عربستان سعودی فرودگاه المخا در یمن را هدف حملات هوایی قرار داده است.",
  "faithful": true,
  "natural": true,
  "reason": ""
}
```

Publication requires `faithful=true`, `natural=true`, non-empty Persian text, and deterministic validator success.

Forbidden behavior:

- adding background facts not present in the source
- changing who attacked whom
- changing dates, quantities, locations, or named people
- editorializing or sensationalizing
- translating idioms literally when a natural Persian news equivalent exists
- leaving promotional fragments such as `My story at`

## Failure behavior

- AI timeout / HTTP error / invalid JSON: review queue, not Telegram, in `required` mode.
- Embedding unavailable in `optional` mode: existing deterministic dedup remains active and a degraded-mode log is emitted.
- Translation or Persian edit failure: never publish raw English or broken Persian.
- MADLAD endpoint unavailable: use Qwen translation only when `HF_TOKEN` is available; otherwise follow mode policy.
- Existing Telegram posts are never edited or deleted by this feature.

## Persistence

The existing `EventLedger` remains the source of truth for published events. AI similarity does not require a new database. Candidate events are read from the ledger, filtered to the last 72 hours, embedded on demand, and compared to the new item. A small in-process embedding cache avoids repeated calls during a cycle.

## Testing

Tests must use mocked Hugging Face HTTP responses; CI must never depend on network inference.

Required regressions include:

- same event from different sources is suppressed
- material update passes
- routine foreign-minister calls are not auto-published
- repeated Trump commentary is not auto-published
- missile/direct attack/Hormuz operational events remain publishable
- malformed senior-editor JSON fails closed
- HF timeout fails closed in required mode
- Persian editor repairs mechanical grammar such as `حملات هوایی ... زده است`
- Persian editor cannot change numbers or named entities
- 72-hour event-memory boundary is enforced
- publisher never sends Telegram when AI gate/editor fails

## Rollout

1. Merge with `AI_NEWSROOM_MODE=optional` so existing runtime remains available while credentials are configured.
2. Add `HF_TOKEN` to `/etc/bikhabar/agent.env` on the VPS and, if MADLAD is desired as the primary translator, add `HF_MADLAD_ENDPOINT`.
3. Run a live shadow cycle and inspect decisions without Telegram writes.
4. Switch `AI_NEWSROOM_MODE=required` only after the shadow cycle demonstrates valid structured responses.
5. From that point, AI failure means review queue rather than low-quality public output.
