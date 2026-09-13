from datetime import datetime, timezone

import src.newsroom_runtime_v2 as newsroom_runtime_v2
from src.newsroom_models import RawNewsItem
from src.newsroom_runtime_v2 import run_once


def _fresh():
    return RawNewsItem(
        source="Reuters",
        source_url="https://example.com/fresh",
        source_item_id="fresh-1",
        published_at="2026-09-07T21:00:00+00:00",
        fetched_at="2026-09-07T21:01:00+00:00",
        title="Iran partially reopens airspace after security restrictions",
    )


def test_shadow_run_never_calls_real_publisher(tmp_path):
    calls = []
    result = run_once(
        shadow=True,
        fetchers=[lambda: [_fresh()]],
        publisher=lambda item: calls.append(item) or {"ok": True, "message_id": 1},
        data_dir=tmp_path,
        now=datetime(2026, 9, 7, 21, 30, tzinfo=timezone.utc),
    )
    assert calls == []
    assert result["telegram_writes"] == 0
    assert result["panel_feed_count"] == 1


def test_production_run_uses_verified_publisher(tmp_path):
    calls = []
    result = run_once(
        shadow=False,
        fetchers=[lambda: [_fresh()]],
        publisher=lambda item: calls.append(item.raw.source_item_id) or {"ok": True, "message_id": 55},
        data_dir=tmp_path,
        now=datetime(2026, 9, 7, 21, 30, tzinfo=timezone.utc),
    )
    assert calls == ["fresh-1"]
    assert result["published"] == 1
    assert result["telegram_writes"] == 1


def test_runtime_prefers_groq_when_both_provider_keys_exist(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_NEWSROOM_MODE", "required")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    monkeypatch.setenv("HF_TOKEN", "hf_exhausted")
    result = run_once(
        shadow=True,
        fetchers=[],
        publisher=lambda item: {"ok": True, "message_id": 1},
        data_dir=tmp_path,
        now=datetime(2026, 9, 7, 21, 30, tzinfo=timezone.utc),
    )
    assert result["ai_available"] is True
    assert result["ai_provider"] == "groq"
    assert result["ai_newsroom_mode"] == "required"


def test_runtime_prefers_openrouter_over_groq_and_hf(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_NEWSROOM_MODE", "required")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-test")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_unreachable")
    monkeypatch.setenv("HF_TOKEN", "hf_exhausted")
    result = run_once(
        shadow=True,
        fetchers=[],
        publisher=lambda item: {"ok": True, "message_id": 1},
        data_dir=tmp_path,
        now=datetime(2026, 9, 7, 21, 30, tzinfo=timezone.utc),
    )
    assert result["ai_available"] is True
    assert result["ai_provider"] == "openrouter"
    assert result["ai_newsroom_mode"] == "required"


def test_runtime_enables_offline_translation_fallback_by_default(tmp_path, monkeypatch):
    captured = {}

    class CapturingPublisher:
        def __init__(self, *args, **kwargs):
            captured.update(kwargs)

        def __call__(self, item):
            return {"ok": True, "message_id": 1}

    monkeypatch.setattr(newsroom_runtime_v2, "StrictTelegramNewsroomPublisher", CapturingPublisher)
    monkeypatch.delenv("OFFLINE_TRANSLATION_ENABLED", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("HF_TOKEN", raising=False)

    run_once(
        shadow=True,
        fetchers=[],
        publisher=None,
        data_dir=tmp_path,
        now=datetime(2026, 9, 7, 21, 30, tzinfo=timezone.utc),
    )

    assert captured["offline_translation_enabled"] is True
