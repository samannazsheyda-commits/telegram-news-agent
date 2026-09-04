# Editorial Panel Design

## Goal

Add a simple, mobile-friendly, single-admin web panel to the existing Telegram news agent so the automated system keeps working normally while the owner can manually review rejected news, edit Persian copy, approve and publish immediately to `@bikhabaar`, and manage additional website and X/Twitter sources without editing code.

## Product Principles

- The existing automated news pipeline remains the primary system and continues to run independently.
- The panel is an optional control surface, not a replacement for the bot.
- Single admin only; no roles, teams, invitations, or user-management system.
- Keep the UI extremely simple and usable from Android/mobile.
- Prefer a free hosting/deployment path and avoid paid APIs where possible.
- Manual publication must be immediate after confirmation.
- No rejected item should silently disappear; every editorial decision must be inspectable.
- Existing source-verification and no-invention rules remain in force.

## Main User Flows

### 1. Review Queue

The panel home screen contains a prominent `نیاز به بررسی` queue. Each card shows:

- source name
- original headline
- Persian headline if translation exists
- Persian summary/detail if translation exists
- source publication time
- original source link
- rejection reason
- current status

Opening a card displays an edit screen. The admin can edit the Persian headline and Persian body before publishing.

Actions:

- `تأیید و انتشار`: validates the edited Persian text, publishes immediately to `@bikhabaar`, marks the item as manually published, and stores the final published copy.
- `رد نهایی`: marks the item as intentionally rejected and removes it from the active review queue while keeping it in history.

Manual approval bypasses the automatic editorial rejection reason for that specific item, but does not bypass basic safety/data-integrity checks: a source URL and identifiable source must still exist, and empty Persian copy cannot be published.

### 2. Source Management — Websites

A `منابع` section includes a website-source list. The admin can add a source using:

- display name
- website URL
- optional RSS/feed URL

On save, the system tries the provided feed first. If no feed is supplied, it performs best-effort feed discovery from the website. Sources have:

- active/inactive toggle
- detected feed URL when found
- last successful check time
- last error summary
- delete action

New website sources join the same Iran-related discovery pipeline. They do not automatically become trusted enough to publish every item: ordinary editorial quality and Iran relevance checks still apply. Their rejected candidates appear in the review queue.

### 3. Source Management — X/Twitter Accounts

The same `منابع` section has an X/Twitter subsection. The admin can add an account using a handle such as `@BarakRavid`.

Each account has:

- display/handle
- active/inactive toggle
- last successful discovery time
- last error/status
- delete action

To preserve the free architecture, the implementation must not require the paid X API. Discovery remains best-effort through publicly accessible/indexed sources, consistent with the current project approach. Only Iran-related discovered posts enter the candidate pipeline.

### 4. Dashboard

The top-level dashboard should expose only the information needed for daily operation:

- count of items waiting for review
- count published today
- count rejected today
- bot status / last completed check
- last Telegram publication time
- quick links to `نیاز به بررسی`, `منتشرشده‌ها`, `ردشده‌ها`, and `منابع`

No analytics suite, charts, multi-user activity logs, or unrelated administration features are required in the first version.

## Architecture

### Existing Agent

The current GitHub Actions agent remains responsible for scheduled polling, automatic editorial filtering, translation, automatic Telegram publication, market/weather/car tasks, and persisted state.

### New Panel Application

Add a small web application within the same repository. It should be independently deployable while importing shared project logic rather than duplicating news formatting or Telegram-send behavior.

Suggested responsibility split:

- `src/editorial_store.py`: normalized persisted representation for review items, final decisions, and custom sources.
- `src/custom_sources.py`: load/validate custom website and X source definitions and expose them to the existing source collector.
- `src/manual_publish.py`: validate edited copy, reuse Telegram formatting/sending rules, record successful manual publication, and guard against double publication.
- `panel/app.py`: HTTP application and routes.
- `panel/templates/`: minimal server-rendered mobile-friendly UI.
- `panel/static/`: only minimal CSS/JS needed for usability.

Avoid a heavy frontend framework unless implementation constraints make it necessary. A server-rendered interface is preferred for simplicity and reliability.

## Persistence Model

The current `state.json` should not become the only database for all panel content because it already carries runtime bot state and is frequently rewritten by Actions.

Use separate repository-backed JSON data files for the first free version:

- `data/editorial_queue.json`
- `data/editorial_history.json`
- `data/custom_sources.json`

The data layer must use atomic reads/writes and deterministic IDs. Concurrent writers must merge safely rather than overwrite unrelated updates.

### Review Item Fields

Each review record contains at minimum:

- `id`
- `news_key`
- `source`
- `source_url`
- `original_title`
- `original_summary`
- `persian_title`
- `persian_body`
- `published_at_source`
- `discovered_at`
- `rejection_reason`
- `status` (`pending`, `published_manual`, `rejected_manual`, `published_auto`, `superseded`)
- `final_persian_title`
- `final_persian_body`
- `decision_at`

The queue should retain the full human-readable candidate, not only a hash.

## Integration With Automatic Editorial Pipeline

When the automatic pipeline rejects a current, source-backed candidate for an editorial reason, it should upsert that candidate into `editorial_queue` with the exact rejection reason.

Items rejected solely because they are stale, malformed, missing a reliable source, or lack a valid publication time should still be auditable, but may be stored as non-actionable history rather than cluttering the active approval queue.

When an item is automatically published, any matching pending review record must be marked `published_auto` so the panel cannot publish it again.

When the admin manually publishes an item, the news key must also become known to the automatic deduplication state so the next bot run does not republish the same story.

## Rejection Reasons

Rejection reasons should be stable machine-readable codes with Persian labels in the UI. Examples:

- `article_or_commentary`
- `low_signal`
- `duplicate_or_redundant`
- `bundled_headline`
- `translation_failed`
- `unapproved_source`
- `invalid_publish_time`
- `stale`

The panel must show both the friendly Persian label and enough raw context to understand the decision.

## Manual Editing and Publication

The edit screen exposes only the Persian headline and body as editable fields. Original source text is read-only and always visible for comparison.

Before publication:

- headline must be non-empty
- source and source URL must exist
- body may be empty only when the headline is genuinely self-contained
- Telegram HTML must be escaped/controlled through existing formatter rules
- duplicate/manual-already-published checks must run

After Telegram confirms success, persist the final exact copy and timestamp. If Telegram fails, leave the item pending and show the error; never mark it published prematurely.

## Authentication and Security

Single-admin authentication only.

- Password is supplied through a deployment secret/environment variable, never committed to the repository.
- Use a secure session cookie.
- All mutation routes require authentication and CSRF protection.
- Avoid exposing Telegram token, GitHub token, password, or internal secrets to browser JavaScript.
- The public panel URL must show only a login screen until authenticated.
- Rate-limit login attempts sufficiently for a small personal panel.

## Free Hosting Strategy

The design should target a free web-hosting option compatible with a small Python app and environment secrets. The automated GitHub Actions agent remains where it is.

Because free hosting products and limits change, deployment choice must be validated at implementation/deployment time rather than hard-coded into the architecture. The application must therefore be portable: standard Python HTTP app, environment configuration, no platform-specific core logic.

If a chosen free host sleeps when idle, that is acceptable because the panel is only an on-demand admin surface; it must not affect the autonomous GitHub Actions bot.

## Custom Source Discovery

### Website Sources

Order of preference:

1. explicitly supplied RSS/Atom feed
2. feed discovered from website metadata
3. clearly identifiable public feed endpoint discovered from the site

Do not implement unrestricted generic scraping of arbitrary page layouts in v1. If a site has no usable public feed, mark it `needs_feed` in the panel and explain that automatic ingestion is unavailable until a compatible feed/public endpoint is provided. This keeps source ingestion reliable and maintainable.

### X/Twitter Sources

Use best-effort publicly indexed discovery only. The UI must label these accounts as `best-effort` so the admin understands that a free system cannot guarantee immediate or complete X coverage without an official paid API.

## UI Design

Persian RTL interface, optimized for a phone.

Visual rules:

- clean flat layout
- no decorative complexity
- large tap targets
- clear status badges
- readable source and rejection reason
- source link always one tap away
- edit fields large enough for Persian copy editing
- publication confirmation required immediately before sending

Primary navigation:

- `داشبورد`
- `نیاز به بررسی`
- `منتشرشده‌ها`
- `ردشده‌ها`
- `منابع`

## Failure Handling

- A broken custom source must not block other sources.
- A panel outage must not block the automatic bot.
- A Telegram failure during manual publication leaves the item pending.
- A malformed custom source is rejected at save time with a clear message.
- If feed discovery fails, preserve the source definition with a visible inactive/error state rather than silently discarding it.
- Concurrent panel and Actions writes must use merge-safe persistence and tests covering race-sensitive update behavior.

## Testing Requirements

Use TDD for implementation.

Required coverage includes:

- rejected eligible candidate becomes a full pending review record
- rejection reason is preserved
- auto-published candidate cannot remain manually publishable
- manual publish writes exact edited Persian copy only after Telegram success
- manual publish prevents later automatic duplicate publication
- Telegram failure does not mark an item published
- add/update/disable/delete website source
- RSS discovery behavior
- invalid website source handling
- add/update/disable/delete X handle
- custom-source Iran filtering
- authentication required on all private routes
- invalid password rejected
- mutation routes protected from CSRF
- secret values never rendered in HTML
- concurrent persistence merge does not lose unrelated records
- existing news/market/weather/car tests continue to pass

## Non-Goals for V1

- multiple administrators
- roles/permissions
- paid X API integration
- arbitrary HTML scraping for every website on the internet
- complex analytics
- scheduled manual posts
- media upload/editor
- editing already-published Telegram messages
- replacing GitHub Actions with the panel host

## Acceptance Criteria

The feature is complete when:

1. The existing bot continues to run automatically without the panel being online.
2. A rejected actionable news item appears in a readable review queue with source, original content, Persian draft, source link, and rejection reason.
3. The admin can edit Persian title/body and publish immediately to `@bikhabaar`.
4. Successful manual publication is persisted and cannot be duplicated by the automatic bot.
5. The admin can add, disable, and delete website feed sources and X/Twitter handles without editing code.
6. Custom sources feed into the same Iran-related editorial pipeline.
7. The panel is protected by a single-admin password stored only as a secret.
8. The panel works comfortably on mobile and can be deployed on a free hosting tier without becoming a dependency of the autonomous bot.
9. All new and existing automated tests pass before completion is claimed.
