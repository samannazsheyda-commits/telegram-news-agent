# Newsroom Panel V4 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the existing layered V3 panel presentation with a fast, mobile-first Newsroom Panel V4 that reuses the current Flask APIs/services and adds real dashboard, incoming/review/Luna/archive/sources/settings/health surfaces without modifying the V3 candidate-decision pipeline.

**Architecture:** Keep Flask + Jinja and the current `panel` blueprints. Consolidate presentation into one V4 shell (`newsroom-v4.css` + `newsroom-v4.js`) and extend `panel/newsroom_api.py` only for panel aggregation/actions. Reuse existing command/source/settings paths; no duplicate backend pipeline.

**Tech Stack:** Python, Flask, Jinja2, vanilla JavaScript, CSS, pytest.

**Spec:** `docs/superpowers/specs/2026-09-18-newsroom-panel-v4-design.md`

## Global Constraints

- Scope is panel-only; do not modify the V3 waiting/ready decision algorithm.
- Do not restore or expose Air Traffic anywhere in V4.
- Do not make V2 the production main path.
- Keep Flask/Jinja; do not introduce a SPA build system.
- Machine translation failure must not block Luna actions or hang the UI.
- Manual Luna flow must always preview before publish.
- Do not expose secrets to templates or JSON responses.
- Mobile must avoid heavy blur/animation and use safe-area-aware bottom navigation.
- Render at most about 20–30 news/archive rows per page/view.
- Reuse existing panel/source/settings command paths wherever possible.

---

### Task 1: Lock V4 shell and remove legacy presentation conflicts

**Files:**
- Modify: `panel/templates/base.html`
- Create: `panel/static/newsroom-v4.css`
- Create: `panel/static/newsroom-v4.js`
- Test: `tests/test_panel_v4_shell.py`

**Interfaces:**
- Consumes: Flask `request.path`, `session`, existing route names.
- Produces: one V4 layout with `data-newsroom-shell="v4"`, desktop navigation, mobile bottom navigation, toast mount, and `window.NewsroomV4` bootstrap.

- [ ] **Step 1: Write failing shell tests**

```python
from panel.app import create_app


def _login(client):
    with client.session_transaction() as session:
        session["admin"] = True


def test_v4_shell_is_single_active_newsroom_layer(app):
    client = app.test_client(); _login(client)
    body = client.get("/").get_data(as_text=True)
    assert 'data-newsroom-shell="v4"' in body
    assert 'newsroom-v4.css' in body
    assert 'newsroom-v4.js' in body
    assert 'newsroom-shell.css' not in body
    assert 'newsroom-final.css' not in body


def test_mobile_nav_has_safe_area_and_primary_destinations(app):
    client = app.test_client(); _login(client)
    body = client.get("/").get_data(as_text=True)
    assert 'class="v4-mobile-nav"' in body
    for label in ("داشبورد", "ورودی", "بررسی", "لونا", "بیشتر"):
        assert label in body
```

- [ ] **Step 2: Run the tests and verify failure**

Run: `pytest tests/test_panel_v4_shell.py -q`
Expected: FAIL because V4 assets/layout do not exist.

- [ ] **Step 3: Implement the V4 base shell**

Update `base.html` so it loads only the shared baseline assets that are still required plus `newsroom-v4.css` and `newsroom-v4.js`; remove active references to `newsroom-shell.css` and `newsroom-final.css`. Set `<body data-newsroom-shell="v4">`. Build semantic desktop navigation and mobile bottom navigation with these top-level destinations: Dashboard, Incoming, Review, Luna, Published, Sources, Settings, Health. Keep logout and CSRF behavior.

Create CSS variables and layout primitives in `newsroom-v4.css`, including:

```css
:root {
  --v4-bg: #eef2f6;
  --v4-surface: #ffffff;
  --v4-surface-2: #f7f9fb;
  --v4-text: #17202a;
  --v4-muted: #667085;
  --v4-border: #d8dee7;
  --v4-accent: #3157d5;
  --v4-danger: #b42318;
  --v4-success: #067647;
  --v4-radius: 18px;
  --v4-touch: 44px;
}

.v4-mobile-nav { padding-bottom: max(8px, env(safe-area-inset-bottom)); }
@media (max-width: 760px) {
  * { backdrop-filter: none !important; }
  .v4-desktop-nav { display: none; }
  .v4-mobile-nav { display: grid; }
}
```

Create a small `newsroom-v4.js` bootstrap that only handles common nav/toast/dialog helpers; feature-specific logic remains added in later tasks.

- [ ] **Step 4: Run shell tests**

Run: `pytest tests/test_panel_v4_shell.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add panel/templates/base.html panel/static/newsroom-v4.css panel/static/newsroom-v4.js tests/test_panel_v4_shell.py
git commit -m "feat: introduce Newsroom Panel V4 shell"
```

---

### Task 2: Build real V4 dashboard aggregation and remove Air Traffic

**Files:**
- Modify: `panel/newsroom_api.py`
- Modify: `panel/templates/dashboard.html`
- Test: `tests/test_panel_v4_dashboard.py`

**Interfaces:**
- Consumes: existing `state.json`, `data/newsroom_v3_production_status.json`, editorial queue/history, settings.
- Produces: `GET /api/newsroom/snapshot` fields `counts`, `quota`, `health`, `latest`, and module data excluding Air Traffic.

- [ ] **Step 1: Write failing dashboard/API tests**

```python
def test_snapshot_excludes_air_traffic(auth_client):
    payload = auth_client.get("/api/newsroom/snapshot").get_json()
    assert "air-traffic" not in payload.get("modules", {})


def test_snapshot_exposes_quota_summary(auth_client):
    payload = auth_client.get("/api/newsroom/snapshot").get_json()
    quota = payload["quota"]
    assert {"regular_limit", "regular_published", "regular_remaining", "special_limit", "special_used"} <= quota.keys()


def test_dashboard_contains_real_operational_cards(auth_client):
    body = auth_client.get("/").get_data(as_text=True)
    for label in ("منتشرشده امروز", "باقی‌مانده", "منتظر بررسی", "سلامت لونا", "سلامت تلگرام"):
        assert label in body
    assert "ترافیک هوایی" not in body
```

- [ ] **Step 2: Run targeted tests**

Run: `pytest tests/test_panel_v4_dashboard.py -q`
Expected: FAIL on missing quota shape/V4 markup and Air Traffic exposure.

- [ ] **Step 3: Implement aggregation**

Remove `air-traffic` from `_MODULE_PREVIEW_PATHS`. Add pure helpers that normalize quota/health without mutating newsroom state:

```python
def _quota_summary(settings: dict, v3: dict) -> dict:
    regular_limit = max(1, _safe_int(settings.get("daily_quota")) or _safe_int(v3.get("daily_limit")) or 35)
    regular_published = max(0, _safe_int(v3.get("daily_published")))
    special_limit = max(0, _safe_int(settings.get("special_quota")) or 5)
    special_used = max(0, _safe_int(v3.get("special_published")))
    return {
        "regular_limit": regular_limit,
        "regular_published": regular_published,
        "regular_remaining": max(0, regular_limit - regular_published),
        "special_limit": special_limit,
        "special_used": special_used,
    }
```

Add a `health` object with agent, Luna/provider, Telegram, source-failure and latest-cycle state using only existing status data. Return explicit `unknown` rather than inventing healthy states.

- [ ] **Step 4: Replace dashboard markup**

Render V4 KPI cards and a compact operational summary. Remove the old operations module grid containing Air Traffic. Keep useful weather/market/tanker controls only if their endpoints are already functional; otherwise hide them from the primary dashboard instead of presenting dead controls.

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_panel_v4_dashboard.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add panel/newsroom_api.py panel/templates/dashboard.html tests/test_panel_v4_dashboard.py
git commit -m "feat: add real V4 newsroom dashboard"
```

---

### Task 3: Incoming news + machine preview + Luna preview-safe flow

**Files:**
- Modify: `panel/app.py`
- Modify: `panel/newsroom_api.py`
- Create: `panel/templates/incoming.html`
- Modify: `panel/static/newsroom-v4.js`
- Modify: `panel/static/newsroom-v4.css`
- Test: `tests/test_panel_v4_incoming.py`

**Interfaces:**
- Produces: `GET /incoming?page=N`, paged card list; panel actions use existing review/reject/publish command paths and a Luna-finalize action if already available.
- Pagination contract: `page >= 1`, `page_size = 25`.

- [ ] **Step 1: Write failing pagination/card tests**

```python
def test_incoming_renders_at_most_25_items(auth_client):
    body = auth_client.get("/incoming").get_data(as_text=True)
    assert body.count('data-news-card=') <= 25


def test_incoming_separates_machine_and_luna_copy(auth_client):
    body = auth_client.get("/incoming").get_data(as_text=True)
    assert "ترجمه ماشینی" in body
    assert "Luna Final" in body or "نسخه Luna" in body


def test_no_direct_publish_with_luna_button(auth_client):
    body = auth_client.get("/incoming").get_data(as_text=True)
    assert "انتشار با Luna" not in body
    assert "ارسال به Luna" in body
```

- [ ] **Step 2: Run tests and verify failure**

Run: `pytest tests/test_panel_v4_incoming.py -q`
Expected: FAIL because `/incoming` does not exist.

- [ ] **Step 3: Add route and pagination helper**

Add a panel-only helper:

```python
def _paginate(rows: list[dict], page: int, page_size: int = 25) -> tuple[list[dict], dict]:
    page = max(1, page)
    total = len(rows)
    start = (page - 1) * page_size
    return rows[start:start + page_size], {
        "page": page,
        "page_size": page_size,
        "total": total,
        "has_prev": page > 1,
        "has_next": start + page_size < total,
    }
```

Use `_live_feed(data)` as the input projection so raw English is never silently presented as Persian final copy.

- [ ] **Step 4: Build unified V4 news cards**

Each card shows Original, machine preview, Luna final state, source/time/status, and actions. If machine translation is empty/failed, show `ترجمه ماشینی موقتاً در دسترس نیست`. Do not disable Luna action because of that state.

- [ ] **Step 5: Implement responsive action states**

In `newsroom-v4.js`, use fetch + CSRF, set actions to `در صف…`/`در حال پردازش…`, show errors as toasts, and refresh the individual card/snapshot rather than full-page reloading where feasible.

- [ ] **Step 6: Run tests**

Run: `pytest tests/test_panel_v4_incoming.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add panel/app.py panel/newsroom_api.py panel/templates/incoming.html panel/static/newsroom-v4.js panel/static/newsroom-v4.css tests/test_panel_v4_incoming.py
git commit -m "feat: add paged V4 incoming newsroom"
```

---

### Task 4: Review, Luna workspace, and publish confirmation safety

**Files:**
- Modify: `panel/templates/review_queue.html`
- Create: `panel/templates/luna.html`
- Modify: `panel/app.py`
- Modify: `panel/static/newsroom-v4.js`
- Test: `tests/test_panel_v4_editorial_flow.py`

**Interfaces:**
- Produces: `/review` V4 queue, `/luna` workspace, reusable confirmation dialog API `NewsroomV4.confirmAction(options)`.

- [ ] **Step 1: Write failing safety tests**

```python
def test_review_uses_v4_cards(auth_client):
    body = auth_client.get("/review").get_data(as_text=True)
    assert 'data-v4-review-card' in body or "فعلاً موردی برای بررسی" in body


def test_luna_workspace_route_exists(auth_client):
    assert auth_client.get("/luna").status_code == 200


def test_publish_buttons_require_confirmation_markup(auth_client):
    body = auth_client.get("/review").get_data(as_text=True)
    assert 'data-confirm="publish"' in body or "تأیید انتشار" in body
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_panel_v4_editorial_flow.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement V4 review and Luna routes**

Reuse `_effective_queue(data)` and current status fields. Luna workspace groups `not reviewed`, `processing`, `ready`, and `failed` based on fields already present; unknown status remains unknown rather than fabricated.

- [ ] **Step 4: Add confirmation helper**

All publish/restart/reset/mass-change actions call one confirmation sheet before POST. Rejecting one story may use a lighter confirmation; publishing always requires confirmation after final preview.

- [ ] **Step 5: Run tests and commit**

Run: `pytest tests/test_panel_v4_editorial_flow.py -q`
Expected: PASS.

```bash
git add panel/templates/review_queue.html panel/templates/luna.html panel/app.py panel/static/newsroom-v4.js tests/test_panel_v4_editorial_flow.py
git commit -m "feat: add V4 Luna and review workspace"
```

---

### Task 5: Published archive, Sources, Settings, Health

**Files:**
- Modify: `panel/templates/history.html`
- Modify: `panel/templates/source_manager.html`
- Create: `panel/templates/settings_v4.html`
- Create: `panel/templates/health.html`
- Modify: `panel/app.py`
- Modify: `panel/newsroom_api.py`
- Test: `tests/test_panel_v4_operations.py`

**Interfaces:**
- Archive pagination: 25 per page with `q`, `source`, `range` filters.
- Health API returns human-readable `summary_fa` plus expandable technical data.

- [ ] **Step 1: Write failing operations tests**

```python
def test_history_is_paginated(auth_client):
    body = auth_client.get("/history").get_data(as_text=True)
    assert 'data-page-size="25"' in body


def test_sources_show_health_columns(auth_client):
    body = auth_client.get("/source-manager").get_data(as_text=True)
    for label in ("سلامت", "آخرین دریافت", "اولویت"):
        assert label in body


def test_health_page_explains_state_in_persian(auth_client):
    body = auth_client.get("/health").get_data(as_text=True)
    assert "چرا خبر منتشر نشده" in body or "وضعیت انتشار" in body
```

- [ ] **Step 2: Implement paged archive and filters**

Filter history server-side before slicing. Keep Telegram message ID and final copy visible. Search is case-insensitive over source/title/body.

- [ ] **Step 3: Adapt existing source manager into V4 shell**

Do not duplicate source write logic. Add health/last receive/error/priority/category/canonical labels only when data exists; show `—` when unknown.

- [ ] **Step 4: Add V4 settings route**

Expose only safe settings. Daily/special quota writes must go through the existing settings persistence layer. Never serialize provider keys/tokens/password hashes.

- [ ] **Step 5: Add health explanation helper**

Implement a pure function like:

```python
def _health_summary_fa(snapshot: dict) -> list[str]:
    notes = []
    if snapshot["quota"]["regular_remaining"] == 0:
        notes.append("سهمیه خبرهای عادی امروز تکمیل شده است.")
    if snapshot["health"]["telegram"] == "error":
        notes.append("ارسال تلگرام خطا دارد.")
    if snapshot["health"]["luna"] == "error":
        notes.append("سرویس Luna یا provider فعلی خطا دارد.")
    if not notes:
        notes.append("مانع قطعی از داده‌های فعلی دیده نمی‌شود.")
    return notes
```

- [ ] **Step 6: Run tests and commit**

Run: `pytest tests/test_panel_v4_operations.py -q`
Expected: PASS.

```bash
git add panel/templates/history.html panel/templates/source_manager.html panel/templates/settings_v4.html panel/templates/health.html panel/app.py panel/newsroom_api.py tests/test_panel_v4_operations.py
git commit -m "feat: add V4 operations and health surfaces"
```

---

### Task 6: Luna Control Assistant + audit log

**Files:**
- Create: `panel/luna_assistant.py`
- Create: `panel/audit_log.py`
- Modify: `panel/newsroom_api.py`
- Create: `panel/templates/_luna_assistant.html`
- Modify: `panel/templates/base.html`
- Modify: `panel/static/newsroom-v4.js`
- Test: `tests/test_panel_v4_luna_assistant.py`

**Interfaces:**
- `AuditLog.append(actor: str, action: str, target: str, before: object, after: object, result: str) -> None`
- `LunaAssistant.handle(message: str, context: dict) -> dict` returns `{reply_fa, intent, requires_confirmation, proposed_action}`.
- Actual mutations remain routed through existing panel action functions/endpoints.

- [ ] **Step 1: Write failing assistant/audit tests**

```python
def test_quota_change_requires_audited_action(assistant):
    result = assistant.handle("سهمیه امروز رو بکن 40", {})
    assert result["intent"] == "update_daily_quota"
    assert result["proposed_action"]["value"] == 40


def test_publish_intent_requires_confirmation(assistant):
    result = assistant.handle("این خبر رو منتشر کن", {"story_id": "abc"})
    assert result["requires_confirmation"] is True


def test_audit_record_has_required_fields(audit_log):
    audit_log.append("user", "update_daily_quota", "settings", {"daily": 35}, {"daily": 40}, "ok")
    row = audit_log.list(limit=1)[0]
    assert {"timestamp", "actor", "action", "target", "before", "after", "result"} <= row.keys()
```

- [ ] **Step 2: Implement focused audit store**

Persist to the existing data backend path `data/panel_audit_log.json`, cap retained rows to a reasonable fixed maximum (for example 2000) and paginate when reading.

- [ ] **Step 3: Implement assistant intent/action layer**

Start with deterministic command intents described by the spec: stats, recent errors/publications, quota updates, source enable/disable, selected-story finalization. Use Luna/provider generation only for conversational explanation/intent assistance where needed; mutations must resolve to explicit allow-listed tools.

- [ ] **Step 4: Add assistant UI**

Desktop side panel; mobile sheet/page. Display proposed sensitive action and require user confirmation before POSTing it.

- [ ] **Step 5: Run tests and commit**

Run: `pytest tests/test_panel_v4_luna_assistant.py -q`
Expected: PASS.

```bash
git add panel/luna_assistant.py panel/audit_log.py panel/newsroom_api.py panel/templates/_luna_assistant.html panel/templates/base.html panel/static/newsroom-v4.js tests/test_panel_v4_luna_assistant.py
git commit -m "feat: add Luna control assistant and audit log"
```

---

### Task 7: Authentication cleanup and legacy UI deactivation

**Files:**
- Modify: `panel/app.py`
- Modify: `panel/templates/login.html`
- Modify: `panel/templates/base.html`
- Test: `tests/test_panel_v4_auth.py`

**Interfaces:**
- Existing `_authenticated()` remains session-based: `bool(session.get("admin"))`.

- [ ] **Step 1: Write auth regression tests**

```python
def test_dashboard_requires_login(app):
    response = app.test_client().get("/", follow_redirects=False)
    assert response.status_code in {302, 303}
    assert "/login" in response.headers["Location"]


def test_login_page_does_not_expose_secrets(app):
    body = app.test_client().get("/login").get_data(as_text=True)
    assert "PANEL_PASSWORD_HASH" not in body
    assert "TELEGRAM_BOT_TOKEN" not in body
```

- [ ] **Step 2: Verify implementation keeps real session auth**

Keep rate limiting, secure cookie configuration, CSRF and logout behavior. Do not implement an always-true bypass in repository code.

- [ ] **Step 3: Stop loading legacy newsroom CSS/JS from active templates**

Verify V4 pages no longer reference `newsroom-shell.css`, `newsroom-final.css`, `newsroom-ui.js`, `newsroom-live.js`, `newsroom-actions.js`, or `newsroom-editor.js`. Do not delete legacy files until the full test suite passes; deactivation is sufficient for this task.

- [ ] **Step 4: Run tests and commit**

Run: `pytest tests/test_panel_v4_auth.py tests/test_panel_v4_shell.py -q`
Expected: PASS.

```bash
git add panel/app.py panel/templates/login.html panel/templates/base.html tests/test_panel_v4_auth.py
git commit -m "fix: secure V4 panel auth and deactivate legacy UI"
```

---

### Task 8: Verification, performance guards, and production-ready branch

**Files:**
- Create: `tests/test_panel_v4_performance.py`
- Modify only files required by failing verification.

**Interfaces:**
- No new product interfaces. This task validates the V4 contract.

- [ ] **Step 1: Add DOM-size/pagination regression tests**

```python
def test_incoming_does_not_render_100_rows(auth_client, seeded_100_live_items):
    body = auth_client.get("/incoming").get_data(as_text=True)
    assert body.count('data-news-card=') <= 25


def test_history_does_not_render_1000_rows(auth_client, seeded_1000_history_items):
    body = auth_client.get("/history").get_data(as_text=True)
    assert body.count('data-history-row=') <= 25
```

- [ ] **Step 2: Run focused V4 suite**

Run: `pytest tests/test_panel_v4_*.py -q`
Expected: PASS.

- [ ] **Step 3: Run existing panel-related tests**

Run: `pytest -q -k "panel or newsroom_api or source_manager or command_center"`
Expected: PASS; investigate every regression rather than weakening tests.

- [ ] **Step 4: Run full test suite**

Run: `pytest -q`
Expected: PASS, or document unrelated pre-existing failures with exact test names before any deployment claim.

- [ ] **Step 5: Static verification**

Search active V4 templates/assets for forbidden panel references:

```bash
grep -R "air-traffic\|ترافیک هوایی" panel/templates panel/static/newsroom-v4.*
grep -R "newsroom-shell.css\|newsroom-final.css\|newsroom-ui.js\|newsroom-live.js\|newsroom-actions.js\|newsroom-editor.js" panel/templates
```

Expected: no active V4 references.

- [ ] **Step 6: Commit final verification fixes**

```bash
git add panel tests
git commit -m "test: verify Newsroom Panel V4"
```

- [ ] **Step 7: Deployment handoff**

Do not claim production completion until the branch is deployed to the VPS, `bikhabar-panel.service` restarts cleanly, mobile/desktop are visually checked, and at least one safe panel action is verified against production data without modifying the V3 waiting/ready algorithm.
