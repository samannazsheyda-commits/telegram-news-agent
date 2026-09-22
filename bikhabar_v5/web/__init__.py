from __future__ import annotations

from functools import wraps
from typing import Any

from flask import (
    Flask,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import check_password_hash

from ..operations import RuntimeSettings
from ..states import CANONICAL_STATES


def _positive_int(value: Any, default: int) -> int:
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return default


def create_app(
    *,
    store: Any,
    config: dict[str, Any] | None = None,
    luna: Any | None = None,
    transcriber: Any | None = None,
    builder: Any | None = None,
    job_queue: Any | None = None,
) -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.update(
        SECRET_KEY=None,
        ADMIN_USERNAME="admin",
        ADMIN_PASSWORD_HASH=None,
        WTF_CSRF_TIME_LIMIT=3600,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=True,
    )
    app.config.update(config or {})
    if not app.config.get("SECRET_KEY"):
        raise RuntimeError("Vision 5 panel SECRET_KEY is required")
    if not app.config.get("ADMIN_PASSWORD_HASH"):
        raise RuntimeError("Vision 5 panel ADMIN_PASSWORD_HASH is required")
    CSRFProtect(app)
    app.extensions["vision5_store"] = store
    app.extensions["vision5_luna"] = luna
    app.extensions["vision5_transcriber"] = transcriber
    app.extensions["vision5_builder"] = builder
    app.extensions["vision5_job_queue"] = job_queue
    app.config["LUNA_ENABLED"] = luna is not None
    app.config["BUILDER_ENABLED"] = builder is not None

    def current_user() -> str | None:
        username = session.get("vision5_user")
        return str(username) if username else None

    def login_required(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if current_user() is None:
                if request.path.startswith("/api/"):
                    return jsonify({"error": "authentication_required"}), 401
                return redirect(url_for("login", next=request.full_path.rstrip("?")))
            return view(*args, **kwargs)

        return wrapped

    def story_or_404(story_id: str) -> dict[str, Any]:
        story = store.get_story(story_id)
        if story is None:
            abort(404)
        return dict(story)

    def filters(default_statuses: tuple[str, ...]) -> dict[str, Any]:
        status_values = tuple(
            status
            for status in request.args.getlist("status")
            if status in CANONICAL_STATES
        )
        return {
            "statuses": status_values or default_statuses,
            "query": str(request.args.get("q") or "").strip(),
            "source": str(request.args.get("source") or "").strip(),
            "page": _positive_int(request.args.get("page"), 1),
            "page_size": 25,
        }

    @app.get("/healthz")
    def healthz():
        return jsonify({"status": "ok", "service": "vision5-panel"})

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            username = str(request.form.get("username") or "").strip()
            password = str(request.form.get("password") or "")
            valid_user = username == app.config["ADMIN_USERNAME"]
            valid_password = check_password_hash(app.config["ADMIN_PASSWORD_HASH"], password)
            if not (valid_user and valid_password):
                flash("نام کاربری یا رمز عبور نادرست است.", "error")
                return render_template("login.html"), 401
            session.clear()
            session["vision5_user"] = username
            return redirect(url_for("inbox"))
        return render_template("login.html")

    @app.post("/logout")
    @login_required
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.get("/")
    @login_required
    def inbox():
        selected = filters(("READY_FOR_REVIEW", "LUNA_TRANSLATED"))
        result = store.list_stories(**selected)
        return render_template("inbox.html", result=result, filters=selected)

    @app.get("/history")
    @login_required
    def history():
        selected = filters(("PUBLISHED",))
        result = store.list_stories(**selected)
        return render_template("history.html", result=result, filters=selected)

    @app.get("/control")
    @login_required
    def control():
        return render_template("control.html", metrics=store.dashboard_metrics())

    @app.route("/sources", methods=["GET", "POST"])
    @login_required
    def sources():
        if request.method == "POST":
            kind = str(request.form.get("kind") or "").strip().lower()
            identity = str(request.form.get("identity") or "").strip()
            display_name = str(request.form.get("display_name") or "").strip()
            if kind not in {"rss", "website", "x", "telegram", "manual"}:
                abort(400, description="unsupported source kind")
            if not identity or not display_name:
                abort(400, description="source identity and display_name are required")
            store.upsert_source(
                {"kind": kind, "identity": identity, "display_name": display_name, "enabled": True}
            )
            flash("منبع به رصد V5 اضافه شد.", "success")
            return redirect(url_for("sources"))
        return render_template("sources.html", sources=store.list_sources())

    @app.post("/sources/<source_id>/toggle")
    @login_required
    def toggle_source(source_id: str):
        enabled = str(request.form.get("enabled") or "").strip().lower() in {"1", "true", "yes", "on"}
        store.set_source_enabled(source_id, enabled=enabled, actor=current_user())
        flash("وضعیت منبع ذخیره شد.", "success")
        return redirect(url_for("sources"))

    @app.route("/settings", methods=["GET", "POST"])
    @login_required
    def settings():
        if request.method == "POST":
            try:
                settings_value = RuntimeSettings.from_mapping(request.form)
            except (TypeError, ValueError) as exc:
                abort(400, description=str(exc))
            store.upsert_newsroom_rule(
                "runtime_settings", settings_value.to_dict(), actor=current_user()
            )
            flash("تنظیمات اجرایی ذخیره شد.", "success")
            return redirect(url_for("settings"))
        row = store.get_newsroom_rule("runtime_settings")
        value = RuntimeSettings.from_mapping((row or {}).get("rule_json") or {}).to_dict()
        return render_template("settings.html", settings=value)

    @app.get("/system")
    @login_required
    def system_status():
        return render_template(
            "system.html",
            health=store.list_service_health(),
            audit=store.list_audit(limit=100),
        )

    @app.get("/luna")
    @login_required
    def luna_page():
        if luna is None:
            abort(503, description="Luna is not configured")
        return render_template("luna.html")

    @app.get("/stories/<story_id>")
    @login_required
    def review_story(story_id: str):
        return render_template("review.html", story=story_or_404(story_id))

    @app.post("/stories/<story_id>/review")
    @login_required
    def submit_review(story_id: str):
        story_or_404(story_id)
        action = str(request.form.get("action") or "").strip().lower()
        if action == "reject":
            reason = str(request.form.get("reject_reason") or "").strip()
            if not reason:
                abort(400, description="reject reason is required")
            store.reject_story(story_id, reason=reason, actor=current_user())
            flash("خبر برای همیشه رد شد.", "success")
            return redirect(url_for("inbox"))
        if action not in {"save", "approve"}:
            abort(400, description="unsupported review action")
        title = str(request.form.get("title") or "").strip()
        body = str(request.form.get("body") or "").strip()
        copy_mode = str(request.form.get("copy_mode") or "edited").strip().lower()
        if not title or copy_mode not in {"google", "luna", "edited"}:
            abort(400, description="valid final title and copy mode are required")
        store.save_review(
            story_id,
            title=title,
            body=body,
            copy_mode=copy_mode,
            actor=current_user(),
            approve=action == "approve",
        )
        if action == "approve" and job_queue is not None:
            job_queue.enqueue("publish", {"story_id": story_id, "allow_retry": False})
        flash("نسخه نهایی تأیید شد." if action == "approve" else "پیش‌نویس ذخیره شد.", "success")
        return redirect(url_for("inbox" if action == "approve" else "review_story", story_id=story_id))

    @app.post("/stories/<story_id>/luna")
    @login_required
    def luna_translation(story_id: str):
        story_or_404(story_id)
        if luna is None:
            abort(503, description="Luna is not configured")
        luna.alternate_translation(story_id=story_id, actor=current_user())
        flash("نسخه جایگزین Luna آماده شد.", "success")
        return redirect(url_for("review_story", story_id=story_id))

    @app.get("/api/stories")
    @login_required
    def stories_api():
        selected = filters(("READY_FOR_REVIEW", "LUNA_TRANSLATED"))
        return jsonify(store.list_stories(**selected))

    @app.post("/api/luna/chat")
    @login_required
    def luna_chat_api():
        if luna is None:
            return jsonify({"error": "luna_not_configured"}), 503
        payload = request.get_json(silent=True) or {}
        message = str(payload.get("message") or "").strip()
        if not message:
            return jsonify({"error": "message_required"}), 400
        story_id = str(payload.get("story_id") or "").strip() or None
        return jsonify(luna.chat(user_id=current_user(), message=message, story_id=story_id))

    @app.post("/api/luna/voice")
    @login_required
    def luna_voice_api():
        if transcriber is None:
            return jsonify({"error": "voice_not_configured"}), 503
        upload = request.files.get("voice")
        if upload is None:
            return jsonify({"error": "voice_required"}), 400
        audio = upload.read(20 * 1024 * 1024 + 1)
        if len(audio) > 20 * 1024 * 1024:
            return jsonify({"error": "voice_too_large"}), 413
        transcript = transcriber.transcribe(
            audio=audio,
            filename=upload.filename or "voice.ogg",
            content_type=upload.mimetype or "audio/ogg",
        )
        return jsonify({"transcript": transcript})

    @app.post("/api/luna/builder/prepare")
    @login_required
    def builder_prepare_api():
        if builder is None:
            return jsonify({"error": "builder_not_configured"}), 503
        payload = request.get_json(silent=True) or {}
        result = builder.prepare(
            change_id=str(payload.get("change_id") or ""),
            patch=str(payload.get("patch") or ""),
            actor=current_user(),
        )
        return jsonify(result), 201

    @app.post("/api/luna/builder/deploy")
    @login_required
    def builder_deploy_api():
        if builder is None:
            return jsonify({"error": "builder_not_configured"}), 503
        payload = request.get_json(silent=True) or {}
        return jsonify(
            builder.deploy(
                branch=str(payload.get("branch") or ""),
                actor=current_user(),
                confirmation_token=str(payload.get("confirmation_token") or ""),
            )
        )

    return app


__all__ = ["create_app"]
