from __future__ import annotations

import io
from copy import deepcopy

import pytest

from panel.app import create_app
from panel.luna_assistant import bp as luna_assistant_bp
from panel.openai_luna import LunaProviderError


class MemoryData:
    def read_json(self, path: str, default):
        return deepcopy(default), None

    def write_json(self, path: str, value, sha, message: str):
        return "memory-sha"


class FakeClient:
    def __init__(self, text="سلام از ویس", error: LunaProviderError | None = None):
        self.text = text
        self.error = error
        self.calls = []

    def transcribe(self, content: bytes, *, filename: str, mimetype: str) -> dict:
        self.calls.append((bytes(content), filename, mimetype))
        if self.error is not None:
            raise self.error
        return {"text": self.text}


def _client(monkeypatch, fake: FakeClient):
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "x",
        "WTF_CSRF_ENABLED": False,
        "DATA_BACKEND": MemoryData(),
        "MAX_CONTENT_LENGTH": 12 * 1024 * 1024,
    })
    app.register_blueprint(luna_assistant_bp)
    monkeypatch.setattr("panel.luna_assistant.get_luna_client", lambda: fake)
    client = app.test_client()
    with client.session_transaction() as session:
        session["admin"] = True
    return client


def _audio(name: str, mime: str, payload: bytes = b"audio-bytes"):
    return {"audio": (io.BytesIO(payload), name, mime)}


@pytest.mark.parametrize(
    ("name", "mime"),
    [
        ("clip.webm", "audio/webm"),
        ("clip.webm", "video/webm"),
        ("clip.mp3", "audio/mpeg"),
        ("clip.mp3", "audio/mp3"),
        ("clip.m4a", "audio/x-m4a"),
        ("clip.mp4", "audio/mp4"),
        ("clip.mp4", "video/mp4"),
        ("clip.wav", "audio/wav"),
        ("clip.wav", "audio/x-wav"),
        ("clip.mpeg", "audio/mpeg"),
        ("clip.mpga", "audio/mpeg"),
    ],
)
def test_transcribe_accepts_supported_audio_formats(monkeypatch, name, mime):
    fake = FakeClient("متن ویس")
    response = _client(monkeypatch, fake).post(
        "/api/panel/luna/transcribe",
        data=_audio(name, mime),
        content_type="multipart/form-data",
    )
    payload = response.get_json()
    assert response.status_code == 200
    assert payload == {"ok": True, "text": "متن ویس"}
    assert fake.calls[0][1] == name
    assert fake.calls[0][2] == mime


def test_transcribe_requires_an_audio_file(monkeypatch):
    response = _client(monkeypatch, FakeClient()).post("/api/panel/luna/transcribe", data={})
    payload = response.get_json()
    assert response.status_code == 400
    assert payload["error"] == "missing_audio"
    assert payload["message"] == "فایل صوتی ارسال نشده است."


def test_transcribe_rejects_empty_audio_before_provider_call(monkeypatch):
    fake = FakeClient()
    response = _client(monkeypatch, fake).post(
        "/api/panel/luna/transcribe",
        data=_audio("clip.webm", "audio/webm", b""),
        content_type="multipart/form-data",
    )
    payload = response.get_json()
    assert response.status_code == 400
    assert payload["error"] == "empty_audio"
    assert fake.calls == []


def test_transcribe_rejects_unsupported_type(monkeypatch):
    fake = FakeClient()
    response = _client(monkeypatch, fake).post(
        "/api/panel/luna/transcribe",
        data=_audio("note.txt", "text/plain", b"hello"),
        content_type="multipart/form-data",
    )
    assert response.status_code == 415
    assert response.get_json()["error"] == "unsupported_audio_type"
    assert fake.calls == []


def test_transcribe_rejects_oversize_audio(monkeypatch):
    fake = FakeClient()
    response = _client(monkeypatch, fake).post(
        "/api/panel/luna/transcribe",
        data=_audio("clip.webm", "audio/webm", b"x" * (10 * 1024 * 1024 + 1)),
        content_type="multipart/form-data",
    )
    assert response.status_code == 413
    assert response.get_json()["error"] == "audio_too_large"
    assert fake.calls == []


def test_transcribe_maps_retryable_provider_errors(monkeypatch):
    fake = FakeClient(error=LunaProviderError("timeout", "تبدیل ویس به متن طول کشید؛ دوباره تلاش کن.", True))
    response = _client(monkeypatch, fake).post(
        "/api/panel/luna/transcribe",
        data=_audio("clip.webm", "audio/webm"),
        content_type="multipart/form-data",
    )
    payload = response.get_json()
    assert response.status_code == 503
    assert payload["ok"] is False
    assert payload["error"] == "timeout"
    assert payload["retryable"] is True
    assert "دوباره" in payload["message"]


def test_transcribe_maps_non_retryable_provider_errors(monkeypatch):
    fake = FakeClient(error=LunaProviderError("invalid_transcription", "متنی از این ویس دریافت نشد.", False))
    response = _client(monkeypatch, fake).post(
        "/api/panel/luna/transcribe",
        data=_audio("clip.wav", "audio/wav"),
        content_type="multipart/form-data",
    )
    payload = response.get_json()
    assert response.status_code == 502
    assert payload["retryable"] is False
    assert payload["message"] == "متنی از این ویس دریافت نشد."
