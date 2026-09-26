from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BANNED = (
    "showToolEvents",
    "toolCard(",
    "tool_events",
    "ویس دریافت شد",
    "ویس به متن تبدیل شد",
    "تبدیل ویس ناموفق بود",
)


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_normal_luna_chat_does_not_render_internal_tool_cards():
    for relative in ("panel/static/newsroom-v5-luna.js", "panel/static/luna-assistant.js"):
        source = _read(relative)
        for banned in BANNED:
            assert banned not in source, f"{banned} still in {relative}"


def test_messenger_uses_inline_confirmation_and_message_paths():
    js = _read("panel/static/newsroom-v5-luna.js")
    shell = _read("panel/templates/app_shell.html")
    legacy = _read("panel/templates/luna.html")
    app = _read("panel/static/newsroom-v5-app.js")

    assert "v5-luna-confirm" in js
    assert "تأیید و اجرا" in js
    assert "appendMessage" in js
    assert "/api/panel/luna/operator-chat" in js
    assert "/api/panel/luna/operator-confirm/" in js
    assert "confirmation_required" in js
    assert 'data-luna="messages"' in shell
    assert 'data-luna="composer"' in shell
    assert 'data-luna="story-chip"' in shell
    assert 'data-luna="messages"' in legacy
    assert 'id="v4LunaComposer"' in legacy
    assert "setStoryContext" in app
    assert "v5:luna-story" in app
    assert "window.location.href" not in app


def test_voice_controls_expose_record_stop_cancel_and_file_fallback():
    js = _read("panel/static/newsroom-v5-luna.js")
    shell = _read("panel/templates/app_shell.html")
    legacy = _read("panel/templates/luna.html")
    for name in ("toggleRecording", "stopRecording", "cancelRecording", "useAudioFileFallback"):
        assert name in js
    for html in (shell, legacy):
        assert 'data-luna="mic"' in html
        assert 'data-luna="voice-timer"' in html
        assert 'data-luna="voice-cancel"' in html
        assert 'data-luna="voice-level"' in html
        assert 'data-luna="audio"' in html
    assert "idle" in js and "recording" in js and "transcribing" in js
    assert "transcript-ready" in js
