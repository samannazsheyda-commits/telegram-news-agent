from __future__ import annotations

from flask import Blueprint, current_app, jsonify, session

from .command_center import _enqueue
from .luna_publish import publish_story
from .luna_tools import LunaToolbox
from .luna_translation import translate_story_in_repository
from .openai_luna import LunaProviderError, get_luna_client


bp = Blueprint("luna_translation_api", __name__)


def _data():
    return current_app.extensions["editorial_data"]


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
    result = publish_story(
        _data(),
        story_id,
        enqueue=_enqueue,
        confirmed=True,
    )
    if result.get("ok"):
        return jsonify(result), 202
    status = 404 if result.get("error") == "story_not_found" else 409
    return jsonify(result), status
