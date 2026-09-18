# Bikhabar Panel V4.1 — Luna Operator Design

## Goal

Turn Panel V4 into a clean, dense, readable newsroom console where Luna is a real Persian-language newsroom operator powered by the OpenAI Responses API and controlled tools, not a keyword router or decorative chat box.

The user should be able to operate day-to-day newsroom work from the panel without returning to SSH/Termius or a separate ChatGPT conversation.

## Scope

This release changes four areas together because they are one workflow:

1. Luna Assistant becomes a real model-driven operator.
2. Story-level Luna becomes a high-quality Persian translation/editorial-copy action, not a PUBLISH/REJECT judge.
3. The panel UI is redesigned for readability, density, and fewer actions.
4. Bad machine translation is removed from the publishable path and replaced with a fail-closed OpenAI translation pipeline plus quality checks.

Air Traffic must be absent from the entire Panel V4.1 UI. Its backend service may continue running independently and is not deleted by this release.

## Product Principles

- Persian-first, simple, calm, and legible.
- Fewer controls, clearer hierarchy, more stories visible per screen.
- Luna is an operator, not a programmer and not an autonomous publisher.
- High-risk actions require explicit confirmation.
- Read-only actions and translation do not require confirmation.
- No silent fallbacks from a high-quality translation to a publishable low-quality translation.
- Existing Newsroom V3 publication mechanics are reused wherever possible instead of replacing them.

## Luna Assistant

### Model architecture

Use the OpenAI Responses API with custom function tools.

Environment configuration:

- `OPENAI_API_KEY`: required for Luna Operator.
- `LUNA_MODEL_FAST`: default `gpt-5.6-luna` for routine intent/tool routing and short replies.
- `LUNA_MODEL_COMPLEX`: default `gpt-5.6-terra` for difficult multi-step requests and translation repair.

The model names remain environment-overridable so deployment is not tied to one SKU.

No API key is stored in GitHub, JSON data files, browser JavaScript, or rendered HTML.

### Conversation behavior

Luna speaks natural Persian and keeps short server-side conversation context for the current admin session. The model receives only:

- the current user request,
- a bounded recent conversation window,
- the minimal story/source/system data required for the selected tool,
- tool results.

The panel must never send the entire newsroom database or long history on every turn.

### Initial tool set

Luna can call only explicit newsroom tools:

- `search_stories(query, source?, status?, limit?)`
- `get_story(story_id)`
- `translate_story(story_id)`
- `reject_and_block_story(story_id, reason?)`
- `move_story_to_review(story_id)`
- `list_recent_published(limit?, source?)`
- `diagnose_newsroom()`
- `list_sources(kind?, active?)`
- `add_source(kind, identifier, display_name?)`
- `enable_source(source_id)`
- `disable_source(source_id)`

No shell, arbitrary Python, arbitrary file writes, GitHub code edits, or unrestricted HTTP requests are exposed to Luna.

### Confirmation policy

No confirmation:

- search/list/get
- diagnosis
- translation
- move to review

Confirmation required:

- reject and permanently block a story
- add a source
- enable/disable a source
- publish a story, if publishing is later exposed as a Luna tool

For V4.1, Luna does not autonomously publish. The final Publish button remains a human action.

### Durable rejection/blocking

When the user says variants of “این خبر رو حذف کن”، “منتشرش نکن”، or “دیگه این خبر رو نذار”، Luna must resolve the intended story and create a durable block, not merely hide the card.

Implementation should reuse an existing durable V3 rejection mechanism if it already prevents rediscovery/republication. If existing rejection is not sufficient, add a narrow durable block registry and one runtime check so a blocked story cannot re-enter the publish path.

The assistant must report exactly what was blocked and why.

## Translation Quality

### Problem

The current panel machine preview ultimately relies on `translate_to_fa`, which tries Google Translate, Google mobile translation, and MyMemory. These outputs can be awkward or semantically wrong even after glossary/repair passes. They must not be treated as publication-ready copy.

### New translation flow

Story cards no longer auto-load machine translation as the primary Persian copy.

The primary action is **«ترجمه با Luna»**. It sends the source title/body to OpenAI with a strict newsroom translation instruction and returns structured fields:

- `title_fa`
- `body_fa`
- `source_language`
- `quality_passed`
- `quality_notes`

The instruction must require:

- no added facts,
- no omitted material facts,
- preservation of names, numbers, units, attribution, uncertainty, and quotations,
- concise natural Persian newsroom style,
- correct Persian punctuation and half-space,
- no analysis or opinion,
- no PUBLISH/REJECT recommendation.

### Quality gate

Before the translation can become the final Persian story copy, validate it against the source:

- non-empty Persian title/body,
- numbers and critical numeric tokens preserved,
- URLs/handles not hallucinated,
- source attribution preserved when present,
- key semantic terms preserved using the existing semantic-preservation checks where useful,
- known mechanical translation artifacts rejected,
- suspicious large length mismatch rejected,
- model output schema validated.

If the first translation fails the gate, run one repair pass with the failure reasons. If it fails again, return a visible “ترجمه نیاز به بررسی دارد” state and do not save it as final publishable copy.

Google/MyMemory translation may remain only as a clearly labeled diagnostic/temporary preview if needed internally. It must not silently replace a failed Luna translation and must not be eligible for one-click publish.

### Existing bad translations

Previously saved low-quality `machine_translation` values remain historical/cache data only. V4.1 must not prefer them over a Luna translation. A fresh Luna translation overwrites the story’s final Persian copy only after the quality gate passes.

## Story Card Workflow

Each story card is compact and shows:

- source + relative time + status,
- original headline,
- a short original excerpt when useful,
- final Luna Persian translation when available.

Primary actions are reduced to:

- `ترجمه با Luna`
- `بررسی / ویرایش`
- `انتشار` (only when final Persian copy is valid)
- `رد و مسدودکردن`
- `منبع`

Remove Luna importance score, decision reason, PUBLISH/REJECT/SPECIAL badges, and the old “send to Luna for judgment” flow.

Publishing always displays a confirmation using the exact Persian text that will be sent.

## Luna Page

The Luna page becomes a full-width assistant workspace, not a two-column demo page.

Required UI:

- large chat history area,
- persistent composer at the bottom,
- clear typing/working state,
- tool/action result cards inside the conversation,
- confirmation cards for sensitive actions,
- compact story/source references that can be clicked to open the relevant item,
- no canned “sample commands” section,
- no legacy list of Luna PUBLISH/REJECT decisions.

Conversation history is bounded and stored server-side; do not put sensitive operational context in localStorage.

## Visual Redesign

### Typography

Use a real loaded Persian font rather than merely naming a font that may not exist on the device.

Preferred family: Vazirmatn, self-hosted as WOFF2 with regular, medium, and bold weights.

Fallback stack: `Vazirmatn, Tahoma, Arial, sans-serif`.

Increase body/story readability:

- body text 14–15px desktop, 14px mobile,
- story headline 16–17px,
- line-height around 1.85 for Persian body text,
- avoid very light gray text for core content.

### Layout

- Reduce oversized KPI area.
- Give the story stream most of the viewport width.
- Fit more stories vertically by reducing decorative padding and duplicate labels.
- Keep critical actions reachable without expanding cards.
- Use a restrained dark slate palette with one blue accent.
- Avoid glassmorphism, excessive gradients, large shadows, and decorative animations.
- Mobile bottom navigation stays compact and safe-area aware.

### Navigation

Keep only daily operator destinations:

- داشبورد
- ورودی خبرها
- بررسی
- Luna
- منتشرشده
- منابع
- تنظیمات/سلامت

Air Traffic is removed from all menus, cards, quick links, health modules, and cached panel shell assets.

## Cache/PWA Cleanup

The service worker must cache only current V4.1 assets. Remove legacy V2/V3 CSS/JS files from its shell list. Increment the cache version. Navigation/document requests remain network-first/no-store so old panel HTML cannot survive a deploy.

## AI Usage / Cost Telemetry

Store bounded daily usage aggregates, not prompts:

- request count,
- input tokens,
- output tokens,
- cached input tokens when available,
- model,
- estimated cost,
- operation type (`assistant`, `translation`, `translation_repair`).

Expose today/month summary in Settings/System Health. Do not log the API key or full private conversation content in usage telemetry.

## Error Handling

- Missing `OPENAI_API_KEY`: Luna UI remains available but clearly reports “Luna متصل نیست”; ordinary panel operation continues.
- OpenAI timeout/rate limit: no destructive action is executed; return a retryable Persian error.
- Tool ambiguity: Luna asks a focused clarification instead of guessing a story/source.
- Tool failure: report the specific failure and preserve prior state.
- Translation failure: never promote fallback machine text as final publishable copy.
- Confirmation expires after a short bounded period and cannot be replayed after completion.

## Security

- All Luna endpoints require authenticated admin session and CSRF protection consistent with the rest of the panel.
- Tool arguments are server-validated even when generated by the model.
- Destructive/source-changing tools create audit-log records.
- Pending confirmations are single-use.
- OpenAI receives only the minimum operational context needed for the user’s request.

## Testing

Add tests for:

- natural Persian request routing to every Luna tool,
- ambiguous story/source requests producing clarification rather than action,
- confirmation required for destructive actions,
- reject/block durability,
- translation schema and quality-gate pass/fail/repair behavior,
- machine translation never becoming final copy after Luna failure,
- story publish disabled without valid final Persian copy,
- token/cost accounting,
- missing API key and provider errors,
- no Air Traffic UI strings/links in V4.1 templates/assets,
- service-worker legacy asset removal,
- readable typography hooks and compact card contract,
- regression coverage for login, dashboard, review, source management, and existing V3 publish command path.

## Deployment

Develop on `panel-v4-1-luna-operator`, run focused and full CI, open a PR, merge only after green checks, then update the VPS production checkout and restart only the panel service unless a narrow runtime block check requires the agent service to be restarted too.

The OpenAI key is configured separately on VPS in `/etc/bikhabar/agent.env`; deployment must not print it or commit it.

## Acceptance Criteria

V4.1 is accepted when:

1. The user can converse naturally in Persian with Luna and get contextual, non-canned replies.
2. Luna can find stories, translate them, reject/block them after confirmation, inspect the newsroom, and manage approved source actions.
3. Story-level Luna produces translation/editorial copy only, with no editorial judgment score/decision UI.
4. Failed/poor translation cannot become final publishable copy.
5. The panel is visibly cleaner, more readable, and shows more stories per viewport.
6. Air Traffic is absent from the entire panel UI and current service-worker shell.
7. Existing login/review/publish/source flows still work.
8. AI token/cost usage is visible and bounded.
