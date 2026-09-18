# Newsroom Panel V4 — Design

Date: 2026-09-18
Status: approved scope, implementation branch `feat/newsroom-panel-v4`

## Goal
Turn the existing Bikhabar panel into the primary daily control surface for the newsroom without changing the V3 publishing pipeline itself. The operator should be able to understand newsroom state, inspect news, request Luna finalization, manage sources/settings, diagnose silence/errors, and perform safe actions without SSH.

## Non-goals
- Do not modify the V3 waiting/ready decision pipeline in this workstream.
- Do not restore Air Traffic.
- Do not make V2 the production main path.
- Do not add a second independent backend pipeline for the panel.
- Do not make machine translation a hard prerequisite for publishing.

## Architecture choice
Keep Flask + Jinja + the existing panel blueprints/services. Reuse working actions from `panel/newsroom_api.py`, `panel/live_api.py`, `panel/command_center.py`, and `panel/source_manager.py`. Replace the accumulated presentation layer with a single V4 shell instead of stacking another patch on top of legacy CSS/JS.

Rejected alternatives:
1. Incrementally patch the existing V3 shell. Rejected because multiple overlapping CSS/JS generations already exist and are a likely source of conflicts and mobile lag.
2. Rewrite the panel as a React/Vue SPA. Rejected because it adds build/deployment complexity without a product need; the current Flask API surface is sufficient.

## V4 information architecture
Desktop uses a professional sidebar/top-level workspace layout. Mobile uses a real bottom navigation with safe-area support.

Primary destinations:
1. Dashboard
2. Incoming
3. Review
4. Luna
5. Published
6. Sources
7. Settings
8. Health / Errors

Luna Assistant is available as a persistent side panel on desktop and a dedicated sheet/page on mobile.

## Visual system
- RTL-first Persian UI.
- Charcoal/slate surfaces, not full black.
- One restrained accent system for status and actions.
- No heavy backdrop blur on mobile.
- Minimal gradients and animation.
- 44px+ touch targets.
- No fixed elements that overlap content.
- Clear active navigation state.
- Consistent spacing scale and button hierarchy.
- Accessible contrast and readable typography.

## Dashboard
Dashboard must expose real operational truth, not decorative counters:
- regular published today / regular daily quota
- regular remaining
- pending human review
- pending/processed Luna count where available
- rejected today
- special news used / special quota where available
- active sources
- last publication
- Agent health
- Luna/provider health
- Telegram health
- latest cycle state/reason

All values come from existing state/store data or a thin panel aggregation layer. Nothing is hardcoded except explicit defaults when no value exists.

## Incoming news
Paginated/lazy list, approximately 20–30 rows per page/view. Each item shows:
- canonical/display source
- time
- original title/body
- machine translation preview
- current state
- dedup/relevance metadata when available
- source URL
- actions

The list must not render all candidates at once.

## News card states
Before Luna:
- original content
- `🌐 ترجمه ماشینی`
- Luna state: not reviewed / processing / failed
- importance if known
- actions: `ارسال به Luna`, `رد`, `باز کردن منبع`

After Luna:
- `🧠 Luna Final`
- decision
- importance
- Persian reason
- final Persian title
- final Persian body
- actions: `انتشار`, `ویرایش`, `رد`

There must be no direct “publish with Luna” action that skips preview.

## Manual editorial flow
Original → machine preview → operator decision → send to Luna → Luna final copy → preview → publish/edit/reject.

If machine translation fails, the card shows `ترجمه ماشینی موقتاً در دسترس نیست`; Luna remains usable and the UI must not hang.

## Review
Dedicated list for items that actually need a human decision. Reuse the existing review queue where possible, but render it through the V4 shell and unified card/action system.

## Luna workspace
Shows Luna queue, processing state, completed finalizations, failures, and provider/fallback state where available.

Luna actions must be asynchronous from the user’s perspective: button state changes to queued/processing, the UI remains responsive, and completion is reflected by lightweight polling or existing snapshot mechanisms.

## Published archive
Real archive with:
- today/week filters
- source filter
- search
- Telegram message ID
- publication time
- final text
- status

Use pagination; do not render the entire archive.

## Sources
Source management exposes:
- enabled/disabled
- health
- last successful receive
- error summary
- priority
- category
- canonical source name
- provider/source identity

Existing source-manager behavior should be reused rather than duplicated.

## Settings
Settings must remove ordinary SSH dependence for:
- regular daily quota
- special quota
- auto publish
- manual approval mode where supported
- minimum publish interval
- categories
- keywords
- source priorities
- Luna/provider settings that are safe to expose
- machine translation behavior
- Telegram operational state
- health/retry controls

Secrets are never rendered or returned to the browser.

## Health and error center
Translate operational state into short human explanations. It should answer questions such as:
- why has nothing been published recently?
- is Telegram failing?
- is Luna/provider failing?
- is quota full?
- are candidates all duplicates/rejected?
- are sources failing?

Raw technical details may be expandable, but the primary text is human-readable Persian.

## Luna Control Assistant
Luna Assistant is an operational assistant, not a decorative chat box.

Supported read actions should include:
- dashboard stats
- agent/provider health
- candidates
- source state
- recent errors
- recent publications

Supported controlled actions should include:
- update regular quota
- update special quota
- enable/disable a source
- update keywords/categories/priorities
- finalize a selected story with Luna
- reject/edit a story
- publish a reviewed story
- safe retry/restart actions where already supported

Sensitive actions require explicit UI confirmation before execution: publish, delete, mass source changes, reset, restart.

## Audit log
Every user/Luna/system action recorded with:
- timestamp
- actor (`user`, `luna`, `system`)
- action
- target
- before
- after
- result

The log must be queryable from the panel.

## Authentication
Remove the temporary always-true VPS bypass from the final deployed version. Keep the existing password/session design as the baseline, with rate limiting and secure cookies. The panel should remain simple to enter but not public/anonymous.

## Performance strategy
- consolidate active V4 styles/scripts instead of loading multiple legacy generations
- first page fast
- immediate navigation state
- pagination 20–30 items
- lazy translation/media
- cache lightweight snapshot reads
- debounce search
- lightweight DOM
- no heavy mobile blur
- no all-record rendering
- avoid heavy offline translation model preload in the HTTP request path
- controlled polling with fingerprint/no-op updates when data is unchanged

## Air Traffic removal
V4 contains no Air Traffic card, preview, route, navigation item, action, or API module exposure. Legacy files/services may be removed separately, but the V4 panel must not reference them.

## Compatibility boundaries
This panel project may read existing V3 state and invoke existing safe command/API actions. It must not change the V3 candidate decision algorithm in order to make the UI look healthier.

## Planned panel files
Primary changes:
- `panel/templates/base.html`
- `panel/templates/dashboard.html`
- V4 templates for incoming/luna/health/settings/archive as needed
- `panel/static/newsroom-v4.css`
- `panel/static/newsroom-v4.js`
- `panel/newsroom_api.py` for panel-only aggregation/actions
- `panel/app.py` for V4 routes/auth integration
- source/settings templates only where required
- panel tests

Legacy CSS/JS will stop being referenced once equivalent V4 behavior is covered; deletion can follow after verification.

## Testing
Panel tests must cover:
- navigation and active states
- mobile navigation markup/safe-area classes
- real dashboard stats and quotas
- machine translation failure state
- Luna preview state
- publish confirmation flow
- reject/edit flow
- source toggle
- settings updates
- Luna Assistant confirmation boundaries
- health/error rendering
- Air Traffic absent from UI/API snapshot
- pagination limits
- authentication

Performance verification should include 100 candidates and 1000 archive records without huge DOM/OOM/worker kill behavior.

## Definition of done for this panel workstream
- V4 shell is the only active newsroom presentation layer
- mobile and desktop navigation work end-to-end
- no button/text overlap
- dashboard uses real values
- machine translation and Luna final copy are visually distinct
- manual Luna flow always previews before publish
- sources/settings work without SSH for supported settings
- health/error center explains failures in Persian
- Luna Assistant can perform supported panel actions with confirmations
- audit log exists
- Air Traffic is absent from the panel
- panel tests pass
- production panel deploy is verified on mobile and desktop
