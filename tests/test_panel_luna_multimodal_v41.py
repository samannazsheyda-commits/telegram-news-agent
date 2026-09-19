from __future__ import annotations

import io
from copy import deepcopy

from panel.app import create_app
from panel.luna_assistant import bp as luna_assistant_bp


class MemoryData:
    def __init__(self):
        self.mapping = {
            "data/panel_audit_log.json": [],
            "data/panel_pending_actions.json": [],
            "data/luna_conversations.json": {},
        }

    def read_json(self, path: str, default):
        return deepcopy(self.mapping.get(path, default)), None

    def write_json(self, path: str, value, sha, message: str):
        self.mapping[path] = deepcopy(value)
        return "memory-sha"


def _client():
    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "x",
            "WTF_CSRF_ENABLED": False,
            "DATA_BACKEND": MemoryData(),
            "MAX_CONTENT_LENGTH": 12 * 1024 * 1024,
        }
    )
    app.register_blueprint(luna_assistant_bp)
    client = app.test_client()
    with client.session_transaction() as session:
        session["admin"] = True
    return client


def test_transcribe_endpoint_requires_audio_file():
    response = _client().post("/api/panel/luna/transcribe", data={})
    payload = response.get_json()

    assert response.status_code == 400
    assert payload["error"] == "missing_audio"


def test_transcribe_endpoint_rejects_unsupported_audio_type_before_provider_call():
    response = _client().post(
        "/api/panel/luna/transcribe",
        data={"audio": (io.BytesIO(b"not-audio"), "note.txt")},
        content_type="multipart/form-data",
    )
    payload = response.get_json()

    assert response.status_code == 415
    assert payload["error"] == "unsupported_audio_type"


def test_chat_endpoint_rejects_unsupported_image_type():
    response = _client().post(
        "/api/panel/luna/chat",
        data={
            "message": "این عکس رو بررسی کن",
            "image": (io.BytesIO(b"fake"), "screen.gif"),
        },
        content_type="multipart/form-data",
    )
    payload = response.get_json()

    assert response.status_code == 415
    assert payload["error"] == "unsupported_image_type"
