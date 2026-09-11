from datetime import datetime, timezone
from pathlib import Path

from src.newsroom_models import RawNewsItem
from src.newsroom_runtime_v2 import run_once


NOW = datetime.fromisoformat("2026-09-11T10:00:00+00:00")


class Publisher:
    def __init__(self):
        self.items = []

    def __call__(self, item):
        self.items.append(item)
        return {"ok": True, "message_id": 1234}


def _missile():
    return RawNewsItem(
        source="Reuters",
        source_url="https://example.com/missile-ai-required",
        source_item_id="missile-ai-required",
        published_at="2026-09-11T09:58:00+00:00",
        fetched_at="2026-09-11T09:59:00+00:00",
        title="Iran launched ballistic missiles toward Israel",
        summary="",
        source_priority="normal",
    )


def test_required_ai_mode_without_token_fails_closed_before_publisher(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_NEWSROOM_MODE", "required")
    monkeypatch.delenv("HF_TOKEN", raising=False)
    publisher = Publisher()
    result = run_once(
        shadow=False,
        fetchers=[lambda: [_missile()]],
        publisher=publisher,
        data_dir=tmp_path,
        now=NOW,
        settings={"hourly_news_limit": 20},
    )
    assert publisher.items == []
    assert result["review_items"] == 1


def test_agent_env_example_documents_ai_newsroom_configuration():
    text = Path("deploy/agent.env.example").read_text(encoding="utf-8")
    assert "AI_NEWSROOM_MODE=" in text
    assert "HF_TOKEN=" in text
    assert "HF_EMBEDDING_MODEL=BAAI/bge-m3" in text
    assert "HF_EDITORIAL_MODEL=Qwen/Qwen3-4B-Instruct-2507:fastest" in text
    assert "HF_MADLAD_ENDPOINT=" in text
    assert "AI_EVENT_MEMORY_HOURS=72" in text
    assert "AI_DUPLICATE_THRESHOLD=0.87" in text
    assert "AI_IMPORTANCE_THRESHOLD=70" in text
