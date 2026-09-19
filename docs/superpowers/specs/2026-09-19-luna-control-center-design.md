# Luna Control Center — Architecture Design

Date: 2026-09-19
Status: Revised after operator feedback; awaiting written-spec re-approval
Project: Bikhabar Telegram News Agent / Newsroom Panel

## 1. Goal

Turn Luna from a translation/chat helper into the natural-language control surface for the entire Bikhabar newsroom panel.

The operator should be able to speak naturally in Persian and ask Luna to inspect, explain, change, publish, rename, enable/disable, troubleshoot, or modify the panel. Luna must execute only through explicit, bounded capabilities. Any operation that mutates state must require human confirmation immediately before execution.

Examples that must work naturally:

- «لونا ClashReports رو فارسی بنویس و اصلاح کن»
- «این منبع رو غیرفعال کن»
- «این خبر رو دیگه منتشر نکن»
- «همین ترجمه ماشینی رو منتشر کن»
- «این خبر رو با نسخه خودت اصلاح کن و منتشر کن»
- «خبرهای این منبع فقط برن برای بررسی»
- «اسم این منبع رو عوض کن»
- «ببین چرا خبرهای این منبع نمیان و درستش کن»
- «این دکمه رو ببر سمت راست»
- «فونت این قسمت رو بزرگ‌تر کن»

## 2. Product principles

### 2.1 Luna is the control surface, not an unrestricted shell

Luna should be able to do everything the product intentionally supports, but it must not receive arbitrary shell access, unrestricted filesystem access, or direct production-edit privileges.

Every action is routed through a registered capability with validation, authorization, confirmation policy, audit logging, and a result contract.

### 2.2 Read-only actions are immediate

Inspection and diagnosis may run without confirmation, including:

- search stories
- inspect one story
- list/search sources
- inspect panel state
- inspect queues
- inspect recent publications
- inspect Builder/CI status
- diagnose why a source or workflow is not working

### 2.3 Every mutation requires confirmation

Any action that changes newsroom state, source state, publication state, configuration, code, UI, or deployment state must stop at a human-confirmation boundary.

Examples:

- publish story
- reject story
- edit or rename source
- enable/disable/delete source
- move story between queues
- save translated/edited copy
- change source policy
- change panel settings
- code/UI change through Builder
- merge a Builder PR

The model may prepare and explain a proposed change before confirmation, but it must not perform the mutation until the user explicitly confirms.

### 2.4 Story rejection is not blocking

Rejecting a story means only that specific story leaves the active publication workflow and is recorded as rejected for history/audit.

Rejection must not:

- create an operator block
- blacklist the story fingerprint for future ingestion
- block the source
- prevent future stories from the same source from entering the newsroom

If the operator later wants to disable or delete a source, that is a separate source mutation with its own confirmation.

### 2.5 No false success

Luna may only say a change succeeded when the executor returns a successful result.

A model-generated sentence such as «انجام شد» is not evidence of success.

### 2.6 Existing safe publication pipeline remains authoritative

Publishing must continue through the existing safe `v3_publish` command path. Luna does not bypass publication safeguards or write directly to Telegram.

### 2.7 Code/UI changes remain CI-gated

Requests that modify application code, UI, routes, behavior, or deployment configuration go through Builder:

request → confirmation → branch → tests → Draft PR → CI → merge confirmation → merge → existing main-to-production promotion.

Luna never edits production code directly.

## 3. Existing foundation

The current V4.1 system already contains useful pieces that should be preserved:

- natural-language operator endpoint
- Luna tool schemas and server-side tool execution
- pending confirmation records with expiry
- audit records
- story translation path
- story publication path
- source-management tools
- Builder branch/PR/CI flow
- stateless Responses API continuation compatible with the configured 1xAI provider

The new architecture should organize these into one explicit control-center layer rather than replacing working components.

## 4. Architecture

### 4.1 High-level flow

```text
User message
   ↓
Luna Interpreter
   ↓
Context Resolver
   ↓
Capability Registry
   ↓
Read-only? ───────────────→ Execute immediately
   ↓ no
Mutation Proposal
   ↓
Pending Action + Preview
   ↓
Human Confirmation
   ↓
Capability Executor
   ↓
Verified Result
   ↓
Audit Log + UI refresh + concise Luna reply
```

### 4.2 Luna Interpreter

Responsibilities:

- understand natural Persian requests
- identify intent
- identify referenced entities such as «این خبر»، «همین منبع»، `ClashReports`
- decide whether more context is required
- select a capability rather than inventing an action

The interpreter must not perform business logic itself.

### 4.3 Context Resolver

Resolves natural references into concrete IDs.

Examples:

- `ClashReports` → source ID
- «این خبر» → current/last referenced story ID
- «همین ترجمه» → machine or Luna copy associated with the current story
- «اون منبعی که الان خطا داره» → matching source after diagnosis

Resolution policy:

1. exact ID if provided
2. exact normalized name/handle match
3. recent conversation context
4. search capability
5. if still ambiguous, ask one short clarification question

No mutation is proposed against an ambiguous target.

### 4.4 Capability Registry

Introduce a central registry describing every action Luna is allowed to perform.

Each capability has a contract similar to:

```python
Capability(
    name="rename_source",
    domain="sources",
    mutates=True,
    requires_confirmation=True,
    schema=...,
    preview=...,
    executor=...,
    result_schema=...,
)
```

The registry becomes the source of truth for:

- tool schema exposed to the model
- mutation/read-only classification
- confirmation policy
- input validation
- preview generation
- executor routing
- audit category

This prevents policy from being duplicated across prompts, tools, endpoints, and UI code.

## 5. Capability domains

### 5.1 Stories

Required capabilities:

- search stories
- inspect story
- show original copy
- show machine Persian copy
- generate/re-generate machine Persian copy
- generate Luna copy
- save manual/Luna edit
- move to review
- reject story
- publish machine copy
- publish Luna copy
- inspect recent published items
- explain why a story is rejected/not publishable

Publishing behavior:

- `publish_machine_copy`: use persisted machine Persian copy
- `publish_luna_copy`: require a passed Luna copy
- both require explicit confirmation
- both enqueue through `v3_publish`

Rejection behavior:

- `reject_story`: marks only the selected story as rejected
- removes that story from the active dashboard/workflow
- does not call `add_operator_block`
- does not create a persistent blacklist entry
- does not alter source state

### 5.2 Sources

Required capabilities:

- list/search source
- inspect source
- add source
- rename display name
- enable
- disable
- hide/delete
- change source policy
- set “review only” behavior
- inspect source health
- diagnose ingestion failures

Example:

User: «لونا ClashReports رو فارسی بنویس و اصلاح کن»

Expected sequence:

1. resolve `ClashReports`
2. infer `rename_source_display_name`
3. propose a Persian display name, e.g. «کلش ریپورتز»
4. show confirmation: «نام نمایشی ClashReports به «کلش ریپورتز» تغییر کند؟»
5. after confirmation, persist source override/custom-source change
6. refresh source cards and any visible story source labels
7. report verified success

### 5.3 Newsroom workflow and settings

Capabilities should include operator-facing configuration that is safe to expose:

- source routing policy
- review-only policy
- mute/unmute newsroom alarm
- machine-translation behavior
- dashboard filters where persisted
- other existing newsroom settings that already have a safe storage path

Do not create a generic arbitrary environment-variable editor.

### 5.4 Diagnostics

Read-only diagnostics may run immediately:

- panel service state visible to application
- source health
- queue counts
- translation failures
- publication queue status
- recent command failures
- Builder status

A diagnosis may propose a mutation, but fixing it follows the normal confirmation boundary.

### 5.5 Code and UI — Builder domain

Requests such as:

- «این دکمه رو ببر سمت راست»
- «فونت این قسمت رو بزرگ‌تر کن»
- «یه فیلتر جدید اضافه کن»

are classified as Builder requests.

Flow:

1. Luna summarizes requested code/UI change
2. user confirms starting Builder
3. Builder creates isolated branch
4. tests are added/updated first where appropriate
5. implementation is committed
6. Draft PR is opened
7. CI status is surfaced by Luna
8. Luna asks for merge confirmation only when CI is green
9. merge occurs through the existing controlled Builder release path
10. existing production promotion handles deployment

Luna must never claim deployment succeeded until the relevant executor/CI state confirms it.

## 6. Unified mutation proposal

All mutating capabilities should use one common proposal envelope:

```json
{
  "action_id": "...",
  "capability": "rename_source",
  "target": {"type": "source", "id": "..."},
  "summary_fa": "نام نمایشی ClashReports به «کلش ریپورتز» تغییر کند؟",
  "before": {...},
  "after": {...},
  "expires_at": "...",
  "status": "pending"
}
```

Benefits:

- one confirmation UI
- one audit format
- clear before/after previews
- consistent expiry behavior
- easier rollback support later

Confirmation must execute the exact frozen proposal, not re-interpret the original user sentence.

## 7. Conversation and context

Conversation context should store only the minimum needed to resolve references reliably:

- recent user/assistant messages
- last referenced story ID
- last referenced source ID
- last proposed action ID
- last Builder PR number

Avoid relying only on free-form conversation text for entity resolution when a concrete ID is available.

## 8. Machine translation and dashboard workflow

The dashboard workflow must support the operator without forcing Luna for every story.

### Required live-card behavior

For every incoming non-Persian story:

1. create a machine Persian translation automatically
2. persist the machine Persian title/body to the story record
3. show the Persian machine copy as the primary card content
4. preserve original-language content behind the source/original view
5. offer separate actions:
   - «انتشار مستقیم» — publish the machine Persian copy
   - «ترجمه با Luna» — create a higher-quality Luna copy
   - review/edit
   - «رد» — reject only this story, without blocking

If the machine translation is already fluent, the operator can publish it without paying the Luna latency/cost.

### Translation source

The existing network translation pipeline may use Google and its existing fallbacks/quality rules. Dashboard localization should not depend on an in-memory panel-only cache as the only copy; the publishable machine translation must be persisted to the story record.

## 9. New-story alarm

The dashboard should poll the live feed and detect newly appearing story IDs.

Behavior:

- no alarm for cards already present when the page first loads
- one short alert sound when one or more new IDs appear
- do not replay the alarm for the same story on every poll
- browser audio is unlocked after the operator's first interaction, because browsers may block autoplay audio
- alarm state respects any existing mute setting

## 10. Remove published cards from live dashboard

A story must leave the active dashboard only after publication is actually confirmed by the newsroom/publication state, not merely when the publish button is clicked.

Preferred behavior:

- optimistic UI may mark the card as «در صف انتشار»
- when the publication state becomes terminal-success (`published_manual`, `published_auto`, or equivalent reconciled success), the card disappears from active live cards
- the story remains available in published/history views and audit data

This prevents a failed queue operation from silently hiding an unpublished story.

## 11. Confirmation UX

Luna should produce short, concrete confirmation prompts.

Good:

> نام نمایشی `ClashReports` به «کلش ریپورتز» تغییر کند؟

> همین ترجمه ماشینی منتشر شود؟ «...»

> این خبر رد شود؟ فقط همین مورد از چرخه فعلی کنار می‌رود.

> منبع `X` غیرفعال شود؟ تا زمان فعال‌سازی دوباره، خبر جدیدی از آن وارد نمی‌شود.

Bad:

> آیا مطمئن هستید که می‌خواهید عملیات مربوطه اجرا شود؟

The confirmation response should show enough target information to prevent accidental edits to the wrong entity.

## 12. Audit

Every capability execution should create an audit entry containing:

- timestamp
- actor (`luna_operator`)
- capability name
- target type/id
- whether confirmation was required
- action ID
- outcome (`success`, `failed`, `expired`, `cancelled`)
- concise human-readable summary
- safe result metadata

Do not store secrets, API keys, raw authorization headers, or full provider payloads in audit records.

## 13. Error handling

### Ambiguous target

Do not mutate. Ask a short clarification question.

### Executor failure

Return the actual failure in plain Persian. Keep the action auditable. Do not say the change succeeded.

### Confirmation expired

Require a new proposal rather than executing stale data.

### Changed target after proposal

Use optimistic concurrency/version data where available. If the underlying record changed materially after proposal creation, fail closed and ask Luna to prepare a fresh proposal.

### Builder failure

Surface branch/PR/CI status and stop. Never bypass CI.

## 14. Security boundaries

Luna must not receive these generic powers:

- arbitrary shell commands
- arbitrary SQL
- arbitrary filesystem paths
- arbitrary environment variable mutation
- secret retrieval
- unrestricted HTTP proxying
- direct Telegram write outside the existing publication path
- direct production code editing

If a future feature needs one of these behaviors, expose a narrowly scoped capability instead.

## 15. Performance targets

- simple read-only Luna actions: target 3–5 seconds in normal conditions
- direct dashboard actions that do not require Luna model output: near-immediate after API round trip
- machine translation should run asynchronously/in small batches so dashboard rendering stays responsive
- Luna translation may be slower but should not block dashboard polling or operator actions
- capability execution should avoid unnecessary extra model rounds when the target and intent are already resolved

These are targets, not hard SLA guarantees.

## 16. Testing strategy

### Unit tests

- capability registry metadata
- read-only vs mutation classification
- resolver exact/ambiguous behavior
- proposal creation
- confirmation executes frozen payload
- expired proposal rejection
- source rename persistence
- machine vs Luna publish copy selection
- reject-story persistence without operator block creation
- safe publication queue integration
- audit records

### Integration tests

- natural request → tool selection → proposal → confirmation → executor result
- source rename example using `ClashReports`
- publish machine translation
- publish Luna translation
- reject story without creating a persistent block
- source enable/disable
- review-only policy change
- Builder request → PR status → merge confirmation

### Dashboard tests

- machine Persian copy appears as primary card content
- direct publish button exists
- Luna translate button remains distinct
- reject button says «رد» and does not imply blocking
- newly arriving story triggers one alarm after audio unlock
- repeated poll does not repeat alarm
- published success removes active card
- failed/queued publication does not prematurely hide card

### Regression rule

No new control-center feature may bypass existing publication, source validation, or Builder CI safety contracts.

## 17. Acceptance criteria

The architecture is complete when all of the following are true:

1. Luna can resolve a natural Persian request to a concrete newsroom capability.
2. Luna can inspect any supported newsroom entity without confirmation.
3. Every mutation produces a preview and requires explicit user confirmation.
4. Confirmation executes the frozen proposed payload, not a fresh interpretation.
5. Luna can rename a source such as `ClashReports` to a Persian display name and the panel updates after confirmation.
6. Luna can publish either machine copy or Luna copy through `v3_publish` after confirmation.
7. Luna can manage source state and routing policy after confirmation.
8. Luna can diagnose a source/workflow issue and propose a fix.
9. Code/UI changes go through Builder branch/tests/PR/CI/merge-confirmation flow.
10. Luna never has unrestricted shell access or direct production-edit access.
11. Incoming stories receive persisted machine Persian copy for dashboard/direct publishing.
12. Dashboard plays a one-shot alarm for genuinely new stories after browser audio unlock.
13. Successfully published stories disappear from the active dashboard but remain in history/audit.
14. Rejecting a story affects only that story and never creates a persistent block/blacklist or source block.
15. All mutations are auditable and Luna never claims success without executor success.

## 18. Non-goals for this phase

- unrestricted autonomous operation without confirmation
- replacing the existing publication queue
- replacing Builder with direct server editing
- giving Luna arbitrary server administration
- creating a generic secret/environment editor
- allowing Luna to silently publish, reject, delete, disable, merge, or deploy without the operator

## 19. Migration approach

The architecture should be introduced incrementally around the existing V4.1 components rather than through a rewrite.

Existing tool handlers, translation logic, publication logic, source management, pending-action storage, audit storage, and Builder integration should be adapted behind the Capability Registry one domain at a time.

The active newsroom must remain usable during migration.