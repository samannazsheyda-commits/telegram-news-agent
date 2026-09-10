# Bikhabar Monitoring Panel Recovery Design

## Goal
Turn the current newsroom page into a fast, Persian, operational monitoring room whose controls reflect real agent state and whose live-feed actions persist correctly.

## User-facing requirements
- Rename the product surface from «اتاق خبر بی‌خبر» to «اتاق مانیتورینگ بی‌خبر» everywhere in the panel navigation/title/header.
- Keep the 24/7 priority area visible but make its priority phrases/keywords editable: add, remove, reorder, and persist them. Runtime urgency sorting must read the same persisted list. Preserve the core order: missiles from Iran, missiles toward Iran, direct war/attacks, Strait of Hormuz, explosions; then drones, warships, tankers, seizure/sinking, nuclear/military/airspace. Also preserve the broader editorial categories already used by the project: جنگ و تحولات نظامی، بازار ارز و طلا، نقشه و ترافیک هوایی، قیمت روز خودرو، قیمت روز موبایل، تحریم و اقتصاد.
- Make Agent / last scan / Telegram / publishing status use a dedicated runtime heartbeat file. Never show a guessed green state.
- Make «اسکن فوری» run the current V2 news intake, not the legacy scanner, and return a terminal command result.
- Live feed refresh target remains fast (about one second in the panel; production agent polling remains 2 seconds) with a short ding for new arrivals.
- Selection must survive live-feed refreshes. Bulk delete must remain selected until the operation completes.
- Deleting a live item must create a durable dismissal tombstone so that the same item does not return on the next scan.
- Live cards are Persian-first and expose final Telegram output; original English is optional/collapsible only.
- Weather, air traffic, Hormuz/tanker, and market cards are toggleable previews. Opening a preview requests a fresh build; clicking again closes it. Air traffic preview must create a fresh live map snapshot and must not reuse the previous image as if it were current.
- Agent settings must move to the bottom and use a compact collapsible presentation.
- Sources, review, and history pages must be Persian-first, lighter/readable, mobile-friendly, and must not become blank because one optional field is missing.
- Keep Doran as the first CSS font family without bundling or distributing the font file.

## Architecture
1. Add `data/runtime_health.json` as the single panel heartbeat contract written atomically by the VPS runtime after every cycle.
2. Add `data/panel_dismissed.json` as a durable live-item tombstone store; `LiveFeedStore.upsert()` refuses dismissed IDs/URLs.
3. Store editable priorities inside `data/newsroom_settings.json` under `priority_rules`; command-center settings API validates and persists them. `newsroom_v2` uses them when scoring urgency.
4. Route manual scan through the current V2 runtime and return a normal `panel_results/<command>.json` result.
5. Keep panel APIs JSON/no-store; JavaScript maintains selection state client-side and requests preview rebuilds before rendering.

## Safety / correctness
- Do not fabricate tanker counts, air traffic, health status, timestamps, or Telegram health.
- Do not publish from preview builders.
- Do not expose tokens/passwords/secret environment values.
- Source times are preferred over discovery/send times for news freshness.
