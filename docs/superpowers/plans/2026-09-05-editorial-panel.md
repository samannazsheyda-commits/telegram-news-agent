# Editorial Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a free, single-admin Persian web panel that lets the owner review rejected news, edit Persian copy, publish immediately to `@bikhabaar`, and manage custom website/RSS and X/Twitter sources without interrupting the autonomous GitHub Actions agent.

**Architecture:** Keep the existing scheduled agent as the primary autonomous process. Add repository-backed editorial/source JSON stores plus a small Flask server-rendered admin app. The panel reads/writes those JSON stores through the GitHub Contents API using a server-side fine-grained token, while the Actions job writes the same files locally and persists them with `git pull --rebase` + `git push`; all record updates are deterministic-ID upserts so concurrent unrelated changes are merged rather than replaced blindly. Shared modules own queue/source/publication logic so the bot and panel do not duplicate business rules.

**Tech Stack:** Python 3.12, Flask, Flask-WTF/CSRF, requests, BeautifulSoup, pytest, GitHub Actions, GitHub REST Contents API, server-rendered Jinja templates, plain RTL CSS.

**Spec:** `docs/superpowers/specs/2026-09-05-editorial-panel-design.md`

## Global Constraints

- Existing automatic news/market/weather/car behavior must remain operational when the panel is offline.
- Single admin only; no roles or user-management system.
- Persian RTL, mobile-first UI with large tap targets and minimal visual complexity.
- Manual approval publishes immediately only after Telegram confirms success.
- Telegram token, GitHub token, and panel password remain server-side secrets and are never rendered in HTML/JS.
- Custom X/Twitter discovery stays best-effort and must not require the paid X API.
- V1 website ingestion supports supplied/discovered RSS/Atom/public feeds only; no arbitrary layout scraping.
- Existing Iran relevance, source-backed content, no-invention, duplicate protection, and editorial formatting rules remain in force.
- Use TDD for every behavior change and run the entire suite before completion.

---

## File Structure

- Create `src/editorial_store.py`: normalized queue/history records, deterministic upserts, merge helpers, local JSON backend, GitHub Contents backend.
- Create `src/custom_sources.py`: custom source model/validation, feed discovery, config loading, custom website/X candidate collection.
- Create `src/manual_publish.py`: manual publication validation, formatting, Telegram send, dedupe marking, history transition.
- Modify `src/main.py`: enqueue rejected actionable items, transition auto-published items, load custom source candidates, persist editorial data.
- Modify `src/sources.py`: expose reusable feed parsing/fetch helpers required by custom sources.
- Create `panel/app.py`: Flask application factory, auth/session, dashboard, queue, edit/publish/reject, source CRUD routes.
- Create `panel/forms.py`: login, edit-news, website-source and X-source forms with CSRF.
- Create `panel/templates/*.html`: minimal Persian server-rendered pages.
- Create `panel/static/panel.css`: mobile-first RTL styling only.
- Modify `requirements.txt`: Flask and Flask-WTF runtime dependencies.
- Modify `.github/workflows/agent.yml`: persist `data/*.json` changes together with `state.json` and run panel-related tests on pushes.
- Create `data/editorial_queue.json`, `data/editorial_history.json`, `data/custom_sources.json`: initial empty stores.
- Create focused tests in `tests/test_editorial_store.py`, `tests/test_custom_sources.py`, `tests/test_manual_publish.py`, `tests/test_panel.py`, and extend `tests/test_news_pipeline_regressions.py`.

---

### Task 1: Editorial Queue and History Store

**Files:**
- Create: `src/editorial_store.py`
- Create: `data/editorial_queue.json`
- Create: `data/editorial_history.json`
- Test: `tests/test_editorial_store.py`

**Interfaces:**
- Produces: `ReviewItem`, `LocalEditorialStore`, `GitHubEditorialStore`, `upsert_review_item()`, `move_review_item()`, `merge_record_sets()`.
- Record identity: `ReviewItem.id` is deterministic from `news_key`; updates never create duplicate queue entries.

- [ ] **Step 1: Write failing store tests**

```python
from src.editorial_store import ReviewItem, merge_record_sets


def test_merge_preserves_unrelated_remote_and_local_records():
    remote = [{"id": "a", "status": "pending"}]
    local = [{"id": "b", "status": "pending"}]
    merged = merge_record_sets(remote, local)
    assert {r["id"] for r in merged} == {"a", "b"}


def test_same_id_prefers_newer_decision_record():
    remote = [{"id": "a", "status": "pending", "updated_at": "2026-09-05T00:00:00+00:00"}]
    local = [{"id": "a", "status": "published_manual", "updated_at": "2026-09-05T00:01:00+00:00"}]
    merged = merge_record_sets(remote, local)
    assert merged[0]["status"] == "published_manual"
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `python -m pytest tests/test_editorial_store.py -q`

Expected: import/module failure because `src.editorial_store` does not exist.

- [ ] **Step 3: Implement deterministic records and merge semantics**

```python
@dataclass(frozen=True)
class ReviewItem:
    id: str
    news_key: str
    source: str
    source_url: str
    original_title: str
    original_summary: str
    persian_title: str
    persian_body: str
    published_at_source: str
    discovered_at: str
    rejection_reason: str
    status: str = "pending"
    final_persian_title: str = ""
    final_persian_body: str = ""
    decision_at: str = ""
    updated_at: str = ""


def merge_record_sets(remote: list[dict], incoming: list[dict]) -> list[dict]:
    by_id = {record["id"]: record for record in remote}
    for record in incoming:
        old = by_id.get(record["id"])
        if old is None or record.get("updated_at", "") >= old.get("updated_at", ""):
            by_id[record["id"]] = record
    return sorted(by_id.values(), key=lambda r: r.get("updated_at", ""), reverse=True)
```

Implement atomic local writes using a temporary file plus `os.replace`. Implement `GitHubEditorialStore` with conditional update using the latest blob SHA; if GitHub returns a conflict, refetch, merge, and retry once.

- [ ] **Step 4: Run focused tests**

Run: `python -m pytest tests/test_editorial_store.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/editorial_store.py data/editorial_queue.json data/editorial_history.json tests/test_editorial_store.py
git commit -m "feat: add merge-safe editorial store"
```

---

### Task 2: Feed Rejected News Into the Review Queue

**Files:**
- Modify: `src/main.py`
- Test: `tests/test_news_pipeline_regressions.py`

**Interfaces:**
- Consumes: `LocalEditorialStore` and `ReviewItem` from Task 1.
- Produces: full pending queue records for actionable editorial rejections; stale/malformed records go to non-actionable history.

- [ ] **Step 1: Add failing pipeline tests**

```python
def test_editorial_rejection_creates_full_pending_review_record(tmp_path, monkeypatch):
    # Wire one same-day Reuters analysis candidate.
    # After run(), assert queue contains source/title/url/reason and status=pending.
    ...


def test_stale_item_is_audited_but_not_actionable(tmp_path, monkeypatch):
    # Wire an old source-backed item.
    # Assert active queue excludes it and history records status=superseded/reason=stale.
    ...
```

Use the existing `_wire` pattern and temporary data paths; do not hit network services.

- [ ] **Step 2: Run regression tests and verify RED**

Run: `python -m pytest tests/test_news_pipeline_regressions.py -q`

Expected: new assertions fail because the pipeline currently records only state audit data and does not write the editorial store.

- [ ] **Step 3: Add stable editorial classification and queue upsert**

In `src/main.py`, centralize rejection classification:

```python
def editorial_decision(item: NewsItem, now: datetime) -> tuple[bool, str]:
    if not _published_dt(item.published):
        return False, "invalid_publish_time"
    if not _published_today(item.published, now):
        return False, "stale"
    if _looks_bundled(item):
        return False, "bundled_headline"
    title = (item.title or "").lower()
    if any(p in title for p in ARTICLE_PATTERNS):
        return False, "article_or_commentary"
    if is_important_news(item.title, item.summary) or _is_trump_iran_news(item):
        return True, "approved_auto"
    return False, "low_signal"
```

For actionable current rejections, translate a best-effort draft and upsert the full record into `data/editorial_queue.json`. For stale/invalid records, write to history only.

- [ ] **Step 4: Ensure rejected items do not become duplicate references for good items**

Keep duplicate references restricted to actual previously published/accepted records; newly rejected candidates must not suppress a factual candidate from another source.

- [ ] **Step 5: Run focused + existing pipeline tests**

Run: `python -m pytest tests/test_news_pipeline_regressions.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/main.py tests/test_news_pipeline_regressions.py
git commit -m "feat: queue rejected news for manual review"
```

---

### Task 3: Custom Website and X/Twitter Source Configuration

**Files:**
- Create: `src/custom_sources.py`
- Create: `data/custom_sources.json`
- Modify: `src/sources.py`
- Test: `tests/test_custom_sources.py`

**Interfaces:**
- Produces: `WebsiteSource`, `XSource`, `validate_website_source()`, `discover_feed_url()`, `load_custom_sources()`, `fetch_custom_news_items()`.
- Custom source candidates return normal `NewsItem` objects and therefore enter the existing Iran/editorial pipeline.

- [ ] **Step 1: Write failing source CRUD/validation tests**

```python
def test_explicit_rss_feed_is_used_before_discovery(): ...
def test_feed_discovery_reads_html_link_rel_alternate(): ...
def test_invalid_website_scheme_is_rejected(): ...
def test_x_handle_is_normalized_to_at_handle(): ...
def test_disabled_custom_source_is_not_fetched(): ...
def test_custom_source_non_iran_item_is_filtered(): ...
```

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_custom_sources.py -q`

Expected: module/functions missing.

- [ ] **Step 3: Implement website source validation and feed discovery**

```python
def validate_website_source(name: str, website_url: str, feed_url: str = "") -> WebsiteSource:
    parsed = urlparse(website_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("invalid_website_url")
    ...
```

Feed discovery order is exactly: supplied feed, `<link rel="alternate" type="application/rss+xml|application/atom+xml">`, then clearly linked public feeds. No generic article-page scraper.

- [ ] **Step 4: Implement free best-effort X discovery adapter**

Store handles separately and construct indexed-search queries restricted to the handle plus Iran terms, reusing the project's current public/indexed discovery strategy. Label status `best_effort` in returned metadata. Never require X credentials.

- [ ] **Step 5: Integrate custom candidates into `fetch_news_items()`**

Merge custom items by `NewsItem.key`; isolate each broken custom source in its own `try/except` so one failure does not block others.

- [ ] **Step 6: Run tests**

Run: `python -m pytest tests/test_custom_sources.py tests/test_sources.py -q`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/custom_sources.py src/sources.py data/custom_sources.json tests/test_custom_sources.py
git commit -m "feat: add configurable website and x sources"
```

---

### Task 4: Manual Edit, Publish, Reject, and Duplicate Protection

**Files:**
- Create: `src/manual_publish.py`
- Modify: `src/main.py`
- Test: `tests/test_manual_publish.py`

**Interfaces:**
- Produces: `publish_review_item(store, item_id, title_fa, body_fa, token, chat_id) -> ReviewItem` and `reject_review_item(store, item_id) -> ReviewItem`.
- Reuses `format_news()` and `send_telegram()`; does not build a second Telegram formatter.

- [ ] **Step 1: Write failing manual publication tests**

```python
def test_manual_publish_saves_exact_edited_copy_after_telegram_success(): ...
def test_telegram_failure_leaves_item_pending(): ...
def test_manual_publish_requires_source_url_and_nonempty_title(): ...
def test_already_published_item_cannot_publish_twice(): ...
def test_manual_publish_marks_news_key_for_auto_dedup(): ...
```

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_manual_publish.py -q`

Expected: module missing.

- [ ] **Step 3: Implement validation and send-before-state-transition ordering**

```python
def publish_review_item(...):
    item = store.get_pending(item_id)
    if not title_fa.strip():
        raise ValueError("headline_required")
    if not item.source or not item.source_url:
        raise ValueError("source_required")
    message = format_news(...)
    send_telegram(message, token, chat_id)  # must succeed first
    # only now persist published_manual and final exact copy
    ...
```

Update the dedupe state only after successful send. If send raises, do not mutate queue/history/status.

- [ ] **Step 4: Make auto-publication transition matching pending records to `published_auto`**

After a successful automatic Telegram send in `src/main.py`, move/update any matching pending queue record to history and make it non-publishable.

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/test_manual_publish.py tests/test_news_pipeline_regressions.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/manual_publish.py src/main.py tests/test_manual_publish.py tests/test_news_pipeline_regressions.py
git commit -m "feat: add safe manual telegram publication"
```

---

### Task 5: Single-Admin Flask Panel and Security

**Files:**
- Create: `panel/__init__.py`
- Create: `panel/app.py`
- Create: `panel/forms.py`
- Create: `panel/templates/base.html`
- Create: `panel/templates/login.html`
- Create: `panel/templates/dashboard.html`
- Create: `panel/templates/review_queue.html`
- Create: `panel/templates/review_edit.html`
- Create: `panel/templates/history.html`
- Create: `panel/templates/sources.html`
- Create: `panel/static/panel.css`
- Modify: `requirements.txt`
- Test: `tests/test_panel.py`

**Interfaces:**
- Produces Flask app factory `create_app(config: dict | None = None)`.
- Environment secrets: `PANEL_PASSWORD_HASH`, `PANEL_SECRET_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `GITHUB_DATA_TOKEN`, `GITHUB_REPOSITORY`.

- [ ] **Step 1: Write failing authentication and CSRF tests**

```python
def test_private_route_redirects_to_login(client): ...
def test_invalid_password_is_rejected(client): ...
def test_authenticated_dashboard_loads(client): ...
def test_mutation_without_csrf_is_rejected(client): ...
def test_secret_values_never_render_in_html(client, app): ...
```

Use Werkzeug password hashing; store only the hash in `PANEL_PASSWORD_HASH`.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_panel.py -q`

Expected: panel package missing.

- [ ] **Step 3: Implement app factory and single-admin login**

```python
def create_app(config=None):
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY=os.environ["PANEL_SECRET_KEY"],
        WTF_CSRF_ENABLED=True,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SECURE=True,
        SESSION_COOKIE_SAMESITE="Lax",
    )
    ...
```

All private routes use one `login_required` decorator. Add a small in-process login-rate limiter keyed by request IP for the personal-panel use case.

- [ ] **Step 4: Implement dashboard and review screens**

Routes:

```text
GET/POST /login
POST     /logout
GET      /
GET      /review
GET      /review/<item_id>
POST     /review/<item_id>/publish
POST     /review/<item_id>/reject
GET      /published
GET      /rejected
GET/POST /sources
POST     /sources/<source_id>/toggle
POST     /sources/<source_id>/delete
```

Original title/body/link are read-only. Persian title/body are editable. Publish form requires a confirmation submit and calls `publish_review_item()` directly for immediate Telegram publication.

- [ ] **Step 5: Implement source forms**

Website form fields: display name, website URL, optional feed URL. X form field: handle. Show active state, detected feed, last check, last error; support toggle/delete.

- [ ] **Step 6: Implement minimal Persian RTL mobile CSS**

No frontend framework. Ensure 44px+ action targets, readable status badges, full-width textareas, sticky/simple navigation, and one-tap source links.

- [ ] **Step 7: Run panel tests**

Run: `python -m pytest tests/test_panel.py -q`

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add panel requirements.txt tests/test_panel.py
git commit -m "feat: add secure single-admin editorial panel"
```

---

### Task 6: GitHub-Backed Panel Persistence

**Files:**
- Modify: `src/editorial_store.py`
- Modify: `src/custom_sources.py`
- Modify: `panel/app.py`
- Test: `tests/test_editorial_store.py`
- Test: `tests/test_panel.py`

**Interfaces:**
- Panel production config uses `GitHubEditorialStore`; tests/local development may use `LocalEditorialStore`.
- Server-side GitHub token is never sent to browser code.

- [ ] **Step 1: Add failing GitHub conflict/retry tests**

```python
def test_github_store_refetches_and_merges_after_sha_conflict(fake_github): ...
def test_panel_source_update_does_not_erase_agent_queue_record(fake_github): ...
```

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_editorial_store.py tests/test_panel.py -q`

Expected: conflict tests fail until remote merge/retry is implemented.

- [ ] **Step 3: Implement server-side repository persistence**

Use GitHub REST Contents API:

```text
GET /repos/{owner}/{repo}/contents/data/editorial_queue.json?ref=main
PUT /repos/{owner}/{repo}/contents/data/editorial_queue.json
```

Every mutation fetches current content + SHA, merges by record ID, submits replacement content with that SHA, and on 409/422 refetches/merges/retries once. Apply the same pattern to history and custom sources.

- [ ] **Step 4: Run focused tests**

Run: `python -m pytest tests/test_editorial_store.py tests/test_panel.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/editorial_store.py src/custom_sources.py panel/app.py tests/test_editorial_store.py tests/test_panel.py
git commit -m "feat: persist panel data through github safely"
```

---

### Task 7: GitHub Actions Persistence and Integration Hardening

**Files:**
- Modify: `.github/workflows/agent.yml`
- Modify: `README.md`
- Test: entire suite

**Interfaces:**
- Scheduled agent persists `state.json` plus editorial/custom-source data files without requiring the web panel to be online.

- [ ] **Step 1: Update workflow persistence scope**

Replace the state-only check/add with:

```bash
if git diff --quiet -- state.json data/editorial_queue.json data/editorial_history.json data/custom_sources.json; then
  echo "No persisted changes"
  exit 0
fi
git add state.json data/editorial_queue.json data/editorial_history.json data/custom_sources.json
git commit -m "chore: update agent state"
git pull --rebase
git push
```

- [ ] **Step 2: Document required deployment secrets and local start command**

Document only secret names, never values:

```text
PANEL_PASSWORD_HASH
PANEL_SECRET_KEY
TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID=@bikhabaar
GITHUB_DATA_TOKEN
GITHUB_REPOSITORY=samannazsheyda-commits/telegram-news-agent
```

Document local command: `flask --app panel.app:create_app run`.

- [ ] **Step 3: Run the complete test suite locally/CI**

Run: `python -m pytest -q`

Expected: all existing and new tests PASS.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/agent.yml README.md
git commit -m "ci: persist editorial panel data"
```

---

### Task 8: Free Deployment Validation and End-to-End Verification

**Files:**
- Create only if required by selected host: a minimal deployment descriptor such as `Procfile`, `render.yaml`, `vercel.json`, or equivalent.
- Modify: `README.md` with the actually validated free-host steps.

**Interfaces:**
- Production panel must run as a standard Python web app with environment secrets.
- Host availability must not be required for the autonomous bot.

- [ ] **Step 1: Validate current free-host options at implementation time**

Check current free-tier support for Python web apps, environment secrets, HTTPS, and outbound requests. Prefer the simplest host that supports the Flask app without rewriting core logic. Do not commit platform assumptions before verification.

- [ ] **Step 2: Deploy with only server-side secrets**

Set the six required secret/config values on the host. Confirm unauthenticated access shows only the login page.

- [ ] **Step 3: Perform end-to-end manual review test using a safe test candidate**

Verify in order:

```text
1. Candidate appears in نیاز به بررسی.
2. Original source/link/rejection reason are visible.
3. Persian headline/body can be edited.
4. Publication confirmation is required.
5. Telegram success moves item to published history.
6. Exact edited copy is stored.
7. Subsequent agent run does not publish the same news key again.
```

- [ ] **Step 4: Verify source management end to end**

Add one known RSS-capable website and one X handle, verify they persist after page reload, verify disabling prevents collection, and verify deletion removes them without affecting built-in sources.

- [ ] **Step 5: Trigger/observe a fresh GitHub Actions run**

Verify tests, near-realtime monitor, and persistence steps all complete successfully on a commit containing the final feature. Inspect logs; do not claim success from code inspection alone.

- [ ] **Step 6: Commit final deployment documentation if it changed**

```bash
git add README.md <deployment-descriptor-if-any>
git commit -m "docs: add validated editorial panel deployment"
```

---

## Final Verification Checklist

Before completion is claimed:

- `python -m pytest -q` passes on the final commit.
- A fresh GitHub Actions run for the final commit passes tests, monitor, and persistence.
- Panel login rejects unauthenticated access and bad passwords.
- CSRF-protected mutations reject missing/invalid tokens.
- No secret value appears in generated HTML or committed files.
- Rejected actionable news is visible with full human-readable context and reason.
- Manual edited publication succeeds only after Telegram confirmation and cannot double-publish.
- Automatic publication transitions matching pending queue items to `published_auto`.
- Custom website/RSS and X sources can be added, disabled, and deleted without code edits.
- A broken custom source does not stop built-in sources.
- Panel outage has no effect on scheduled agent runs.
- Mobile layout is usable on an Android-size viewport.
