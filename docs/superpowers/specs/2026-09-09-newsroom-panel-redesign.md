# Bikhabar Newsroom Panel Redesign

## Goal
Replace the decorative command-center dashboard with a real 24/7 Persian newsroom panel whose controls, previews, feed actions, command status, and health indicators reflect actual backend state.

## Approved user-facing requirements
- Rename all command-center copy to «اتاق خبر بی‌خبر» / «اتاق خبر».
- Keep the 24/7 priority strip static: no add/remove/edit controls.
- Make stop/resume publishing and immediate scan show real command progress and final success/failure state.
- Operational modules: weather, air traffic, tanker/Hormuz, market. Clicking a module opens its preview inline; clicking again closes it. Preview must not remain permanently open.
- Module preview is the exact publication payload when available, with refresh and publish actions separated.
- Agent settings must persist to the runtime settings store and show saved/dirty state.
- Health must come from backend data/heartbeat/command results, never static green copy.
- Live feed must prefer Persian text. Original English is secondary/collapsible only.
- Every live item exposes useful actions: source, edit/review when queued, delete from live feed, and final Telegram output preview when available.
- Final Telegram output must be visible in the panel, including source timestamp/link/footer when the runtime has produced it.
- New live item arrival plays one short ding when sound is enabled.
- Fast 24/7 behavior: JSON API polling at 1 second for live feed and command status, 2 seconds for health/status; no full-page HTML refresh.
- Menu/navigation copy and hierarchy must be fully Persian and visually simpler.

## Architecture
- `panel/live_api.py` becomes the read API for localized live-feed records and final-output fields.
- `panel/command_center.py` owns command submission, command-result lookup, status/health, module preview read API, and persisted settings.
- The VPS agent continues consuming `panel_commands/*.json` and writing `panel_results/*.json`; the browser follows result state until terminal.
- Existing weather preview JSON remains the source for weather. Other modules expose the latest persisted preview/snapshot payload when available; absence is explicitly shown as unavailable rather than fabricated.
- `dashboard.html` becomes a compact single-page newsroom shell. `live.js` renders feed rows, details, previews, settings state, ding alerts, command progress, and health from JSON.

## Safety / truthfulness
- Never show a module as healthy or available unless backend state supports it.
- Never fabricate preview values, tanker counts, Telegram state, or VPS health.
- Unknown/unavailable data is shown as «نامشخص» or «پیش‌نمایش موجود نیست».
- English originals may exist only behind an explicit «متن اصلی» disclosure.
