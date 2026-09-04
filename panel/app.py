from __future__ import annotations

import os
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
from src.services import send_telegram
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
            app.config["GITHUB_REPOSITORY"],
            app.config["GITHUB_DATA_TOKEN"],
            branch=app.config.get("GITHUB_BRANCH", "main"),
        )
    app.extensions["editorial_data"] = data

    @app.context_processor
    def globals_for_templates():
        return {"reason_fa": REASON_FA}

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if _authenticated():
            return redirect(url_for("dashboard"))
        form = LoginForm()
        ip = request.remote_addr or "unknown"
        if form.validate_on_submit():
            if _rate_limited(ip):
                flash("تعداد تلاش‌ها زیاد بوده. چند دقیقه بعد دوباره امتحان کن.", "error")
                return render_template("login.html", form=form), 429
            password_hash = app.config.get("PANEL_PASSWORD_HASH", "")
            if not password_hash or not check_password_hash(password_hash, form.password.data):
                _record_login_failure(ip)
                flash("رمز ورود درست نیست.", "error")
            else:
                _login_attempts.pop(ip, None)
                session.clear()
                session["admin"] = True
                session.permanent = True
                return redirect(request.args.get("next") or url_for("dashboard"))
        return render_template("login.html", form=form)

    @app.post("/logout")
    @login_required
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.get("/")
    @login_required
    def dashboard():
        queue = _effective_queue(data)
        history = _read_list(data, "data/editorial_history.json")
        published_today = sum(1 for r in history if r.get("status") in {"published_manual", "published_auto"} and _same_tehran_day(str(r.get("decision_at") or r.get("updated_at") or "")))
        rejected_today = sum(1 for r in history if r.get("status") in {"rejected_manual", "superseded"} and _same_tehran_day(str(r.get("decision_at") or r.get("updated_at") or "")))
        state, _ = data.read_json("state.json", {})
        last_publication = next((r.get("decision_at") or r.get("updated_at") for r in history if r.get("status") in {"published_manual", "published_auto"}), "")
        return render_template(
            "dashboard.html",
            queue_count=len(queue),
            published_today=published_today,
            rejected_today=rejected_today,
            last_publication=last_publication,
            bot_active=True,
            state=state if isinstance(state, dict) else {},
        )

    @app.get("/review")
    @login_required
    def review_queue():
        return render_template("review_queue.html", items=_effective_queue(data))

    @app.route("/review/<item_id>", methods=["GET", "POST"])
    @login_required
    def review_edit(item_id: str):
        history = _read_list(data, "data/editorial_history.json")
        if any(r.get("id") == item_id and r.get("status") in TERMINAL_STATUSES for r in history):
            flash("این خبر قبلاً تعیین تکلیف شده.", "info")
            return redirect(url_for("review_queue"))
        record = next((r for r in _effective_queue(data) if r.get("id") == item_id), None)
        if record is None:
            abort(404)
        form = ReviewEditForm()
        if request.method == "GET":
            form.title_fa.data = str(record.get("persian_title") or "")
            form.body_fa.data = str(record.get("persian_body") or "")
        if form.validate_on_submit():
            if form.reject.data:
                now = _now_iso()
                final = dict(record)
                final.update(status="rejected_manual", decision_at=now, updated_at=now)
                _upsert_record(data, "data/editorial_history.json", final, "chore: manually reject editorial item")
                _remove_record(data, "data/editorial_queue.json", item_id, "chore: remove rejected editorial item")
                flash("خبر رد نهایی شد.", "success")
                return redirect(url_for("review_queue"))

            title_fa = (form.title_fa.data or "").strip()
            body_fa = (form.body_fa.data or "").strip()
            if not record.get("source") or not record.get("source_url"):
                flash("این خبر منبع یا لینک معتبر ندارد و قابل انتشار نیست.", "error")
            else:
                message = _build_message(record, title_fa, body_fa)
                if not message:
                    flash("متن خبر برای انتشار معتبر نیست.", "error")
                else:
                    try:
                        send_telegram(message, app.config["TELEGRAM_BOT_TOKEN"], app.config["TELEGRAM_CHAT_ID"])
                    except Exception as exc:
                        flash(f"ارسال تلگرام ناموفق بود: {exc}", "error")
                    else:
                        now = _now_iso()
                        final = dict(record)
                        final.update(
                            status="published_manual",
                            final_persian_title=title_fa,
                            final_persian_body=body_fa,
                            decision_at=now,
                            updated_at=now,
                        )
                        # History first: even if a later GitHub write conflicts, the item becomes non-publishable.
                        _upsert_record(data, "data/editorial_history.json", final, "chore: record manual telegram publication")
                        try:
                            data.mark_news_seen(str(record.get("news_key") or ""))
                        finally:
                            _remove_record(data, "data/editorial_queue.json", item_id, "chore: remove manually published editorial item")
                        flash("خبر با موفقیت در تلگرام منتشر شد.", "success")
                        return redirect(url_for("review_queue"))
        return render_template("review_edit.html", item=record, form=form)

    @app.get("/history")
    @login_required
    def history():
        records = _read_list(data, "data/editorial_history.json")
        status = request.args.get("status", "")
        if status:
            records = [r for r in records if r.get("status") == status]
        return render_template("history.html", items=records, status=status)

    @app.route("/sources", methods=["GET"])
    @login_required
    def sources():
        records = _read_list(data, "data/custom_sources.json")
        return render_template(
            "sources.html",
            sources=records,
            website_form=WebsiteSourceForm(prefix="web"),
            x_form=XSourceForm(prefix="x"),
        )

    @app.post("/sources/website")
    @login_required
    def add_website_source():
        form = WebsiteSourceForm(prefix="web")
        if not form.validate_on_submit():
            flash("اطلاعات سایت کامل یا معتبر نیست.", "error")
            return redirect(url_for("sources"))
        try:
            source = validate_website_source(form.name.data, form.website_url.data, form.feed_url.data or "")
            record = asdict(source)
            if not record.get("feed_url"):
                try:
                    feed = discover_feed_url(record["website_url"])
                except Exception as exc:
                    record["last_error"] = str(exc)[:240]
                    feed = ""
                if feed:
                    record["feed_url"] = feed
                    record["status"] = "active"
                else:
                    record["status"] = "needs_feed"
            _upsert_record(data, "data/custom_sources.json", record, "chore: add custom website source")
            flash("منبع سایت ذخیره شد.", "success")
        except ValueError:
            flash("آدرس سایت یا RSS معتبر نیست.", "error")
        return redirect(url_for("sources"))

    @app.post("/sources/x")
    @login_required
    def add_x_source():
        form = XSourceForm(prefix="x")
        if not form.validate_on_submit():
            flash("آی‌دی X معتبر نیست.", "error")
            return redirect(url_for("sources"))
        try:
            record = asdict(XSource.create(form.handle.data, form.name.data or ""))
            _upsert_record(data, "data/custom_sources.json", record, "chore: add custom x source")
            flash("حساب X به لیست بررسی اضافه شد.", "success")
        except ValueError:
            flash("آی‌دی X معتبر نیست.", "error")
        return redirect(url_for("sources"))

    @app.post("/sources/<source_id>/toggle")
    @login_required
    def toggle_source(source_id: str):
        def transform(records):
            found = False
            for record in records:
                if record.get("id") == source_id:
                    record["active"] = not bool(record.get("active", True))
                    record["updated_at"] = _now_iso()
                    found = True
                    break
            if not found:
                abort(404)
            return records
        _write_latest_list(data, "data/custom_sources.json", transform, "chore: toggle custom source")
        return redirect(url_for("sources"))

    @app.post("/sources/<source_id>/delete")
    @login_required
    def delete_source(source_id: str):
        _remove_record(data, "data/custom_sources.json", source_id, "chore: delete custom source")
        flash("منبع حذف شد.", "success")
        return redirect(url_for("sources"))

    return app
