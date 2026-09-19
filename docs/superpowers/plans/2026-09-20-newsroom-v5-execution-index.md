# Newsroom V5 — Execution Index and Rollout Order

**Design:** `docs/superpowers/specs/2026-09-20-newsroom-app-luna-v5-design.md`

This index turns the approved V5 architecture into four independently reviewable implementation stages. Each stage gets its own implementation branch/PR, test gate, merge approval, and deployment approval. No stage implicitly authorizes the next one.

## Execution order

1. **Runtime storage and migration**
   - Plan: `2026-09-20-newsroom-v5-runtime-storage.md`
   - Suggested branch: `feat/v5-runtime-storage`
   - Outcome: SQLite/WAL schema, canonical store API, migration/parity tooling.
   - Production behavior: unchanged. Legacy GitHub backend remains default.

2. **Translation/editorial pipeline and publication outbox**
   - Plan: `2026-09-20-newsroom-v5-pipeline-publishing.md`
   - Suggested branch: `feat/v5-pipeline-publishing`
   - Depends on Stage 1 merged.
   - Outcome: translation-first durable processing, exact rejection tombstones, editorial routing, idempotent publication outbox/reconciliation.
   - Production behavior: shadow only initially. Auto-publish remains OFF.

3. **App shell, Review, and real-time UX**
   - Plan: `2026-09-20-newsroom-v5-app-shell-realtime.md`
   - Suggested branch: `feat/v5-app-shell-realtime`
   - Depends on Stage 1 and stable Stage 2 APIs/state contracts.
   - Outcome: local V5 APIs, SSE, unlimited logical Review with cursor/virtual rendering, app-shell navigation and PWA caching.
   - Production behavior: feature-flagged until explicit cutover approval.

4. **Luna operator, chat, and voice**
   - Plan: `2026-09-20-newsroom-v5-luna-chat-voice.md`
   - Suggested branch: `feat/v5-luna-chat-voice`
   - Depends on Stage 1 storage adapter and integrates with Stage 3 shell/context APIs.
   - Outcome: per-turn tool dedupe, model routing, cleaner conversational responses, story context handoff, messenger UI, voice→editable text.
   - Production behavior: feature-flagged until explicit cutover approval; HTTPS is a prerequisite for reliable direct microphone capture.

## Feature flags / rollout controls

Keep the following controls explicit during rollout:

- `NEWSROOM_STORE_BACKEND=github|sqlite`
- `NEWSROOM_V5_SHADOW_PIPELINE=false|true`
- `NEWSROOM_V5_UI_ENABLED=false|true`
- `NEWSROOM_AUTO_PUBLISH_ENABLED=false|true`

Defaults during implementation must preserve current production behavior. In particular, `NEWSROOM_AUTO_PUBLISH_ENABLED` stays false until the operator explicitly approves enabling it after burn-in.

## Pull-request strategy

Use one PR per stage. Every implementation PR follows this sequence:

1. branch from the latest tested `main`;
2. add RED regression/contract tests first;
3. implement only that stage’s scope;
4. run focused tests;
5. run the complete regression suite;
6. open/update PR and wait for required CI checks;
7. report exact evidence (head SHA, CI run, failures/passes);
8. ask for fresh merge approval;
9. after merge and production CI, ask for fresh deployment/cutover approval where deployment is needed.

Do not combine merge and deployment authorization unless the user explicitly authorizes both in the same instruction.

## PR #173 handling

The existing Review hotfix PR #173 predates this V5 architecture. Do not silently merge it into production as part of V5 planning.

At Stage 1 implementation start:

- branch from the latest `main`, not from PR #173;
- inspect #173’s tests/behavior and port only V5-compatible invariants (Persian-ready Review, no English actionable card, Persian-first detail) into the new V5 test suite where they remain useful;
- avoid carrying forward page-render translation or temporary queue behavior that conflicts with translation-first workers;
- once V5 supersedes those fixes and is verified, close/supersede #173 separately rather than pretending it was merged.

## Rollout phases

### Phase A — Storage only

Deploy SQLite code and migration tooling with `NEWSROOM_STORE_BACKEND=github`. Run dry-run migration and parity verification. No operator-visible behavior changes.

### Phase B — Shadow pipeline

Enable `NEWSROOM_V5_SHADOW_PIPELINE=true` with Telegram writes disabled from the V5 path. Compare story identities, Persian readiness, routing outcomes, rejection suppression, and timing against the legacy path.

### Phase C — Runtime store cutover

After parity evidence and explicit deployment/cutover approval, migrate the final delta, switch `NEWSROOM_STORE_BACKEND=sqlite`, keep legacy JSON intact, and keep auto-publish OFF. Verify Review counts/identities and publication history before enabling further V5 features.

### Phase D — V5 app shell

Enable `NEWSROOM_V5_UI_ENABLED=true` only after API/SSE/performance tests are green and production HTTPS/reverse-proxy behavior is verified. Keep a rollback route to V4 while burn-in continues.

### Phase E — Luna V5

Enable the new Luna operator/chat/voice experience after context persistence, tool dedupe, confirmation safety, transcription and frontend contract tests pass. Direct microphone capture is considered production-ready only over HTTPS.

### Phase F — Optional auto-publish

After a burn-in period with observable editorial decisions and zero-loss Review routing, request explicit user confirmation before setting `NEWSROOM_AUTO_PUBLISH_ENABLED=true`. First enablement should use conservative thresholds and anti-flood pacing.

## Rollback contract

A rollback must not destroy new data.

- Preserve legacy JSON snapshots during migration and initial cutover.
- Keep schema migrations forward-compatible and do not delete legacy files during these four stages.
- Feature flags allow disabling V5 UI and shadow/auto-publish independently.
- If SQLite cutover is rolled back, first export/reconcile any terminal decisions and publications created after cutover so a rejected or published story is not resurrected by legacy state.
- Telegram publication history is never rolled back by resending; reconciliation/idempotency remains authoritative.

## Cross-stage verification gates

Before calling the V5 program complete, prove all of the following with fresh evidence:

- no English-only actionable story is visible;
- no placeholder «در حال آماده‌سازی» exists in operator Review;
- all relevant nonduplicate unpublished stories are logically reachable in Review with no business cap;
- exact rejected stories do not return while later stories from the same source remain eligible;
- translation outages retain raw stories and retry rather than lose them;
- publication retries/timeouts cannot duplicate a Telegram post;
- ordinary navigation after app bootstrap does not full-reload the document;
- UI reads/mutations do not wait on GitHub JSON network calls;
- SSE failure has a safe polling/refetch fallback;
- repeated identical Luna tool calls execute once per user turn;
- Luna internal tool mechanics are not rendered in normal chat;
- voice transcription produces editable composer text with file/capture fallback;
- auto-publish remains OFF until explicitly enabled by the operator;
- full regression suite and production smoke checks are green.

## Recommended implementation method

Because the stages are sequential and touch shared state contracts, execute one stage at a time. Within a stage, independent test/adapter tasks may be delegated in parallel only after the canonical interface for that stage is fixed. Do not run Stage 2–4 implementation concurrently against an unstable Stage 1 schema.

The first implementation target is **Plan 1: Runtime Storage and Migration**.