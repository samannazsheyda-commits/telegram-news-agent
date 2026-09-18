from __future__ import annotations

from flask import Blueprint, current_app, jsonify, session

from .command_center import _enqueue
from .luna_tools import LunaToolbox
from .luna_translation import translate_story_in_repository
from .openai_luna import LunaProviderError, get_luna_client


bp = Blueprint("luna_translation_api", __name__)


def _data():
    return current_app.extensions["editorial_data"]


def _find_live_story(story_id: str) -> dict | None:
    value, _ = _data().read_json("data/panel_live_feed.json", [])
    for row in value if isinstance(value, list) else []:
        if isinstance(row, dict) and str(row.get("id") or row.get("item_id") or row.get("story_id") or "") == story_id:
            return dict(row)
    return None


@bp.before_request
def require_admin():
    if not session.get("admin"):
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    return None


@bp.post("/api/panel/luna/translate-story/<story_id>")
def translate_story(story_id: str):
    try:
        result = translate_story_in_repository(
            _data(),
            story_id,
            get_luna_client(),
        )
    except LunaProviderError as exc:
        status = 503 if exc.retryable or exc.code == "missing_api_key" else 502
        return jsonify({"ok": False, "error": exc.code, "message": exc.message_fa, "retryable": exc.retryable}), status
    return jsonify(result), (200 if result.get("ok") else 422)


@bp.post("/api/panel/luna/block-story/<story_id>")
def block_story(story_id: str):
    result = LunaToolbox(_data()).execute(
        "reject_and_block_story",
        {"story_id": story_id, "reason": "dashboard_admin_block"},
        confirmed=True,
    )
    return jsonify(result), (200 if result.get("ok") else 409)


@bp.post("/api/panel/luna/publish-final/<story_id>")
def publish_final(story_id: str):
    row = _find_live_story(story_id)
    if row is None:
        return jsonify({"ok": False, "error": "story_not_found", "message": "خبر پیدا نشد."}), 404
    if str(row.get("luna_translation_status") or "") != "passed":
        return jsonify({"ok": False, "error": "translation_not_approved", "message": "این خبر هنوز ترجمه تأییدشده Luna ندارد."}), 409
    title = str(row.get("final_persian_title") or "").strip()
    body = str(row.get("final_persian_body") or "").strip()
    source = str(row.get("source") or "").strip()
    source_url = str(row.get("source_url") or row.get("link") or "").strip()
    original_title = str(row.get("original_title") or row.get("title") or "").strip()
    original_body = str(row.get("original_summary") or row.get("summary") or row.get("body") or "").strip()
    if not title or not source or not source_url or not original_title:
        return jsonify({"ok": False, "error": "publish_fields_missing", "message": "اطلاعات لازم برای انتشار کامل نیست."}), 409

    command_id = _enqueue(
        "v3_publish",
        item_id=story_id,
        news_key=str(row.get("news_key") or story_id),
        source=source,
        source_url=source_url,
        original_title=original_title,
        original_body=original_body,
        title=title,
        body=body,
        luna_v41_final=True,
        published_at=str(row.get("published_at_source") or row.get("published") or ""),
    )
    return jsonify({"ok": True, "status": "queued", "command_id": command_id, "message": "نسخه تأییدشده Luna در صف انتشار قرار گرفت."}), 202
