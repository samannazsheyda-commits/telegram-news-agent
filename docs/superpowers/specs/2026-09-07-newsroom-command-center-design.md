# Newsroom Command Center Design

## Goal
Turn the existing static GitHub Pages review panel into a Persian-first newsroom command center for «بی‌خبر» while preserving the current GitHub-file command architecture and Telegram publication workflow.

## Visual direction
Use direction C: a dense professional newsroom mixed with a minimal premium UI. The interface remains dark, information-first, and RTL. Red is reserved for breaking/critical states; green for healthy/publish; amber for hold/warning. Doran NoEn ExtraBold is the intended display typeface for headlines, counts, tabs, and key labels. Because uploaded font binaries must not be published from this chat, CSS must reference the local family name first and use a close web-safe Persian fallback if the font is unavailable.

## Main layout
1. Command bar: agent health, last scan, latest source timestamp, fresh-news count, broken-source indicator, Telegram/system health, and Scan Now.
2. Live Feed / Decision Queue: today-only pending stories, sorted by real source time, searchable and filterable.
3. Situation rail: breaking count, newest story, source health summary, market/earthquake placeholders from current available state, system warnings.
4. Management views: pending, processing, published, rejected, analytics, sources/settings, system/audit.

## Story card
Each story shows Persian headline, Persian body, localized source label, source time, priority, category, duplicate/update signal, and source link behind a Persian label. Main actions: Publish, Reject, Hold, Edit/advanced. A Telegram preview renders the exact outgoing Persian-only visible format. English source names or raw URLs must never be displayed in Telegram output; the actual URL is only the href behind «لینک منبع خبر».

## Bulk operations
Every list view includes «پاک کردن همه» and «پاک کردن نتایج فیلترشده». Bulk operations show a two-step confirmation with item count. Clearing published/rejected history only clears panel history; it does not delete Telegram messages. Clearing pending moves items to terminal history as superseded rather than silently losing auditability.

## Settings
A newsroom settings view exposes: source enable/priority/trust, topic mode (auto/review/ignore), freshness window, duplicate strictness, auto-publish master switch, quiet mode, earthquake thresholds, market toggles, NOTAM sensitivity, X account mode, Telegram output preferences, emergency lock, compact/comfortable density, alerts, and local UI preferences. Initial version persists operational settings in `data/newsroom_settings.json` through the existing command-file workflow; unsupported runtime controls are clearly marked as panel preferences rather than pretending to control the agent.

## Safety and audit
Dangerous actions require confirmation. Emergency Lock disables auto-publish intent in settings and is prominent. Every settings save and bulk clear command writes a terminal `panel_results` record; editorial movements continue to be represented in history. Existing secrets stay server-side/browser-local; no token is committed.

## Analytics
The dashboard computes from queue/history/state already available: today reviewed, today published, today rejected, pending, processing, duplicate/superseded count, source mix, category mix when available, and recent activity. No fake metrics are shown; unavailable metrics render «داده کافی نیست».

## Architecture
Keep `docs/panel.js` as the compatibility layer for authentication, existing publish/reject/refresh, and data loading. Add `docs/newsroom-v1.js` as a UI/controller enhancement and `docs/newsroom-v1.css` for the redesigned shell. Extend `src/panel_command_file.py` with non-destructive newsroom commands (`clear`, `settings_save`) and store settings in `data/newsroom_settings.json`. Update the command workflow snapshot/merge list to persist settings.

## Success criteria
- Persian-first UI, Doran-first display typography, polished desktop/mobile layout.
- Real refresh still works.
- Publish/reject still work with current backend.
- Bulk clear works per view and filtered pending lists with two-step confirmation.
- Settings can be saved and reloaded through GitHub commands.
- No raw English source label or visible raw URL in Telegram manual publication.
- Tests cover the new command actions, panel contracts, and format invariants.
