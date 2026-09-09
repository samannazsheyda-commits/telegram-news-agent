# Bikhabar Panel V3 Design

## Goal
Rebuild the VPS-first control panel so it feels like a production newsroom: fast, Persian-first, operationally useful, and directly driven by runtime state rather than slow page rendering or client-side network work.

## Product requirements
- Dashboard must be visually light, clean, professional, RTL, and responsive.
- Live news feed refresh target: 1 second using a lightweight JSON endpoint, no full-page refresh.
- Each feed row shows Persian headline, source, source timestamp, panel-arrival timestamp, relative age, status, and source link.
- Original English text is hidden by default behind an expandable control and must not disturb Persian layout.
- Question headlines, explainers, opinion/analysis/live-blog/article-style items, promotional/context-dependent fragments, and meaningless/incomplete headlines are rejected before they enter the main live feed.
- Batch selection and deletion must work for arbitrary selected rows and select-all.
- Source Manager must support add/remove/toggle/test for Telegram, X/Twitter, Threads, Website/RSS and existing system/Truth sources. Runtime state is authoritative on VPS.
- Operational modules are collapsible cards with preview panels. Preview refresh is non-publishing. Each module has a publish-now action when available.
- Air-traffic preview is always live in the panel, covering Iran + Persian Gulf + Iraq + a small part of Syria. It uses OpenSky first, ADSB.lol and airplanes.live as fallbacks, shows the current detected-aircraft count and active provider, and never fabricates aircraft.
- Air-traffic Telegram snapshots run daily at 18:00 and 00:00 Tehran, including the live map, Persian date/time and detected-aircraft count.
- Weather, air traffic, tanker/Hormuz and market modules expose their preview status without blocking dashboard load.
- Dashboard exposes system heartbeat, last scan, last successful Telegram publish, source health, current poll target and feed freshness.

## Architecture
- Keep Flask/Gunicorn and the current VPS-first runtime.
- Keep heavyweight fetch/translation/analysis inside the agent/runtime. Panel APIs only read prepared runtime JSON and enqueue commands.
- Replace slow or mixed dashboard behavior with small JSON APIs consumed incrementally by JavaScript.
- Preserve current authentication and CSRF behavior.
- Use semantic server-generated timestamps and Persian presentation helpers; do not compute source time from browser receipt time.
- Keep all mutable operational state under the VPS runtime root.

## Live feed data contract
Each `/api/live-feed` item should expose:
- `id`
- `title_fa`
- `original_title`
- `source`
- `source_url`
- `source_time_iso`
- `source_time_fa`
- `arrival_time_iso`
- `arrival_time_fa`
- `age_seconds`
- `panel_status`
- `panel_status_fa`
- `decision_reason_fa`
- `has_original`

The default UI renders only `title_fa` and Persian metadata. `original_title` is only rendered inside an expandable original-text block.

## Editorial ingress rules
Reject before primary live-feed display when any of these apply:
- title is a question (`?`, `؟`) unless it is an attributed direct alert whose factual body is complete;
- English patterns: `why`, `what we know`, `explainer`, `analysis`, `opinion`, `live blog`, `guide`, `timeline`, `everything you need to know`;
- Persian equivalents: `چرا`, `آنچه می‌دانیم`, `تحلیل`, `یادداشت`, `راهنما`, `پرسش و پاسخ` when used as article framing;
- obvious promotional boilerplate or Google News boilerplate;
- context-dependent fragments such as `watch:`, `more:`, `developing:` with no complete factual clause;
- extremely short or structurally incomplete text with no event/action signal.

High-priority missile/attack/explosion/Hormuz alerts remain protected from generic article filters when they contain a concrete event statement.

## Source Manager
Use tabs/cards for Telegram, X, Threads, Website/RSS, Truth and System. A custom source write must immediately update the runtime-backed source JSON used by the agent. Each row shows active state, last check, last error, and a test button. Threads is a best-effort public source using a normalized public handle/URL and indexed/public discovery; its status must be shown transparently.

## Performance budget
- Main HTML should not perform external network fetches.
- `/api/live-feed` should only read local/runtime JSON and format records.
- Feed polling every 1 second, but skip overlapping requests and stop aggressive polling while the tab is hidden.
- Update only changed rows where practical; do not rebuild unrelated dashboard sections.
- Operational preview requests are lazy: only when a preview is expanded or manually refreshed.

## Air-traffic module
- Geographic framing: Iran centered, Persian Gulf fully visible, Iraq visible, only a small western slice of Syria, no unnecessary Europe/Africa zoom-out.
- Show every aircraft returned by the active public ADS-B provider within that viewport; no invented type/classification.
- Display provider, detected count, generated timestamp and map image.
- Refresh panel preview periodically while expanded.
- Telegram scheduler: 18:00 and 00:00 Asia/Tehran.

## Success criteria
- No raw English headline is visible in the default Persian feed.
- Article/question/noise examples are absent from the primary feed.
- A new prepared runtime row appears in the browser within roughly 1–2 seconds under normal VPS conditions.
- Batch delete visibly removes selected rows and persists through the command/runtime path.
- Add/toggle/delete/test source actions return clear success/error state and affect subsequent agent scans.
- All operational modules can expand/collapse without page reload; previews do not publish accidentally.
- Panel remains responsive while agent performs network work.
