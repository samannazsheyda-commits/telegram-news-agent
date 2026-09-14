# Bikhabar V3 Mobile Newsroom Panel Design

## Goal
Build a fast, private, single-admin newsroom control panel for Bikhabar that is optimized for mobile web, works equally well on desktop, talks directly to the VPS/runtime, and gives the editor safe real-time control over Newsroom V3 without using GitHub as an operational intermediary.

## Approved product decisions

- Single administrator only; no roles or multi-user workflow.
- Mobile-first responsive UX; desktop uses the same product with a denser combined layout.
- Dark, premium visual system with Bikhabar red as the primary accent.
- Home screen is a combined newsroom: live feed and urgent actions first, then metrics, health, modules, sources, and settings.
- Every live story exposes direct editorial actions: publish, edit, reject, open source.
- Operational architecture is VPS-first. GitHub remains source control/deployment only.
- Destructive or high-risk actions require a short confirmation step: publish, reject, emergency stop/resume, source deletion.
- Low-risk actions are direct: edit, open source, refresh/scan, preview.
- Live feed auto-refreshes and clearly marks new/high-priority items; sound notification is optional and muted by user choice.

## Current-system constraints

The production panel is Flask/Jinja served by Gunicorn on the same VPS and uses `LocalJsonRepository` when `PANEL_LOCAL_ROOT` is present. The current panel already has authenticated local APIs, command files under `panel_commands`, result files under `panel_results`, live-feed data, source management, settings, module previews, and manual editorial routes.

Newsroom V3 is already the production publisher. The redesign must not change V3 publication safety guarantees, Canary evidence, Telegram duplicate protection, or ancillary Weather/Air-Traffic services.

The VPS is memory constrained, so the panel must avoid a heavy front-end runtime or build server.

## Architecture options considered

### A. React/Vite SPA
A full SPA would make component composition pleasant and could support richer client state, but it adds a build pipeline, more static assets, more JavaScript, and more deployment surface on a small VPS. It is unnecessary for a single-admin panel.

### B. Cosmetic refresh of the existing dashboard
This is the lowest-risk path but preserves the current large `live.js`, overlapping CSS layers, duplicated status calls, and page-centric editorial workflow. It would look better without materially improving maintainability or operational speed.

### C. Flask/Jinja shell + focused JSON APIs + modular vanilla JS — chosen
Keep Flask, Jinja, CSRF/session authentication, Gunicorn, and the local runtime repository. Replace the current visual shell and split client behavior into small modules. Use one lightweight snapshot endpoint for periodic state refresh and dedicated POST endpoints for actions. This gives a newsroom-quality UX without adding a framework or another daemon.

## Information architecture

### Primary navigation
The private navigation has four destinations:

1. **اتاق خبر** — live desk and daily control surface.
2. **بررسی** — stories intentionally moved into manual review/editing.
3. **منتشرشده‌ها** — publication history and outcomes.
4. **منابع** — source health and source management.

On mobile this becomes a persistent bottom navigation with large touch targets. On desktop it becomes a compact top/side newsroom navigation while preserving the same destinations.

### Home / اتاق خبر hierarchy

The page is ordered by editorial urgency:

1. Compact top status: V3 active/stale, Telegram healthy/error, publication enabled/paused, last cycle.
2. Breaking/live feed.
3. Quick control row: scan now, publication stop/resume.
4. Compact KPIs: new, review queue, published today, rejected today.
5. Module operations: weather, air traffic, tanker, market.
6. Source/priority summary.
7. System health and advanced settings in collapsed sections.

The editor should be able to understand system health and act on a story without scrolling through configuration first.

## Live story card

Each card shows only information needed for a newsroom decision:

- priority indicator (`فوری`, `مهم`, normal) when supported by data;
- Persian headline;
- compact source label and relative discovery time;
- editorial/system state;
- short body/snippet only when available;
- actions: `انتشار`, `ویرایش`, `رد`, `منبع`.

Published/terminal stories cannot expose a second publish action.

### Direct actions

**Publish**
- Confirmation sheet/dialog shows final headline and source.
- Panel sends a command to the existing local command queue rather than calling Telegram directly.
- UI enters `در صف` then polls the command result.
- Success is shown only after the runtime returns a successful command result.
- Ambiguous/failed publish never renders as success and never triggers an automatic retry from the browser.

**Edit**
- Opens an inline mobile sheet / desktop side drawer rather than navigating away where practical.
- Saves the story into the manual-review queue with final Persian title/body.
- Publish from the editor still uses the V3 command path.

**Reject**
- Requires confirmation.
- Writes the existing manual-reject history state and removes the item from the actionable live feed.
- It never deletes Telegram content.

**Source**
- Opens the original source in a new tab/window immediately.

## VPS-first API design

The panel must read/write the local runtime backend only in VPS deployment. GitHub data access stays available for tests/development compatibility but is not part of the production interaction path.

### New consolidated snapshot endpoint

`GET /api/newsroom/snapshot`

Returns a single payload containing:

- `engine`: `v3`, `v2_fallback`, or unknown;
- `agent_state` and `last_cycle_at`;
- `telegram_state`;
- `publishing` and `emergency_lock`;
- V3 production status including `reason`, `error`, `sources_ok`, `sources_failed`, `items_fetched`, `published`, `publish_failed`, latest Telegram message ID;
- counts for live/review/published/rejected;
- latest live story summaries;
- module status summaries;
- current priority terms;
- `snapshot_at` and a monotonically useful version/fingerprint.

The endpoint reads `newsroom_v3_production_status.json` directly when available so the UI reflects the current production engine rather than legacy V2-only state fields.

### Action endpoints

Existing command-center endpoints are retained where safe, but the UI contracts are normalized:

- `POST /api/newsroom/scan`
- `POST /api/newsroom/publishing`
- `POST /api/newsroom/live/<id>/publish`
- `POST /api/newsroom/live/<id>/review`
- `POST /api/newsroom/live/<id>/reject`
- `GET /api/newsroom/command/<id>`

These may delegate internally to the existing command-center helpers to avoid two operational implementations.

Every action response returns a stable shape:

```json
{
  "ok": true,
  "status": "queued|succeeded|failed|ambiguous",
  "command_id": "...",
  "message": "..."
}
```

No browser endpoint gets the Telegram bot token.

## Refresh model and performance

Use lightweight polling rather than WebSockets/SSE:

- active visible page: every 3 seconds;
- hidden/background page: every 15 seconds;
- immediate refresh after an action finishes;
- abort the previous fetch if a newer refresh starts;
- do not repaint unchanged story cards when the snapshot fingerprint is unchanged.

This is intentionally simpler and safer than holding streaming Gunicorn connections and is more than sufficient for one administrator.

Target behavior:

- first meaningful mobile render from server-side HTML without waiting for JavaScript;
- no front-end framework;
- no external UI/CDN dependency required for the core panel;
- no full-page refresh for routine newsroom actions;
- touch targets at least 44px;
- avoid loading all publication history into the dashboard response.

## Visual system

### Theme

- near-black graphite background;
- elevated charcoal surfaces;
- Bikhabar red reserved for live/urgent/danger/accent states;
- muted warm-gray typography for metadata;
- high-contrast white primary text;
- subtle borders and shadows rather than glass-heavy blur.

### Typography and density

- Persian-first RTL layout.
- Headline hierarchy dominates ornamental UI.
- Mobile cards are compact but not cramped.
- Desktop uses a two-column newsroom: live desk as the dominant column and operations/health as the secondary rail.

### Feedback states

Every asynchronous button must visibly move through:

`آماده → در حال ارسال → در صف → انجام شد / خطا`

Actions disable while in-flight to prevent duplicate requests. Success toasts never appear before a runtime result confirms success.

## Mobile interaction details

- Sticky bottom navigation.
- Sticky compact system-status bar at the top of the newsroom.
- Story actions remain thumb reachable.
- Confirmation uses a bottom sheet style on narrow screens and modal/dialog style on desktop.
- Inline editor uses a full-height sheet on mobile and side drawer on desktop.
- Source links remain one tap.
- Sound notification is off/on persisted in local storage; no autoplay assumption.

## Desktop interaction details

At desktop widths, the home page becomes a combined editorial workstation:

- left/main: live feed and review actions;
- right rail: V3 health, publication state, quick commands, modules;
- lower sections: source priorities and advanced settings.

No desktop-only feature is required for correctness; mobile and desktop expose the same operational capabilities.

## Source manager

Source management stays a separate destination but adopts the same visual system. It must expose source state clearly, keep add/edit actions simple, and protect source deletion with confirmation. Source deletion must not be bundled with unrelated runtime changes.

## Security

- Existing admin session login remains the only user model.
- CSRF remains required on state-changing requests.
- Session cookie remains HTTP-compatible under current deployment and can switch to secure cookies behind future HTTPS.
- No secrets are rendered to HTML/JSON.
- Production API writes are authenticated by the existing admin session.
- Destructive actions reject malformed IDs and unknown commands server-side; browser confirmation is UX protection, not authorization.

## V3 publication safety

The panel is an operator interface, not a second publisher.

- It must enqueue publication through the runtime command path.
- It must not call `send_telegram` directly for live/manual V3 publication.
- It must preserve the V3 rules around ambiguous Telegram state, duplicate prevention, retry cooldowns, and at-most-one write semantics where applicable.
- It must not modify/delete the V3 Canary marker.
- It must not trigger V2 production publication while V3 is active.

The old manual review route that directly calls Telegram should be migrated to the same V3 command path before the redesigned UI treats it as a supported publish flow.

## Code organization

Keep server responsibilities small and client modules focused.

Proposed server files:

- `panel/newsroom_api.py` — snapshot and newsroom action HTTP contract; delegates existing command/runtime helpers.
- `panel/newsroom_view.py` or existing `app.py` route — server-rendered initial newsroom state.
- `panel/command_center.py` — remains command/settings implementation, reduced only where duplication is removed.

Proposed client files:

- `panel/static/newsroom-shell.css` — single primary newsroom design layer replacing the current stack of overlapping newsroom styles.
- `panel/static/newsroom-live.js` — snapshot refresh and story rendering.
- `panel/static/newsroom-actions.js` — action requests, confirmations, command-result polling.
- `panel/static/newsroom-editor.js` — inline edit sheet/drawer.
- `panel/static/newsroom-ui.js` — navigation, toasts, sound preference, small UI utilities.

Templates:

- `panel/templates/base.html` — responsive shell/navigation.
- `panel/templates/dashboard.html` — editorial workstation.
- `panel/templates/review_queue.html`, `review_edit.html`, `history.html`, `source_manager.html` — visual consistency and migration to shared components.

Existing old `dashboard/` static GitHub-browser dashboard is not used as the production panel and is outside the redesign unless tests prove it is still deployed somewhere.

## Testing strategy

All behavior changes use TDD.

Server tests cover:

- authenticated snapshot payload with real V3 production-status fields;
- snapshot behavior when V3 status is missing/stale;
- live publish creates exactly one local command and does not call Telegram directly;
- direct manual-review publication uses V3 command path;
- reject is terminal and removes actionable live state;
- already-published item cannot be republished;
- emergency stop/resume updates the settings used by V3;
- command-result states including failed/ambiguous are surfaced truthfully;
- CSRF/admin protection remains intact.

UI contract tests cover:

- required mobile navigation and action controls exist;
- old overlapping stylesheets are no longer loaded after migration;
- story cards expose source/edit/publish/reject controls;
- confirmation hooks exist for destructive actions;
- no Telegram token or secret appears in rendered output.

Regression suite must continue to pass before merge.

## Deployment

Deployment stays on the existing path:

1. feature branch and pull request;
2. full CI and panel checks;
3. merge to `main` only after green checks;
4. existing pipeline promotes tested main to `production`;
5. VPS updater deploys the production SHA;
6. verify `bikhabar-panel.service=active` and `bikhabar-agent.service=active`;
7. live probe the panel login, snapshot endpoint, and one non-Telegram action such as scan/status;
8. verify no duplicate Telegram write was caused by deployment.

## Acceptance criteria

The redesign is complete when:

1. The first page on mobile feels like an operational newsroom rather than a settings dashboard.
2. V3/Telegram/publication health is visible immediately and reflects current V3 production state.
3. A story can be opened, edited, published, rejected, or sourced without a full-page workflow jump.
4. Publish/reject/stop require confirmation and duplicate clicks are prevented.
5. Publication success is shown only after runtime confirmation.
6. Production panel actions operate on local VPS state/commands, not GitHub Actions.
7. Manual publication no longer bypasses V3 by calling Telegram directly.
8. Mobile and desktop expose the same capabilities; desktop uses the approved combined layout.
9. The panel remains lightweight enough for the current VPS and does not introduce a Node/SPA production runtime.
10. Full tests and deployment validation pass, then live VPS evidence confirms the new panel SHA and healthy services.
