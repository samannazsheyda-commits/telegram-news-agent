from __future__ import annotations

from flask import Blueprint, jsonify, session

from .github_builder import GitHubBuilder
from .luna_usage import summary
from .openai_luna import get_luna_client


bp = Blueprint("luna_usage_api", __name__)


@bp.before_request
def require_admin():
    if not session.get("admin"):
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    return None


@bp.get("/api/panel/luna/usage")
def luna_usage():
    client = get_luna_client()
    builder = GitHubBuilder.from_env()
    return jsonify(
        {
            "ok": True,
            "connected": client.connected,
            "builder_connected": builder.connected,
            "fast_model": client.fast_model,
            "complex_model": client.complex_model,
            "transcribe_model": client.transcribe_model,
            "usage": summary(),
        }
    )
