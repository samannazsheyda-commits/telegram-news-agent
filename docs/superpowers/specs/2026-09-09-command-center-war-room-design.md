# Bikhabar Command Center War Room — Design

## Goal
Build a production-grade Persian RTL newsroom command center for the Bikhabar Telegram news agent, optimized for mobile and desktop operations during fast-moving war/news events.

## Product principles
- VPS is the only production runtime; GitHub remains source/CI/control plane.
- Live newsroom information must update without full-page refresh.
- War priorities are always visually dominant: missiles from Iran, missiles into Iran, explosions, direct attacks, Strait of Hormuz, drones, ships/tankers.
- One-tap operational controls must be obvious and safe.
- The UI must be Persian-first, RTL, high readability, and use Doran when an authorized font asset is present; otherwise use a safe Persian fallback stack without blocking the panel.
- Never expose secrets in the browser.

## Information architecture
The dashboard is a single War Room home screen with five regions:
1. Operations header: agent health, live connection, target scan interval, latest publication, panic stop/resume, instant scan.
2. Breaking priority strip: persistent red priority taxonomy.
3. Live newsroom feed: newest items, status, source, age, decision reason, source link, media indicator.
4. Operational modules: weather, air traffic, Hormuz/tanker, market; each shows schedule/state and supports publish-now where implemented.
5. System diagnostics: live/queue/published/rejected counts, agent heartbeat, source failures/latency where data exists.

## Realtime behavior
- Keep the existing 3-second live refresh for the feed and 5-second status refresh.
- Preserve optional sound alerts; user preference persists in localStorage.
- Show connection state and last successful sync time.
- New top item triggers visible badge and optional short tone.

## Command Center controls
- Panic stop/resume writes newsroom settings and immediately gates automated publication.
- Instant scan enqueues a refresh command for the VPS agent.
- Weather and air-traffic publish-now controls enqueue their existing commands.
- Unsupported modules must display an explicit unavailable/not-yet-wired state, not fake success.
- Every command surface must show queued/success/error feedback.

## Newsroom feed states
Visual chips for: fresh, auto-published, waiting/manual review, duplicate, rejected, publish failure. Breaking-priority items receive a stronger visual treatment based on title/source text keywords.

## Visual system
- Dark newsroom canvas, deep graphite surfaces, subtle borders, restrained red for urgent states, green only for healthy status.
- Dense but readable cards with strong hierarchy and large tap targets.
- Mobile layout collapses to one column with sticky operational controls.
- Doran font is used only when an authorized asset is actually available in the project/runtime. CSS uses `Doran` first and a Persian system-safe fallback stack afterward.
- No external font CDN dependency.

## PWA
Add a web app manifest, theme metadata, Apple mobile-capable metadata, and a small service worker that caches only static shell assets. Dynamic newsroom/API responses remain network-first/no-store.

## Safety and auth
- Existing admin session protection remains mandatory.
- Existing CSRF protection remains mandatory for state-changing requests.
- No Telegram token, panel password hash, server secrets, or GitHub token may be serialized into HTML/JS/API responses.

## Testing
- Dashboard smoke test verifies War Room controls and Doran-first CSS reference.
- Command Center API tests verify authenticated status, panic stop/resume, known module queueing, and unknown module rejection.
- PWA tests verify manifest and service worker routes/assets.
- Full regression suite must pass before merge and promotion to production.
