import json
from datetime import datetime, timezone

import src.runtime as runtime
from src.sources import NewsItem


def _write_state(path, recent=None):
    path.write_text(
        json.dumps({
            "truth_last_id": "10",
            "news_seen": ["seed"],
            "recent_published_news": recent or [],
            "market_last_sent_at": "2026-09-04T21:00:00+00:00",
            "car_last_sent_date": "2026-09-05",
            "weather_noon_last_sent_date": "2026-09-05",
            "weather_night_last_sent_date": "2026-09-05",
        }),
        encoding="utf-8",
    )


def test_same_trump_quote_from_new_source_is_suppressed_across_runs(tmp_path, monkeypatch):
    state_path = tmp_path / "state.json"
    original = NewsItem(
        "fr24-small-potatoes",
        "France 24",
        "Trump says war with Iran is small potatoes for America",
        "Trump described the conflict with Iran as small potatoes for the United States.",
        "https://news/fr24",
        "Fri, 04 Sep 2026 20:21:00 GMT",
    )
    duplicate = NewsItem(
        "bbc-small-potatoes",
        "BBC News",
        "Trump says Iran war is small potatoes and adds that negotiations may continue",
        "Trump called the war with Iran small potatoes for America and added one sentence about diplomacy.",
        "https://news/bbc",
        "Fri, 04 Sep 2026 21:20:00 GMT",
    )
    _write_state(state_path, [{
        "key": original.key,
        "source": original.source,
        "title": original.title,
        "summary": original.summary,
        "link": original.link,
        "published": original.published,
        "sent_at": "2026-09-04T21:00:00+00:00",
    }])
    monkeypatch.setattr(runtime.agent, "STATE_PATH", str(state_path))
    monkeypatch.setattr(runtime, "_original_fetch_news_items", lambda: [duplicate])
    monkeypatch.setattr(runtime, "fetch_custom_news_items", lambda: [])
    monkeypatch.setattr(runtime, "fetch_priority_news_items", lambda: [])
    monkeypatch.setattr(runtime, "_terminal_manual_keys", lambda: set())

    items = runtime._combined_fetch_news_items()
    assert items == []


def test_distinct_new_trump_development_is_not_suppressed(tmp_path, monkeypatch):
    state_path = tmp_path / "state.json"
    original = NewsItem(
        "fr24-small-potatoes",
        "France 24",
        "Trump says war with Iran is small potatoes for America",
        "Trump described the conflict with Iran as small potatoes for the United States.",
        "https://news/fr24",
        "Fri, 04 Sep 2026 20:21:00 GMT",
    )
    new_story = NewsItem(
        "reuters-new-sanctions",
        "Reuters",
        "Trump announces new sanctions on Iran oil exports",
        "The president announced a new sanctions package targeting Iranian oil exports.",
        "https://news/reuters-new",
        "Fri, 04 Sep 2026 21:30:00 GMT",
    )
    _write_state(state_path, [{
        "key": original.key,
        "source": original.source,
        "title": original.title,
        "summary": original.summary,
        "link": original.link,
        "published": original.published,
        "sent_at": "2026-09-04T21:00:00+00:00",
    }])
    monkeypatch.setattr(runtime.agent, "STATE_PATH", str(state_path))
    monkeypatch.setattr(runtime, "_original_fetch_news_items", lambda: [new_story])
    monkeypatch.setattr(runtime, "fetch_custom_news_items", lambda: [])
    monkeypatch.setattr(runtime, "fetch_priority_news_items", lambda: [])
    monkeypatch.setattr(runtime, "_terminal_manual_keys", lambda: set())

    items = runtime._combined_fetch_news_items()
    assert [item.key for item in items] == ["reuters-new-sanctions"]


def test_successful_publish_is_remembered_for_future_cross_run_dedup(tmp_path, monkeypatch):
    state_path = tmp_path / "state.json"
    _write_state(state_path)
    item = NewsItem(
        "fresh-story",
        "Reuters",
        "Trump says Iran conflict is small potatoes for America",
        "Trump made the remark during an interview.",
        "https://news/reuters",
        "Fri, 04 Sep 2026 21:30:00 GMT",
    )
    monkeypatch.setattr(runtime.agent, "STATE_PATH", str(state_path))
    runtime._sent_news_items.clear()
    runtime._sent_news_items.append(item)

    runtime._flush_recent_published(datetime(2026, 9, 4, 22, 0, tzinfo=timezone.utc))

    remembered = runtime.agent.load_state(state_path).get("recent_published_news") or []
    assert remembered and remembered[0]["key"] == "fresh-story"
    assert remembered[0]["sent_at"] == "2026-09-04T22:00:00+00:00"
    assert runtime._sent_news_items == []
