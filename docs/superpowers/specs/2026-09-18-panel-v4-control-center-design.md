# Bikhabar Panel V4 Control Center — Design

## Scope
Panel-only redesign. Do not change Newsroom V3 decision/publish pipeline, V2 runtime, or Air Traffic backend. Air Traffic is removed from the panel UI. Existing Flask/Jinja stack stays in place.

## Product goal
Turn the panel into the daily control center for «بی‌خبر»: fast dashboard, real navigation, news intake/review/archive, sources/settings/health, and a Luna control assistant. The operator should be able to manage routine work without SSH.

## UX
- RTL Persian, mobile-first.
- Slate/charcoal visual language; no full-black heavy theme.
- Minimal blur/animation; no overlapping buttons/text.
- Desktop: compact top navigation + split-view friendly content.
- Mobile: fixed bottom navigation with safe-area and large touch targets.
- One shared V4 shell and one primary V4 stylesheet/JS entrypoint; legacy styles/scripts are not loaded on the V4 shell unless still required by a page-specific feature.

## Primary sections
1. Dashboard — daily quota, regular/special usage, waiting/review/Luna counts, last publish, health indicators.
2. Intake — original title/body, machine preview, state/dedup/relevance, actions.
3. Review — only items needing human decision.
4. Luna — Luna queue/final outputs and Luna Assistant.
5. Published — searchable/filterable archive.
6. Sources — enable/disable, health, last fetch, error, priority/category/canonical name.
7. Settings — quota, special quota, publish mode, interval, keywords/categories, Luna/translation/Telegram health.
8. System — human-readable diagnostics, provider health, recent errors, audit log.

## Manual story flow
Original -> machine preview -> Send to Luna -> Luna final preview -> Publish/Edit/Reject.
There is no direct “publish with Luna” action before the Luna preview exists.

## News card states
Before Luna: source/time, original, machine preview, Luna=not reviewed, state/importance, actions: Send to Luna / Reject / Source.
After Luna: importance, decision, reason, final Persian title/body, actions: Publish / Edit / Reject.

## Luna Assistant
Luna Assistant is a panel control surface, not decorative chat. The panel exposes explicit action endpoints/tools for safe reads and controlled writes. Sensitive actions require confirmation. Initial supported intents in V4 UI: explain daily status/silence, read stats/health, update regular/special quota, list recent published items, disable/enable one source, and finalize a selected story with Luna. Actions must be auditable.

## Safety
- Publish/delete/reset/restart/bulk source disable require confirmation.
- Manual publish must use existing safe publish command path and must not bypass duplicate/accounting logic.
- Do not expose secrets.
- Authentication remains session-based; no permanent auth bypass is added to repo.

## Performance
- Dashboard renders at most 30 intake cards initially.
- Archive/review use pagination or bounded rendering.
- Machine/Luna translation is lazy; no heavy Argos preload in request path.
- No huge DOM, no heavy mobile blur, no page-wide animation loops.

## Air Traffic
No Air Traffic card, tab, preview button, or panel action in V4. Backend/service removal is outside this panel-only branch.

## Compatibility
Reuse existing Flask routes/data stores and panel command queue wherever possible. Add panel-only presentation/service helpers rather than changing Newsroom V3 production logic.

## Verification
- Flask/Jinja render tests assert V4 branding/nav, no Air Traffic, no direct Luna publish-before-preview, correct quota/health surfaces.
- JS syntax checks.
- Full pytest regression via PR CI.
- Browser/mobile visual verification after deployment is a separate VPS step.