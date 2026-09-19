# Bikhabar Newsroom V5 + Luna — Product and Architecture Design

Date: 2026-09-20
Status: Approved design, pre-implementation

## 1. Product intent

Bikhabar is an editorial control app for Iran-related breaking news. Its primary job is not to archive every ingestion artifact; it is to help the operator publish the right news quickly and safely.

The intended newsroom flow is:

1. Sources ingest fresh stories.
2. The system removes exact duplicates, already rejected items, and irrelevant noise.
3. Every remaining story is translated into Persian before it becomes visible to the operator.
4. Luna acts as senior editor: it identifies important, concrete, fresh stories and may auto-publish only when all safety and quality guards pass.
5. Any relevant, non-duplicate story that Luna does not auto-publish remains available to the operator in Review, fully in Persian.
6. The operator may publish, edit, ask Luna about, or reject the story.
7. Published and rejected stories leave the active queue immediately and remain auditable in history.

The product must feel like a fast mobile app rather than a collection of server-rendered pages that reload from the network.

## 2. Core invariants

These rules are product contracts, not optional UI preferences.

### 2.1 Persian-first visibility

- No English-only story may appear in Dashboard/Review as an actionable card.
- No placeholder such as “translation is being prepared” may appear in the operator queue.
- Translation is a required ingestion stage, not a page-render side effect.
- A story with a transient translation failure stays internal and is retried; it does not leak raw English into Review.
- If the source itself is already Persian, the system normalizes/polishes it and treats it as Persian-ready.

### 2.2 Review means unpublished news requiring human choice

Review contains every relevant, non-duplicate, non-terminal story that has not already been published automatically.

There is no artificial business cap such as 40 or 100 stored Review stories. Pagination and virtualization are performance mechanisms only; they must not hide or discard eligible stories.

### 2.3 Rejection is durable for that exact story

Rejecting a story creates a durable story tombstone. The same story must not reappear on later scans, retries, or duplicate detection passes.

Rejecting a story does **not** block its source. A later genuinely new story from the same source remains eligible.

### 2.4 Publication is idempotent

A story must not be published twice because of browser refresh, worker restart, timeout, duplicate command submission, or Telegram reconciliation.

### 2.5 Source time is canonical for newsroom ordering

The canonical visible timeline uses the source publication timestamp. `updated_at`, translation time, discovery time, or panel-open time must never masquerade as the story’s publication time.

## 3. Unified story lifecycle

Every story has one canonical lifecycle shared by Dashboard, Review, Luna, and the publishing workers.

Recommended states:

- `received`: ingested and stored; internal only.
- `translated`: a usable Persian version exists.
- `editorial_ready`: Luna/editorial checks have completed.
- `review`: relevant, non-duplicate, unpublished, and awaiting human decision.
- `publishing`: publication is committed to the outbox and being sent/reconciled.
- `published`: Telegram publication succeeded and the message id is known.
- `rejected`: explicitly rejected by the operator.
- `duplicate`: exact/same-event duplicate with no material new fact.
- `irrelevant`: outside the newsroom’s editorial scope.
- `failed`: terminal technical failure that cannot safely advance without intervention.

`received` and transient translation/editorial failures are backend concerns. They must not produce actionable English cards.

The system must stop maintaining divergent meanings for the same story across `panel_live_feed`, editorial queue, history, and page-specific projections. Compatibility exports may exist during migration, but one runtime record is authoritative.

## 4. Runtime storage architecture

### 4.1 SQLite on the VPS is the runtime source of truth

Interactive reads and writes move from GitHub JSON files to a local SQLite database using WAL mode.

Reasoning:

- UI requests must not wait on GitHub network latency.
- transactions are required for durable state transitions and outbox publication.
- indexes and cursor queries are needed for large Review queues.
- local reads must be fast enough for app-like navigation.

### 4.2 Proposed tables

#### `stories`

Core identity and source fields:

- `id` — stable internal story id
- `news_key` — stable source/event identity when available
- `source_id`
- `source_name`
- `source_url`
- `source_item_id`
- `original_title`
- `original_body`
- `published_at_source`
- `discovered_at`
- `state`
- `created_at`
- `updated_at`

Indexes should support `(state, published_at_source DESC, id DESC)`, `news_key`, `source_url`, and source identity lookup.

#### `translations`

- `story_id`
- `title_fa`
- `body_fa`
- `backend`
- `quality_passed`
- `attempt_count`
- `last_error`
- `translated_at`

The active operator copy is always Persian-ready. A later Luna rewrite can live separately from the initial machine translation.

#### `editorial_decisions`

- `story_id`
- `importance`
- `priority_class`
- `publish_recommended`
- `new_fact`
- `topic`
- `reason`
- `confidence`
- `model`
- `decided_at`

#### `publications`

- `story_id`
- `idempotency_key` (unique)
- `copy_mode` (`machine`, `luna`, `manual`)
- `title_fa`
- `body_fa`
- `status`
- `telegram_message_id`
- `attempt_count`
- `last_error`
- `created_at`
- `published_at`

#### `story_tombstones`

- `story_id`
- `news_key`
- `source_url`
- `reason` (`rejected_manual`, duplicate identity, etc.)
- `created_at`

Matching must be narrow enough to suppress the same story without suppressing future stories from the same source. Prefer stable `news_key`/source item id, with exact canonical source URL as fallback. Do not use broad topical fingerprinting for manual rejection.

#### `sources`

Source configuration and operational health. Runtime source changes are local and audited; GitHub export is secondary.

#### `jobs`

Durable background work for translation, editorial analysis, publication, reconciliation, and maintenance retries.

#### `luna_conversations`

Conversation messages, structured context, recent referenced story/source ids, and pending confirmations.

#### `audit_log`

Append-only record of sensitive operator/Luna mutations.

## 5. Ingestion and translation pipeline

The only supported path is:

`ingest → exact identity/tombstone checks → dedup/event relation → translate → translation QC → editorial decision → auto-publish or review`

### 5.1 Translation is mandatory before operator visibility

The existing lightweight translation stack remains useful as the first tier:

1. Google translate endpoint
2. Google mobile fallback
3. MyMemory fallback
4. AI translation fallback when the lightweight stack cannot produce acceptable Persian

Translation work executes in a background worker, never synchronously during page rendering.

Transient failures create/retry a translation job with exponential backoff and bounded jitter. The story remains `received`/internal until a Persian translation passes minimal quality checks.

Quality checks should preserve the current source-aware protections for names, numbers, operational terms, known idiom failures, and semantic loss. A bad machine translation must not be silently treated as publish-ready.

### 5.2 No news loss during provider outages

A failed translation provider must not mark the story as “seen and gone”. The raw story remains durable and the job is retried.

The UI may expose a technical health counter under Control/System, but not an English story card in Review.

## 6. Luna as senior editor

Luna has two distinct responsibilities and they must not be conflated:

1. **Editorial Luna** — evaluates incoming stories and prepares/publishes newsroom copy.
2. **Operator Luna** — conversational assistant that the human uses to inspect and control the newsroom.

They may share model/provider infrastructure but have separate prompts, contracts, and tests.

### 6.1 Editorial auto-publication policy

Auto-publication is an explicit mode, controlled by a setting and auditable.

A story may auto-publish only when all required gates pass:

- source is enabled/allowed;
- story is fresh;
- story is not tombstoned;
- story is not an exact duplicate or same-event repetition without material new fact;
- Persian translation exists and passes quality checks;
- editorial analysis identifies a concrete new fact;
- priority is `critical`, or `high` with sufficient editorial confidence;
- publication guards and Telegram availability pass.

Routine statements, analysis, warnings, predictions, diplomacy without a concrete new operational fact, and low-confidence material do not auto-publish.

Crucially, failure to auto-publish does **not** mean discard. A relevant story that is not duplicate/irrelevant moves to `review`.

### 6.2 No artificial daily quota as a hidden blocker

A daily quota must not silently stop the channel and swallow eligible breaking news.

Use anti-flood controls instead:

- rate-limit publication bursts;
- serialize or pace rapid sends;
- preserve queued publication jobs;
- show operational status visibly in Control/System.

If a configurable editorial cap is retained for policy reasons, reaching it must route stories to Review and surface the reason, never lose them.

## 7. Review and operator workflow

Review is the primary home screen for daily use.

Each story card shows:

- source;
- exact source publication time plus relative age;
- Persian title;
- concise Persian body/summary;
- Luna importance/priority indicator;
- optional short editorial reason;
- primary actions: `Publish`, `Edit`, `Reject`;
- secondary action: `Ask Luna`;
- source link.

### 7.1 Publish

Publish opens a compact confirmation preview of the exact Persian copy to be sent. On confirmation, the request performs a local transactional transition to the publication outbox and immediately gives optimistic UI feedback.

The card disappears only after publication is confirmed/reconciled, or it may show a transient `publishing` state until confirmation arrives.

### 7.2 Edit

Edit focuses on the Persian publish copy. Original-language content is available only as a collapsible reference section, not as the primary decision surface.

### 7.3 Reject

Reject requires confirmation, creates a durable exact-story tombstone, marks the canonical story rejected, removes it from active UI in real time, and preserves the decision in history/audit.

### 7.4 Unlimited logical queue, virtualized rendering

The server exposes cursor pagination ordered by `published_at_source DESC, id DESC`.

The UI does not render thousands of cards at once. It keeps only a bounded viewport window and loads additional pages as the user scrolls. This is a rendering optimization, not a content limit.

## 8. Publication outbox and Telegram reconciliation

Publication must use an outbox pattern.

In one local transaction:

1. validate story is eligible and not already published;
2. create/update a unique publication record using an idempotency key;
3. transition story to `publishing`;
4. commit.

A worker sends the prepared Persian copy to Telegram.

On success:

- store Telegram message id;
- mark publication `published`;
- mark story `published`;
- emit a real-time event.

On ambiguous timeout:

- do not blindly resend;
- run reconciliation using available command/message metadata;
- only retry when safe.

This design prevents browser refresh, double-click, command retry, worker restart, or API timeout from creating duplicate Telegram posts.

## 9. Real-time application architecture

### 9.1 App shell

The authenticated newsroom becomes a persistent application shell.

Primary mobile navigation:

1. **News** — unpublished Persian Review queue
2. **Luna** — conversational operator/editor assistant
3. **Published** — publication history
4. **Control** — sources, settings, health, technical status

`Intake` is no longer part of the normal operator navigation. Raw/staging processing remains internal or available only under diagnostics.

### 9.2 Navigation behavior

After the initial load, ordinary tab/navigation transitions must not perform a full document reload.

State to preserve:

- current tab;
- Review scroll position;
- loaded Review cursor/pages;
- selected story context;
- Luna conversation state;
- composer draft where practical.

### 9.3 Server-Sent Events

Use SSE as the primary one-way real-time channel because the newsroom mostly needs server-to-client updates and regular HTTP remains appropriate for mutations.

Events include:

- `story_added`
- `story_updated`
- `story_published`
- `story_rejected`
- `counts_changed`
- `job_health_changed`
- `luna_status`

Polling is a fallback for disconnected clients, not the primary refresh mechanism.

## 10. PWA and caching

The current network-only navigation behavior is replaced by an app-shell strategy.

- HTML shell and versioned static assets are cached.
- Runtime APIs remain network-fresh.
- Navigation can fall back to the cached authenticated shell when appropriate.
- asset cache names/versioning change with deploys.
- service worker activation removes obsolete caches and claims clients.
- the UI exposes a safe “new version available / reload” path if a breaking frontend update is detected.

The application should run over HTTPS in production. This is required for reliable PWA behavior and microphone capture on modern mobile browsers.

## 11. Luna operator design

The goal is ChatGPT-like interaction quality and operator ergonomics, not merely a different color scheme.

### 11.1 Conversation behavior

Luna must:

- understand conversational Persian;
- use conversation and structured story/source context;
- execute a tool once when one execution is sufficient;
- never claim an operation completed without executor success;
- hide internal tool logs from the normal conversation;
- answer successful simple mutations with a short human response such as “چشم، انجام شد.”;
- return useful content for read/info requests instead of an empty success acknowledgement;
- ask a question only when ambiguity materially prevents a correct action;
- require confirmation only for sensitive mutations such as publish, delete, source/settings changes, and code/UI changes;
- preserve builder/merge separation and CI gates for code changes.

### 11.2 Tool-call deduplication

Within one user turn, Luna caches completed tool calls by canonical `(tool_name, normalized_arguments)`.

If the model requests the identical read/action again in the same turn, the runtime reuses the prior result rather than invoking the executor a second time.

Internal events remain available to audit/telemetry but are not rendered as chat cards.

### 11.3 Model routing

- routine commands and straightforward tool use → fast model;
- complex editorial reasoning, ambiguous analysis, or higher-stakes synthesis → stronger configured model;
- transcription → dedicated transcription model.

Routing is deterministic/testable where possible and must not expose model plumbing to the operator.

## 12. Luna chat UX

Luna becomes a full-height messenger-style experience.

Composer capabilities:

- text input;
- clear send button;
- image attachment;
- microphone/voice recording;
- recording state and timer/waveform feedback;
- stop/cancel behavior;
- voice transcription into the editable text composer;
- ability to edit transcription before sending.

The page displays only meaningful conversational UI:

- user messages;
- Luna messages;
- inline confirmation for a pending sensitive action;
- compact error/retry state when needed;
- optional builder/PR result card when a code task genuinely produces a PR.

Generic internal tool cards such as repeated `list_sources · done` are removed.

### 12.1 Story-context handoff

Every Review card includes `Ask Luna`.

Opening Luna from a story sets structured context with the selected story id, allowing commands such as:

- “تیترشو کوتاه‌تر کن”
- “این ارزش انتشار داره؟”
- “منبعش رو بررسی کن”

without the operator copying the story text or URL.

## 13. Voice and transcription

Voice must work as a first-class input method.

Preferred flow:

1. tap microphone;
2. browser begins recording;
3. tap again to stop;
4. upload audio asynchronously;
5. transcription returns;
6. transcript is inserted into the composer;
7. operator edits or sends.

Fallback flow:

- if `MediaRecorder/getUserMedia` is unavailable, open the device audio picker/recorder;
- submit the selected file to the same transcription endpoint.

Production HTTPS is a requirement for the preferred browser recording path.

Voice progress should be represented as composer/recording state, not noisy internal tool cards in the conversation.

## 14. Performance budget

Implementation is not considered complete merely because functionality works. The app has explicit performance targets.

Target budgets on the production VPS under ordinary load:

- post-initial-load tab transition: < 100 ms perceived response;
- common Review SQLite query: < 50 ms server-side;
- local publish/reject mutation acknowledgement: target < 200 ms excluding external Telegram completion;
- new already-processed story visible after pipeline completion: < 1 s through SSE;
- no normal tab transition performs a full-page reload;
- no interactive request path waits on GitHub API;
- long external translation/OpenAI/Telegram operations run in workers and do not freeze UI navigation.

Client rendering must remain smooth with large logical queues by using cursor pagination and list virtualization.

## 15. Migration from GitHub JSON

Migration must be reversible and must not lose stories.

### Phase A — prepare

- create SQLite schema and migrations;
- import sources/configuration;
- import current live feed, editorial queue, editorial history, publication state, seen/tombstone candidates, and Luna conversation data where applicable;
- normalize duplicate identities;
- produce import counts and validation report.

### Phase B — dual verification

- run SQLite projections in shadow mode;
- compare counts, terminal states, current Review eligibility, and published history against existing JSON data;
- do not auto-publish from the new runtime yet.

### Phase C — cutover

- pause ingestion briefly;
- import the final delta;
- switch runtime reads/writes to SQLite behind a feature flag;
- resume ingestion;
- verify Review, translation jobs, Luna, publication commands, and SSE.

### Phase D — controlled auto-publish enablement

- start with editorial auto-publish disabled;
- validate fresh stories are translated and routed to Review correctly;
- enable Luna auto-editor only after explicit operator confirmation and production verification.

### Rollback

- retain legacy JSON snapshots and migration metadata;
- keep a feature flag to return reads to the legacy path during the stabilization window;
- do not delete legacy files during initial rollout.

After stabilization, GitHub JSON may remain as backup/audit export rather than interactive storage.

## 16. Error handling and observability

The Control/System area must make operational failures visible without polluting Review.

Track at minimum:

- ingestion successes/failures by source;
- translation queue depth, attempts, provider failures, and oldest pending age;
- editorial queue depth and model errors;
- publication outbox depth;
- Telegram send/reconciliation failures;
- SSE client health;
- Luna provider/transcription health;
- database migration/schema version;
- most recent successful ingest/translation/editorial/publication timestamps.

A provider outage should degrade the relevant background stage, not freeze the entire app.

## 17. Security and confirmations

Existing authenticated admin/session protections remain.

Mutation policy:

- read/status/analysis actions: no confirmation;
- publish, delete, reject, source changes, settings changes, code/UI changes: explicit confirmation;
- enabling automatic Luna publishing: explicit confirmation;
- automatic publications after the mode is enabled: no per-story human confirmation, but every decision and publication is audited.

CSRF protection remains for state-changing browser requests. SSE is authenticated and read-only.

## 18. Testing strategy

The implementation plan must include tests at the boundaries that matter most.

### Data/state tests

- migration preserves eligible Review stories and terminal history;
- rejected story cannot re-enter after rescans;
- source remains usable after one story is rejected;
- canonical source time ordering;
- cursor pagination returns all eligible stories without overlap/loss.

### Translation tests

- English story is not operator-visible before Persian passes;
- source-Persian story advances without unnecessary translation;
- provider fallback order;
- transient failure retries without losing story;
- low-quality translation does not become publish-ready.

### Editorial routing tests

- critical/high-confidence concrete fresh fact can auto-publish when mode enabled;
- normal/uncertain relevant story routes to Review;
- duplicate/irrelevant story does not clutter Review;
- auto-publish disabled routes otherwise-eligible story to Review.

### Publication tests

- double command yields one Telegram publication;
- worker restart preserves outbox work;
- ambiguous Telegram timeout reconciles before retry;
- successful publication removes story from active Review and appears in history.

### Luna tests

- identical tool+args in one turn invokes executor once;
- successful mutation returns one concise user-facing completion;
- read request returns requested information;
- internal tool events are not rendered in chat;
- complex request can route to the stronger model;
- context from `Ask Luna` resolves the selected story;
- voice transcription populates the composer.

### UX/PWA tests

- tab navigation does not full reload;
- SSE add/update/remove events patch the current list correctly;
- Review scroll state survives Luna round-trip;
- service worker serves versioned app shell while API remains fresh;
- mobile microphone fallback works when direct capture is unavailable.

### Performance checks

Add repeatable smoke benchmarks for common SQLite queries, Review API latency, and large-queue client rendering.

## 19. Rollout order

Implementation should be split into safe milestones rather than one giant switch:

1. runtime database/schema + migration tooling;
2. unified story repository and state machine;
3. background translation jobs and Persian-first invariant;
4. editorial routing and Review API;
5. publication outbox/idempotency;
6. SSE and app-shell navigation;
7. Review virtualization and simplified operator UX;
8. Luna orchestration/tool dedupe/model routing;
9. Luna chat redesign + voice UX;
10. shadow verification and migration cutover;
11. explicit enablement of automatic Luna publishing;
12. stabilization, observability tuning, and retirement of interactive GitHub JSON reads.

Each milestone must keep production deployable and include regression coverage for previously fixed newsroom behaviors.

## 20. Non-goals

This redesign does not require:

- rewriting the entire backend in another language/framework;
- replacing Flask solely for fashion;
- exposing raw ingestion/staging states to the operator;
- using WebSockets when SSE plus normal HTTP is sufficient;
- using broad topic fingerprints to permanently suppress future news after a manual rejection;
- removing GitHub-based audit/backup immediately;
- letting Luna silently merge code or bypass CI/confirmation gates.

## 21. Acceptance criteria

The redesign is successful when all of the following are true in production:

1. Every actionable news card the operator sees is Persian.
2. There is no “translation preparing” placeholder in the active newsroom.
3. All relevant, non-duplicate, unpublished stories remain available for human review with no artificial queue cap.
4. Important high-confidence breaking news can be auto-published by Luna when that mode is explicitly enabled.
5. Stories Luna does not auto-publish flow to Review instead of disappearing.
6. Rejecting a story prevents only that story from returning.
7. Published stories leave the active queue immediately and cannot double-publish.
8. Review ordering reflects real source publication time.
9. Luna behaves like a concise operator assistant: context-aware, no repeated tools, no internal tool spam, confirmation only where required.
10. Voice recording/transcription is a first-class Luna input path.
11. Normal navigation feels app-like and does not require full-page reloads.
12. Interactive reads do not depend on GitHub network latency.
13. The migration can be rolled back during the stabilization window without data loss.
