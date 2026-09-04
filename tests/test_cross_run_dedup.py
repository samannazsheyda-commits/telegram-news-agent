import json
from datetime import datetime, timezone

import src.main as main
from src.sources import NewsItem, TruthPost


def _wire(monkeypatch, state_path, items, sent):
    monkeypatch.setattr(main, "STATE_PATH", str(state_path))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    monkeypatch.setattr(main, "fetch_truth_posts", lambda: [TruthPost("10", "", "old", "https://truth/10")])
    monkeypatch.setattr(main, "fetch_news_items", lambda: items)
    monkeypatch.setattr(main, "fetch_news_detail", lambda item: item.summary)
    monkeypatch.setattr(main, "translate_to_fa", lambda text: text)
    monkeypatch.setattr(main, "send_telegram", lambda text, token, chat: sent.append(text))


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
    state_path.write_text(json.dumps({
        "truth_last_id": "10",
        "news_seen": ["fr24-small-potatoes"],
        "recent_published_news": [{
            "key": original.key,
            "source": original.source,
            "title": original.title,
            "summary": original.summary,
            "link": original.link,
            "published": original.published,
        }],
        "market_last_sent_at": "2026-09-04T21:00:00+00:00",
        "car_last_sent_date": "2026-09-05",
        "weather_noon_last_sent_date": "2026-09-05",
        "weather_night_last_sent_date": "2026-09-05",
    }), encoding="utf-8")
    sent = []
    _wire(monkeypatch, state_path, [duplicate], sent)

    assert main.run(datetime(2026, 9, 4, 22, 0, tzinfo=timezone.utc)) == 0
    assert [x for x in sent if "لینک منبع خبر" in x] == []
    state = main.load_state(state_path)
    assert "bbc-small-potatoes" in state["news_seen"]
    assert any(r["key"] == "bbc-small-potatoes" and r["reason"] == "duplicate_or_redundant" for r in state.get("news_rejections", []))


def test_successful_publish_is_remembered_for_future_cross_run_dedup(tmp_path, monkeypatch):
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps({
        "truth_last_id": "10",
        "news_seen": ["seed"],
        "market_last_sent_at": "2026-09-04T21:00:00+00:00",
        "car_last_sent_date": "2026-09-05",
        "weather_noon_last_sent_date": "2026-09-05",
        "weather_night_last_sent_date": "2026-09-05",
    }), encoding="utf-8")
    item = NewsItem(
        "fresh-story",
        "Reuters",
        "Trump says Iran conflict is small potatoes for America",
        "Trump made the remark during an interview.",
        "https://news/reuters",
        "Fri, 04 Sep 2026 21:30:00 GMT",
    )
    sent = []
    _wire(monkeypatch, state_path, [item], sent)

    assert main.run(datetime(2026, 9, 4, 22, 0, tzinfo=timezone.utc)) == 0
    remembered = main.load_state(state_path).get("recent_published_news") or []
    assert remembered and remembered[0]["key"] == "fresh-story"
