from types import SimpleNamespace

from src.newsroom_channel_publisher import build_channel_copy_publisher
from src.newsroom_models import RawNewsItem
from src.newsroom_normalize import normalize_item
from src.strict_translation import StrictTelegramNewsroomPublisher
import src.newsroom_runtime_v2 as newsroom_runtime_v2
import src.newsroom_v3.canary as canary_module


SOURCE = "Iran launched two ballistic missiles toward Israel."
GOOD_FA = "ایران دو موشک بالستیک به سمت اسرائیل شلیک کرد."


class FakeLuna:
    available = True

    def __init__(self, config=None):
        self.config = config

    def translate_to_fa(self, source):
        return SimpleNamespace(text=GOOD_FA, backend="1xai", faithful=True)

    def edit_persian(self, source, draft):
        return SimpleNamespace(text=GOOD_FA, faithful=True, natural=True, reason="ok")


class ExplodingSession:
    def get(self, *args, **kwargs):
        raise AssertionError("channel copy must not use free translation backends")

    def post(self, *args, **kwargs):
        raise AssertionError("Telegram must not be called when Luna copy is missing")


def _item(title=SOURCE):
    return normalize_item(
        RawNewsItem(
            source="Reuters",
            source_url="https://example.com/missiles",
            source_item_id="missiles-1",
            published_at="2026-09-26T16:00:00+00:00",
            fetched_at="2026-09-26T16:01:00+00:00",
            title=title,
            summary="",
            source_priority="normal",
        )
    )


def test_channel_publisher_is_luna_required_even_when_env_says_optional(monkeypatch):
    monkeypatch.setenv("AI_NEWSROOM_MODE", "optional")
    monkeypatch.setenv("OPENAI_API_KEY", "1xai-test")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://1xai.ir/v1")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("HF_TOKEN", raising=False)

    publisher = build_channel_copy_publisher()

    assert isinstance(publisher, StrictTelegramNewsroomPublisher)
    assert publisher.ai_mode == "required"
    assert publisher.send_still_photos is False
    assert publisher.ai is not None
    assert publisher.ai.available is True


def test_channel_publisher_uses_luna_copy_and_never_falls_back_to_google(monkeypatch):
    monkeypatch.setenv("AI_NEWSROOM_MODE", "optional")
    monkeypatch.setenv("OPENAI_API_KEY", "1xai-test")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.setattr(
        "src.newsroom_channel_publisher.LocalFirstOneXAINewsAI",
        FakeLuna,
    )

    publisher = build_channel_copy_publisher()
    publisher.session = ExplodingSession()
    publisher.translator = lambda text: (_ for _ in ()).throw(
        AssertionError("free translator must not run for channel copy")
    )

    assert publisher._translate_resilient(SOURCE) == GOOD_FA


def test_channel_publisher_fails_closed_without_free_backends_when_luna_is_down(monkeypatch):
    monkeypatch.setenv("AI_NEWSROOM_MODE", "optional")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "@bikhabaar")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("HF_TOKEN", raising=False)

    publisher = build_channel_copy_publisher()
    publisher.session = ExplodingSession()
    publisher.translator = lambda text: "نباید استفاده شود"

    result = publisher(_item())
    assert result["ok"] is False
    assert result.get("error") == "translation_or_format_failed"


def test_v2_runtime_uses_shared_luna_channel_publisher(monkeypatch, tmp_path):
    captured = {}

    def fake_builder():
        captured["used"] = True
        return lambda item: {"ok": True, "message_id": 9}

    monkeypatch.setattr(newsroom_runtime_v2, "build_channel_copy_publisher", fake_builder)
    newsroom_runtime_v2.run_once(
        shadow=True,
        fetchers=[],
        publisher=None,
        data_dir=tmp_path,
    )
    assert captured["used"] is True


def test_v3_production_publisher_wraps_luna_required_channel_copy(monkeypatch):
    monkeypatch.setenv("AI_NEWSROOM_MODE", "optional")
    monkeypatch.setenv("OPENAI_API_KEY", "1xai-test")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("HF_TOKEN", raising=False)

    publisher = canary_module.build_production_publisher()
    assert publisher.publisher.ai_mode == "required"
