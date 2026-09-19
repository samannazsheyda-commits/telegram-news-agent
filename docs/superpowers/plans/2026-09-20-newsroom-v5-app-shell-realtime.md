# Newsroom V5 Implementation Plan 3 — App Shell, Review, and Real-Time UX

**Depends on:** Plan 1 SQLite runtime store and Plan 2 canonical story pipeline.

**Goal:** Make the operator surface behave like a fast app: Persian unpublished news as the primary screen, cursor/infinite loading without artificial content caps, SSE updates, persistent navigation state, and no ordinary full-page reloads.

## Task 1 — Define Review API contract with failing tests

**Create:** `tests/test_newsroom_v5_review_api.py`

Add RED tests for authenticated endpoints:

- `GET /api/v5/review?limit=25` returns only Persian-ready `review` stories;
- ordering is `published_at_source DESC, id DESC`;
- `next_cursor` loads the next logical page with no skips/duplicates;
- no hard business cap: seed >100 eligible stories and traverse all pages;
- untranslated, publishing, published, rejected, duplicate, and irrelevant rows are excluded;
- item payload has source, exact source timestamp, Persian title/body, importance/priority, and source URL;
- publish/reject/edit URLs/actions reference the canonical story id.

Run:

```bash
python -m pytest -q tests/test_newsroom_v5_review_api.py
```

## Task 2 — Add V5 API blueprint backed only by local store

**Create:** `panel/newsroom_v5_api.py`

Expose:

- `GET /api/v5/review`;
- `GET /api/v5/story/<id>`;
- `POST /api/v5/story/<id>/reject`;
- `POST /api/v5/story/<id>/publish`;
- `PATCH /api/v5/story/<id>/copy`;
- `GET /api/v5/published`;
- `GET /api/v5/counts`.

Sensitive mutations preserve existing CSRF/session/confirmation expectations. Endpoint code must never read GitHub JSON directly and must never invoke translation synchronously.

**Modify:** panel app/blueprint registration path used by the current V4 APIs.

Run:

```bash
python -m pytest -q tests/test_newsroom_v5_review_api.py
```

## Task 3 — Add event bus and SSE endpoint

**Create:** `src/newsroom_v5_events.py`

**Create:** `panel/newsroom_v5_events_api.py`

Start with a simple in-process bounded event broker appropriate to the current single-VPS deployment, with monotonic event ids and heartbeat comments. Define typed events:

- `story_added`;
- `story_updated`;
- `story_published`;
- `story_rejected`;
- `counts_changed`;
- `job_health_changed`;
- `luna_status`.

Do not make SQLite writes depend on a connected browser. Events are post-commit notifications; clients reconnect and refetch authoritative state if they miss an event.

**Create:** `tests/test_newsroom_v5_events.py`

**Create:** `tests/test_newsroom_v5_sse_api.py`

Test event ids/order, heartbeat/reconnect behavior, auth, and publish/reject event emission.

Run:

```bash
python -m pytest -q tests/test_newsroom_v5_events.py tests/test_newsroom_v5_sse_api.py
```

## Task 4 — Introduce persistent application shell

**Create:** `panel/templates/app_shell.html`

**Create:** `panel/static/newsroom-v5-app.js`

**Create:** `panel/static/newsroom-v5-app.css`

**Modify:** `panel/templates/base.html`

The shell owns four daily-use tabs:

1. خبرها
2. Luna
3. منتشرشده
4. کنترل

Keep server auth/session bootstrap, CSRF meta, manifest, and graceful direct URLs, but ordinary tab changes after bootstrap use client-side view switching/history state rather than document navigation.

Persist in `sessionStorage` where safe:

- active tab;
- Review scroll offset;
- loaded cursor/window state;
- selected story id;
- Luna draft/context handoff marker.

Do not add a heavy SPA framework unless measurements prove the small vanilla shell cannot satisfy the spec.

## Task 5 — Implement virtual/infinite Review list

**Create:** `panel/static/newsroom-v5-review.js`

Review boot behavior:

- fetch first cursor page;
- render Persian-only cards;
- use `IntersectionObserver` to fetch later pages;
- keep a bounded rendered window around the viewport;
- preserve source-time order when SSE inserts a new story;
- restore scroll position when returning from Luna/detail;
- never discard server-side eligible stories because they are outside the DOM window.

Card actions:

- انتشار;
- ویرایش;
- رد خبر;
- از Luna بپرس;
- منبع.

**Create:** `tests/test_newsroom_v5_frontend_contract.py`

Use static/source contract assertions where the repository has no browser runner yet. Assert there is no hard slice like `items[:100]`, no machine-ready removal that hides logically eligible Review items, and no ordinary `window.location.href` navigation in V5 app code.

If adding a JS test runner is necessary, keep it minimal and add the exact command to CI rather than introducing a frontend build toolchain for its own sake.

## Task 6 — Wire optimistic mutations and exact confirmation

In `panel/static/newsroom-v5-review.js`:

- publish shows exact Persian preview and asks for confirmation;
- reject asks confirmation;
- after accepted mutation, card gets immediate local busy/publishing state;
- final removal occurs on authoritative response/SSE;
- failures restore the card and show a concise error;
- double submission is disabled client-side in addition to server idempotency.

**Extend:** `tests/test_newsroom_v5_review_api.py` for conflict/idempotency response shape.

## Task 7 — Add SSE client with polling fallback

**Create or extend:** `panel/static/newsroom-v5-app.js`

Behavior:

- one `EventSource` per shell;
- event updates local list/counts without reload;
- reconnect uses browser EventSource behavior plus refetch-on-open;
- if SSE repeatedly fails, fall back to a low-frequency incremental fetch, not 5-second full-page/feed reload;
- when connection recovers, polling stops.

Remove V5 dependency on the old 5-second dashboard polling path. Do not break V4 until V5 feature flag/cutover is ready.

## Task 8 — Change Service Worker to app-shell caching

**Modify:** `panel/static/sw.js`

Version the V5 cache. Strategy:

- versioned static assets: cache-first/stale-while-revalidate as appropriate;
- authenticated app shell/navigation: network-first with cached shell fallback only where safe;
- `/api/` and SSE: network-only/no-store;
- no stale mutation responses;
- activate deletes old V4/V5 caches;
- add an update signal so an already-open client can show «نسخه جدید آماده است» rather than silently mixing incompatible assets.

**Create:** `tests/test_newsroom_v5_service_worker.py`

Static contract tests should prove `/api/` remains network-fresh while shell/static can be cached.

## Task 9 — Make HTTPS an explicit deployment precondition

**Modify:** `deploy/update-vps.sh` only if needed for health checks; do not provision DNS/TLS blindly in code.

**Create:** `scripts/check_newsroom_v5_runtime.py`

Check:

- DB path writable;
- SQLite WAL active;
- HTTPS/forwarded scheme configuration is correct for microphone/PWA expectations;
- SSE endpoint can remain open through the configured reverse proxy;
- required environment flags are explicit.

This check must be read-only.

## Task 10 — Performance smoke tests

**Create:** `tests/test_newsroom_v5_performance.py`

Use deterministic local measurements, not internet calls. Seed a realistic queue (for example 2,000 stories) and assert generous CI-safe upper bounds while logging the design targets:

- indexed Review query remains comfortably below the 50ms production target on local CI data;
- cursor fetch cost does not grow linearly with page number;
- mutation transaction does not touch GitHub adapter;
- rendering API payload stays bounded by page size.

Add runtime timing headers/metrics only if useful for diagnostics; do not expose sensitive internals.

Run:

```bash
python -m pytest -q \
  tests/test_newsroom_v5_review_api.py \
  tests/test_newsroom_v5_events.py \
  tests/test_newsroom_v5_sse_api.py \
  tests/test_newsroom_v5_frontend_contract.py \
  tests/test_newsroom_v5_service_worker.py \
  tests/test_newsroom_v5_performance.py
```

Then:

```bash
python -m pytest -q
```

## Completion gate

Plan 3 is complete only when all logically eligible Review stories are reachable, operator-visible cards are always Persian, ordinary app navigation does not reload the document, SSE updates add/remove stories in real time, APIs do not wait on GitHub, service-worker caching cannot stale live data, and full regression tests are green.

Do not cut production over to the V5 shell or deploy without fresh user approval.