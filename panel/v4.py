from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Callable

from flask import Blueprint, current_app, jsonify, redirect, render_template, request, session, url_for

from src.ai_newsroom import AIServiceError
from src.one_x_ai_newsroom import OneXAINewsAI
from src.services import translate_to_fa

from .command_center import _enqueue, _find_live_item, _review_record_from_live, _settings, _write_list, _write_settings


bp = Blueprint("panel_v4", __name__)
_ALLOWED_LUNA_DECISIONS = {"PUBLISH", "REJECT", "WAIT", "SPECIAL"}


def _data():
    return current_app.extensions["editorial_data"]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rows(path: str) -> list[dict]:
    value, _ = _data().read_json(path, [])
    return [dict(row) for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _read(path: str, default):
    value, _ = _data().read_json(path, default)
    return value


def _story_id(row: dict) -> str:
    return str(row.get("item_id") or row.get("id") or row.get("news_key") or "").strip()


def _source_text(row: dict) -> str:
    title = str(row.get("original_title") or row.get("title") or "").strip()
    body = str(row.get("original_summary") or row.get("summary") or row.get("body") or "").strip()
    return f"TITLE:\n{title}\n\nBODY:\n{body}".strip()


def _has_persian(value: str) -> bool:
    return bool(re.search(r"[\u0600-\u06ff]", str(value or "")))


def _normalise_preview(raw: dict[str, Any], *, story_id: str) -> dict[str, Any]:
    decision = str(raw.get("decision") or "").strip().upper()
    if decision not in _ALLOWED_LUNA_DECISIONS:
        raise ValueError("invalid_luna_decision")
    try:
        importance = float(raw.get("importance") or 0)
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid_luna_importance") from exc
    if importance > 10:
        importance = importance / 10.0
    importance = max(0.0, min(10.0, round(importance, 1)))
    reason = str(raw.get("reason_fa") or raw.get("reason") or "").strip()
    title = str(raw.get("title_fa") or "").strip()
    body = str(raw.get("body_fa") or "").strip()
    try:
        confidence = float(raw.get("confidence") or 0)
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))
    if not reason:
        raise ValueError("invalid_luna_reason")
    if decision in {"PUBLISH", "SPECIAL"} and (not title or not _has_persian(title) or not body or not _has_persian(body)):
        raise ValueError("invalid_luna_final_copy")
    return {
        "story_id": story_id,
        "decision": decision,
        "importance": importance,
        "reason_fa": reason,
        "title_fa": title,
        "body_fa": body,
        "confidence": confidence,
        "special_reason": str(raw.get("special_reason") or "").strip() or None,
        "updated_at": _now_iso(),
    }


def _default_luna_finalizer(row: dict) -> dict[str, Any]:
    service = OneXAINewsAI()
    if not service.available:
        raise AIServiceError("luna_unavailable")
    source = _source_text(row)
    return service._chat_json(
        model=service.config.editorial_model,
        system=(
            "You are Luna, editor-in-chief of Bikhabar. Return exactly one JSON object. "
            "Judge whether this is a real, current, event-driven news development worth publishing. "
            "Reject opinion, analysis, teasers, generic reports and duplicates. Write concise natural Persian, "
            "preserve names, numbers, attribution and meaning, and never add facts. "
            "Required keys: decision (PUBLISH|REJECT|WAIT|SPECIAL), importance (0-10), reason_fa, "
            "title_fa, body_fa, confidence (0-1), special_reason. For REJECT, title_fa/body_fa may be empty."
        ),
        user=source,
        max_tokens=1100,
    )


def _finalizer() -> Callable[[dict], dict]:
    injected = current_app.config.get("PANEL_LUNA_FINALIZER")
    return injected if callable(injected) else _default_luna_finalizer


def _machine_translator() -> Callable[[str], str]:
    injected = current_app.config.get("PANEL_MACHINE_TRANSLATOR")
    return injected if callable(injected) else translate_to_fa


def _upsert(path: str, record: dict, *, id_key: str, message: str) -> list[dict]:
    target = str(record.get(id_key) or "")
    return _write_list(path, lambda rows: [record] + [row for row in rows if str(row.get(id_key) or "") != target], message)


def _update_live_story(story_id: str, **fields) -> None:
    def transform(rows: list[dict]) -> list[dict]:
        for row in rows:
            if _story_id(row) == story_id:
                row.update(fields)
                break
        return rows

    _write_list("data/panel_live_feed.json", transform, "panel v4: persist preview state")


def _preview_for(story_id: str) -> dict | None:
    return next((row for row in _rows("data/panel_luna_previews.json") if str(row.get("story_id") or "") == story_id), None)


def _audit(action: str, target: str, *, actor: str = "user", before=None, after=None, result: str = "ok") -> None:
    record = {
        "timestamp": _now_iso(),
        "actor": actor,
        "action": action,
        "target": target,
        "before": before,
        "after": after,
        "result": result,
    }
    _write_list("data/panel_audit_log.json", lambda rows: ([record] + rows)[:500], "panel v4: audit action")


@bp.before_request
def require_admin():
    if session.get("admin"):
        return None
    if request.path.startswith("/api/"):
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    return redirect(url_for("login", next=request.path))


@bp.get("/intake")
def intake_page():
    query = str(request.args.get("q") or "").strip().casefold()
    source = str(request.args.get("source") or "").strip().casefold()
    rows = _rows("data/panel_live_feed.json")
    rows.sort(key=lambda row: str(row.get("updated_at") or row.get("discovered_at") or ""), reverse=True)
    if query:
        rows = [row for row in rows if query in (str(row.get("original_title") or row.get("title") or "") + " " + str(row.get("original_summary") or row.get("summary") or "")).casefold()]
    if source:
        rows = [row for row in rows if source in str(row.get("source") or "").casefold()]
    return render_template("intake.html", items=rows[:30], query=request.args.get("q", ""), source_filter=request.args.get("source", ""))


@bp.get("/luna")
def luna_page():
    previews = _rows("data/panel_luna_previews.json")[:50]
    return render_template("luna.html", previews=previews)


@bp.get("/settings")
def settings_page():
    settings, _ = _settings()
    state = _read("state.json", {})
    return render_template("settings_v4.html", settings=settings, state=state if isinstance(state, dict) else {})


@bp.post("/settings/quotas")
def update_quotas():
    def _bounded(value: str, default: int, upper: int) -> int:
        try:
            return max(0, min(upper, int(value)))
        except (TypeError, ValueError):
            return default

    current, _ = _settings()
    regular = _bounded(request.form.get("daily_limit", ""), int(current.get("daily_limit") or 35), 200)
    special = _bounded(request.form.get("special_daily_limit", ""), int(current.get("special_daily_limit") or 5), 50)
    before = {"daily_limit": current.get("daily_limit", 35), "special_daily_limit": current.get("special_daily_limit", 5)}
    _write_settings(lambda value: {**value, "daily_limit": regular, "special_daily_limit": special})
    _audit("update_quotas", "newsroom_settings", before=before, after={"daily_limit": regular, "special_daily_limit": special})
    return redirect(url_for("panel_v4.settings_page"))


@bp.get("/system")
def system_page():
    state = _read("state.json", {})
    v3 = _read("data/newsroom_v3_production_status.json", {})
    audit = _rows("data/panel_audit_log.json")[:50]
    return render_template("system_health.html", state=state if isinstance(state, dict) else {}, v3=v3 if isinstance(v3, dict) else {}, audit=audit)


@bp.post("/api/panel/machine-preview/<story_id>")
def machine_preview(story_id: str):
    row = _find_live_item(story_id)
    if row is None:
        return jsonify({"ok": False, "error": "story_not_found", "message": "خبر پیدا نشد"}), 404
    cached = str(row.get("machine_translation") or row.get("machine_preview") or "").strip()
    if cached:
        return jsonify({"ok": True, "preview": cached, "label": "🌐 ترجمه ماشینی", "cached": True})
    source = _source_text(row)
    try:
        preview = str(_machine_translator()(source) or "").strip()
    except Exception as exc:
        return jsonify({"ok": False, "error": "machine_translation_failed", "message": "ترجمه ماشینی موقتاً در دسترس نیست", "detail": type(exc).__name__}), 503
    if not preview:
        return jsonify({"ok": False, "error": "machine_translation_failed", "message": "ترجمه ماشینی موقتاً در دسترس نیست"}), 503
    _update_live_story(story_id, machine_translation=preview, machine_translation_at=_now_iso())
    return jsonify({"ok": True, "preview": preview, "label": "🌐 ترجمه ماشینی", "cached": False})


@bp.post("/api/panel/luna/preview/<story_id>")
def luna_preview(story_id: str):
    row = _find_live_item(story_id)
    if row is None:
        return jsonify({"ok": False, "error": "story_not_found", "message": "خبر پیدا نشد"}), 404
    try:
        raw = _finalizer()(dict(row))
        if not isinstance(raw, dict):
            raise ValueError("invalid_luna_payload")
        preview = _normalise_preview(raw, story_id=story_id)
    except (AIServiceError, ValueError) as exc:
        _audit("luna_preview", story_id, actor="luna", result=f"failed:{type(exc).__name__}")
        return jsonify({"ok": False, "error": "luna_preview_failed", "message": "Luna نتوانست نسخه نهایی معتبر بسازد"}), 503

    _upsert("data/panel_luna_previews.json", preview, id_key="story_id", message="panel v4: save Luna preview")
    _update_live_story(
        story_id,
        final_persian_title=preview["title_fa"],
        final_persian_body=preview["body_fa"],
        luna_decision=preview["decision"],
        importance=preview["importance"],
        decision_reason_fa=preview["reason_fa"],
        luna_confidence=preview["confidence"],
        luna_reviewed_at=preview["updated_at"],
    )
    review = _review_record_from_live(row, story_id)
    review.update(
        persian_title=preview["title_fa"],
        persian_body=preview["body_fa"],
        final_persian_title=preview["title_fa"],
        final_persian_body=preview["body_fa"],
        luna_decision=preview["decision"],
        luna_importance=preview["importance"],
        luna_reason_fa=preview["reason_fa"],
        updated_at=preview["updated_at"],
    )
    _upsert("data/editorial_queue.json", review, id_key="id", message="panel v4: stage Luna preview for review")
    _audit("luna_preview", story_id, actor="luna", after={"decision": preview["decision"], "importance": preview["importance"]})
    return jsonify({"ok": True, "preview": preview, "review_url": f"/review/{story_id}"})


@bp.post("/api/panel/luna/publish/<story_id>")
def publish_luna_preview(story_id: str):
    row = _find_live_item(story_id)
    if row is None:
        return jsonify({"ok": False, "error": "story_not_found", "message": "خبر پیدا نشد"}), 404
    preview = _preview_for(story_id)
    if preview is None:
        return jsonify({"ok": False, "error": "luna_preview_required", "message": "قبل از انتشار باید نسخه نهایی Luna را ببینی"}), 409
    if str(preview.get("decision") or "") not in {"PUBLISH", "SPECIAL"}:
        return jsonify({"ok": False, "error": "luna_preview_not_publishable", "message": "تصمیم Luna برای این خبر انتشار نیست"}), 409
    title = str(preview.get("title_fa") or "").strip()
    body = str(preview.get("body_fa") or "").strip()
    if not title or not body:
        return jsonify({"ok": False, "error": "luna_preview_invalid", "message": "نسخه نهایی Luna ناقص است"}), 409

    review = _review_record_from_live(row, story_id)
    review.update(
        persian_title=title,
        persian_body=body,
        final_persian_title=title,
        final_persian_body=body,
        luna_decision=preview.get("decision"),
        luna_importance=preview.get("importance"),
        luna_reason_fa=preview.get("reason_fa"),
        updated_at=_now_iso(),
    )
    _upsert("data/editorial_queue.json", review, id_key="id", message="panel v4: approve Luna final preview")
    command_id = _enqueue(
        "v3_publish",
        item_id=story_id,
        news_key=str(row.get("news_key") or story_id),
        source=str(row.get("source") or ""),
        source_url=str(row.get("source_url") or row.get("link") or ""),
        title=title,
        body=body,
        published_at=str(row.get("published_at_source") or row.get("published") or ""),
    )
    _audit("publish_after_luna_preview", story_id, after={"command_id": command_id, "decision": preview.get("decision")})
    return jsonify({"ok": True, "status": "queued", "command_id": command_id, "message": "نسخه تأییدشده Luna در صف انتشار قرار گرفت"}), 202
