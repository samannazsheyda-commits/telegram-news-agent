from __future__ import annotations

from flask import Blueprint, current_app, jsonify, session

from .luna_translation import translate_story_in_repository
from .openai_luna import LunaProviderError, get_luna_client


bp = Blueprint("luna_translation_api", __name__)


@bp.before_request
def require_admin():
    if not session.get("admin"):
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    return None


@bp.post("/api/panel/luna/translate-story/<story_id>")
def translate_story(story_id: str):
    try:
        result = translate_story_in_repository(
            current_app.extensions["editorial_data"],
            story_id,
            get_luna_client(),
        )
    except LunaProviderError as exc:
        status = 503 if exc.retryable or exc.code == "missing_api_key" else 502
        return jsonify({"ok": False, "error": exc.code, "message": exc.message_fa, "retryable": exc.retryable}), status
    return jsonify(result), (200 if result.get("ok") else 422)
