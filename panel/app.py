from __future__ import annotations

import os
import re
import time
from collections import defaultdict, deque
from dataclasses import asdict
from datetime import datetime, timezone
from functools import wraps
from zoneinfo import ZoneInfo

import requests
from flask import Flask, abort, flash, redirect, render_template, request, session, url_for
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import check_password_hash

from src.custom_sources import XSource, discover_feed_url, validate_website_source
from src.formatters import format_news
from src.github_data import GitHubJsonRepository
from src.services import send_telegram, translate_to_fa
from src.sources import NewsItem

from .forms import LoginForm, ReviewEditForm, WebsiteSourceForm, XSourceForm


TEHRAN = ZoneInfo("Asia/Tehran")
TERMINAL_STATUSES = {"published_manual", "published_auto", "rejected_manual", "superseded"}
REASON_FA = {
    "article_or_commentary": "تحلیل / یادداشت سردبیری",
    "low_signal": "اهمیت خبری پایین",
    "low_signal_or_unapproved_source": "اهمیت پایین یا منبع تأییدنشده",
    "duplicate_or_redundant": "تکراری یا بسیار مشابه",
    "bundled_headline": "چند خبر در یک تیتر",
    "bundled_or_multi_headline": "چند خبر در یک تیتر",
    "translation_failed": "ترجمه ناموفق",
    "translation_failed_retry_later": "ترجمه ناموفق؛ قابل بررسی دستی",
    "unapproved_source": "منبع تأییدنشده",
    "invalid_publish_time": "زمان انتشار نامعتبر",
    "stale": "قدیمی",
    "not_today_tehran": "مربوط به امروز تهران نیست",
    "vague_or_speculative": "مبهم یا گمانه‌زنی",
    "question_or_explainer": "پرسشی / توضیحی",
    "filtered_question_or_article": "پرسشی / مقاله‌ای",
    "filtered_incomplete_or_teaser": "ناقص / پیش‌نمایش مقاله",
    "no_matching_event": "رویداد تازه",
    "same_source_identity_already_seen": "همان خبر قبلاً دیده شده",
    "auto_publish_off": "انتشار خودکار خاموش است",
    "publish_failed": "ارسال به تلگرام ناموفق بود",
    "eligible": "خبر معتبر",
}
PANEL_STATUS_FA = {
    "new": "تازه",
    "auto_published": "منتشرشده خودکار",
    "waiting": "در انتظار بررسی",
    "duplicate": "تکراری",
    "rejected": "ردشده",
    "failed": "خطای انتشار",
}


csrf = CSRFProtect()
_login_attempts: dict[str, deque[float]] = defaultdict(deque)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today_tehran() -> str:
    return datetime.now(timezone.utc).astimezone(TEHRAN).date().isoformat()


def _same_tehran_day(value: str) -> bool:
    if not value:
        return False
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(TEHRAN).date().isoformat() == _today_tehran()
    except ValueError:
        return False


def _authenticated() -> bool:
    return bool(session.get("admin"))


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not _authenticated():
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def _rate_limited(ip: str) -> bool:
    now = time.monotonic()
    bucket = _login_attempts[ip]
    while bucket and now - bucket[0] > 600:
        bucket.popleft()
    return len(bucket) >= 8


def _record_login_failure(ip: str) -> None:
    _login_attempts[ip].append(time.monotonic())


def _read_list(data, path: str) -> list[dict]:
    value, _ = data.read_json(path, [])
    return value if isinstance(value, list) else []


def _effective_queue(data) -> list[dict]:
    queue = _read_list(data, "data/editorial_queue.json")
    history = _read_list(data, "data/editorial_history.json")
    terminal = {r.get("id") for r in history if r.get("status") in TERMINAL_STATUSES}
    return [r for r in queue if r.get("status", "pending") == "pending" and r.get("id") not in terminal]


def _has_persian(value: str) -> bool:
    return bool(re.search(r"[\u0600-\u06ff]", str(value or "")))


def _live_feed(data, translator=None) -> list[dict]:
    """Read dashboard feed without external translation/network work.

    The live JSON endpoint is the authoritative V3 renderer. This legacy
    server-side list only seeds initial markup and therefore must stay cheap.
    """
    rows = sorted(
        _read_list(data, "data/panel_live_feed.json"),
        key=lambda r: str(r.get("updated_at") or r.get("discovered_at") or ""),
        reverse=True,
    )
    localized: list[dict] = []
    for row in rows[:80]:
        item = dict(row)
        title = str(item.get("persian_title") or item.get("display_title") or "").strip()
        item["display_title"] = title if _has_persian(title) else "عنوان فارسی در حال آماده‌سازی"
        item["panel_status_fa"] = PANEL_STATUS_FA.get(str(item.get("panel_status") or ""), "در حال پردازش")
        item["decision_reason_fa"] = REASON_FA.get(str(item.get("decision_reason") or ""), "")
        localized.append(item)
    return localized


def _published_history(data) -> list[dict]:
    rows = _read_list(data, "data/editorial_history.json")
    return [r for r in rows if r.get("status") in {"published_manual", "published_auto"}]


def _write_latest_list(data, path: str, transform, message: str) -> list[dict]:
    for attempt in range(2):
        current, sha = data.read_json(path, [])
        if not isinstance(current, list):
            current = []
        updated = transform([dict(x) for x in current])
        try:
            data.write_json(path, updated, sha, message)
            return updated
        except requests.HTTPError as exc:
            status = getattr(exc.response, "status_code", None)
            if attempt == 0 and status in {409, 422}:
                continue
            raise
    raise RuntimeError("github_write_conflict")


def _upsert_record(data, path: str, record: dict, message: str) -> list[dict]:
    def transform(records):
        records = [r for r in records if r.get("id") != record.get("id")]
        records.insert(0, dict(record))
        return records
    return _write_latest_list(data, path, transform, message)


def _remove_record(data, path: str, record_id: str, message: str) -> list[dict]:
    return _write_latest_list(
        data,
        path,
        lambda records: [r for r in records if r.get("id") != record_id],
        message,
    )


def _build_message(record: dict, title_fa: str, body_fa: str) -> str:
    item = NewsItem(
        key=str(record.get("news_key") or ""),
        source=str(record.get("source") or ""),
        title=str(record.get("original_title") or ""),
        summary=str(record.get("original_summary") or ""),
        link=str(record.get("source_url") or ""),
        published=str(record.get("published_at_source") or ""),
    )
    return format_news(item, title_fa, body_fa, marker_override="⚪️")


def create_app(config: dict | None = None):
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("PANEL_SECRET_KEY", ""),
        PANEL_PASSWORD_HASH=os.environ.get("PANEL_PASSWORD_HASH", ""),
        TELEGRAM_BOT_TOKEN=os.environ.get("TELEGRAM_BOT_TOKEN", ""),
        TELEGRAM_CHAT_ID=os.environ.get("TELEGRAM_CHAT_ID", "@bikhabaar"),
        GITHUB_DATA_TOKEN=os.environ.get("GITHUB_DATA_TOKEN", ""),
        GITHUB_REPOSITORY=os.environ.get("GITHUB_REPOSITORY", "samannazsheyda-commits/telegram-news-agent"),
        GITHUB_BRANCH=os.environ.get("GITHUB_BRANCH", "main"),
        LIVE_FEED_TRANSLATOR=translate_to_fa,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=True,
        MAX_CONTENT_LENGTH=64 * 1024,
    )
    if config:
        app.config.update(config)
    if app.config.get("TESTING"):
        app.config["SESSION_COOKIE_SECURE"] = False
    if not app.config.get("SECRET_KEY"):
        raise RuntimeError("PANEL_SECRET_KEY is required")

    csrf.init_app(app)

    data = app.config.get("DATA_BACKEND")
    if data is None:
        data = GitHubJsonRepository(
            token=app.config.get("GITHUB_DATA_TOKEN", ""),
            repository=app.config.get("GITHUB_REPOSITORY", ""),
            branch=app.config.get("GITHUB_BRANCH", "main"),
        )
    app.extensions["editorial_data"] = data

    @app.context_processor
    def inject_csrf_token():
        from flask_wtf.csrf import generate_csrf
        return {"csrf_token": generate_csrf}

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if _authenticated():
            return redirect(url_for("dashboard"))
        form = LoginForm()
        ip = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown").split(",")[0].strip()
        if request.method == "POST" and _rate_limited(ip):
            abort(429)
        if form.validate_on_submit():
            password_hash = app.config.get("PANEL_PASSWORD_HASH", "")
            if password_hash and check_password_hash(password_hash, form.password.data):
                session.clear()
                session["admin"] = True
                return redirect(request.args.get("next") or url_for("dashboard"))
            _record_login_failure(ip)
            flash("رمز عبور نادرست است.", "error")
        return render_template("login.html", form=form)

    @app.post("/logout")
    @login_required
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.get("/")
    @login_required
    def dashboard():
        live = _live_feed(data)
        pending = _effective_queue(data)
        history = _read_list(data, "data/editorial_history.json")
        published = [r for r in history if r.get("status") in {"published_manual", "published_auto"}]
        rejected = [r for r in history if r.get("status") == "rejected_manual"]
        today_published = [r for r in published if _same_tehran_day(str(r.get("acted_at") or r.get("published_at") or ""))]
        today_rejected = [r for r in rejected if _same_tehran_day(str(r.get("acted_at") or ""))]
        weather_preview, _ = data.read_json("data/weather_preview.json", {})
        state, _ = data.read_json("data/state.json", {})
        if not isinstance(weather_preview, dict):
            weather_preview = {}
        if not isinstance(state, dict):
            state = {}
        return render_template(
            "dashboard.html",
            live=live,
            pending=pending,
            published=published,
            live_count=len(live),
            queue_count=len(pending),
            published_today=len(today_published),
            rejected_today=len(today_rejected),
            weather_preview=weather_preview,
            last_publication=str(state.get("last_publication") or "—"),
        )

    @app.get("/queue")
    @login_required
    def review_queue():
        return render_template("queue.html", items=_effective_queue(data))

    @app.route("/queue/<item_id>", methods=["GET", "POST"])
    @login_required
    def review_edit(item_id: str):
        queue = _effective_queue(data)
        record = next((r for r in queue if str(r.get("id")) == item_id), None)
        if record is None:
            abort(404)
        form = ReviewEditForm()
        if request.method == "GET":
            form.title_fa.data = record.get("persian_title") or ""
            form.body_fa.data = record.get("persian_body") or ""
        if form.validate_on_submit():
            now = _now_iso()
            if form.action.data == "reject":
                history_record = dict(record)
                history_record.update({"status": "rejected_manual", "acted_at": now, "id": item_id})
                _upsert_record(data, "data/editorial_history.json", history_record, f"Reject editorial item {item_id}")
                flash("خبر رد شد.", "success")
                return redirect(url_for("review_queue"))

            title_fa = (form.title_fa.data or "").strip()
            body_fa = (form.body_fa.data or "").strip()
            if not title_fa:
                flash("تیتر فارسی لازم است.", "error")
                return render_template("review.html", form=form, item=record)
            message = _build_message(record, title_fa, body_fa)
            telegram_result = send_telegram(
                app.config.get("TELEGRAM_BOT_TOKEN", ""),
                app.config.get("TELEGRAM_CHAT_ID", ""),
                message,
            )
            history_record = dict(record)
            history_record.update({
                "status": "published_manual" if telegram_result else "publish_failed",
                "acted_at": now,
                "final_persian_title": title_fa,
                "final_persian_body": body_fa,
                "id": item_id,
            })
            _upsert_record(data, "data/editorial_history.json", history_record, f"Publish editorial item {item_id}")
            if telegram_result:
                flash("خبر منتشر شد.", "success")
                return redirect(url_for("review_queue"))
            flash("ارسال تلگرام ناموفق بود.", "error")
        return render_template("review.html", form=form, item=record)

    @app.get("/history")
    @login_required
    def history():
        status_filter = request.args.get("status", "").strip()
        rows = _read_list(data, "data/editorial_history.json")
        if status_filter:
            rows = [r for r in rows if r.get("status") == status_filter]
        return render_template("history.html", items=rows)

    @app.route("/sources", methods=["GET", "POST"])
    @login_required
    def sources():
        websites = _read_list(data, "data/website_sources.json")
        x_sources = _read_list(data, "data/x_sources.json")
        website_form = WebsiteSourceForm(prefix="website")
        x_form = XSourceForm(prefix="x")

        if website_form.submit.data and website_form.validate_on_submit():
            try:
                feed_url = discover_feed_url(website_form.url.data)
                validate_website_source(feed_url)
            except Exception:
                flash("RSS معتبر پیدا نشد یا سایت در دسترس نبود.", "error")
                return render_template("sources.html", websites=websites, x_sources=x_sources, website_form=website_form, x_form=x_form)
            record = {
                "id": f"web-{int(time.time())}",
                "name": website_form.name.data.strip(),
                "url": website_form.url.data.strip(),
                "feed_url": feed_url,
                "active": bool(website_form.active.data),
                "created_at": _now_iso(),
            }
            _upsert_record(data, "data/website_sources.json", record, "Add website source")
            flash("منبع سایت اضافه شد.", "success")
            return redirect(url_for("sources"))

        if x_form.submit.data and x_form.validate_on_submit():
            source = XSource(x_form.handle.data)
            record = {
                "id": f"x-{source.handle.lower()}",
                "name": x_form.name.data.strip(),
                "handle": source.handle,
                "active": bool(x_form.active.data),
                "created_at": _now_iso(),
            }
            _upsert_record(data, "data/x_sources.json", record, "Add X source")
            flash("اکانت X اضافه شد.", "success")
            return redirect(url_for("sources"))

        return render_template("sources.html", websites=websites, x_sources=x_sources, website_form=website_form, x_form=x_form)

    @app.post("/sources/website/<source_id>/delete")
    @login_required
    def delete_website_source(source_id: str):
        _remove_record(data, "data/website_sources.json", source_id, "Delete website source")
        flash("منبع سایت حذف شد.", "success")
        return redirect(url_for("sources"))

    @app.post("/sources/x/<source_id>/delete")
    @login_required
    def delete_x_source(source_id: str):
        _remove_record(data, "data/x_sources.json", source_id, "Delete X source")
        flash("منبع X حذف شد.", "success")
        return redirect(url_for("sources"))

    return app
