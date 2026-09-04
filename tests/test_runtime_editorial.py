from __future__ import annotations

from datetime import datetime, timezone

import src.runtime as runtime
from src.editorial_store import LocalEditorialStore
from src.sources import NewsItem


def test_rejected_actionable_item_is_saved_for_manual_review(tmp_path, monkeypatch):
    store = LocalEditorialStore(tmp_path / "queue.json", tmp_path / "history.json")
    monkeypatch.setattr(runtime, "_store", store)
    monkeypatch.setattr(runtime.agent, "translate_to_fa", lambda text: f"FA:{text}")
    monkeypatch.setattr(runtime.agent, "fetch_news_detail", lambda item: "Useful source detail")
    monkeypatch.setattr(runtime, "_original_audit_news", lambda state, item, reason, now: None)
    item = NewsItem(
        "story-key",
        "Reuters",
        "Analysis: Iran policy changes",
        "Source-backed context",
        "https://example.com/story",
        "Fri, 05 Sep 2026 10:00:00 GMT",
    )

    runtime._audit_with_editorial_store({}, item, "article_or_commentary", datetime(2026, 9, 5, 10, 5, tzinfo=timezone.utc))

    records = store.queue()
    assert len(records) == 1
    assert records[0]["news_key"] == "story-key"
    assert records[0]["source"] == "Reuters"
    assert records[0]["source_url"] == "https://example.com/story"
    assert records[0]["rejection_reason"] == "article_or_commentary"
    assert records[0]["persian_title"].startswith("FA:")


def test_stale_or_invalid_item_goes_to_history_not_queue(tmp_path, monkeypatch):
    store = LocalEditorialStore(tmp_path / "queue.json", tmp_path / "history.json")
    monkeypatch.setattr(runtime, "_store", store)
    monkeypatch.setattr(runtime.agent, "translate_to_fa", lambda text: text)
    monkeypatch.setattr(runtime.agent, "fetch_news_detail", lambda item: "")
    monkeypatch.setattr(runtime, "_original_audit_news", lambda state, item, reason, now: None)
    item = NewsItem("old", "Reuters", "Old Iran story", "", "https://example.com/old", "")

    runtime._audit_with_editorial_store({}, item, "invalid_publish_time", datetime.now(timezone.utc))

    assert store.queue() == []
    assert store.history()[0]["status"] == "superseded"


def test_auto_send_moves_matching_pending_item_to_history(tmp_path, monkeypatch):
    store = LocalEditorialStore(tmp_path / "queue.json", tmp_path / "history.json")
    monkeypatch.setattr(runtime, "_store", store)
    item = NewsItem("auto-key", "Reuters", "Iran attack", "detail", "https://example.com/a", "Fri, 05 Sep 2026 10:00:00 GMT")
    record = runtime.ReviewItem.for_news(news_key=item.key, source=item.source, source_url=item.link, original_title=item.title)
    store.upsert_queue(record)
    monkeypatch.setattr(runtime, "_original_format_news", lambda *args, **kwargs: "message")
    monkeypatch.setattr(runtime, "_original_send_telegram", lambda *args, **kwargs: None)

    runtime._format_with_tracking(item, "تیتر", "متن")
    runtime._send_with_tracking("message", "token", "chat")

    assert store.get_pending(record.id) is None
    assert store.history()[0]["status"] == "published_auto"
