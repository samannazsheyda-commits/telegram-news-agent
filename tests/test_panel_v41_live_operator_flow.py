from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from panel.app import create_app
from panel.live_api import bp as live_api_bp
from panel.luna_publish import publish_story


class MemoryData:
    def __init__(self):
        self.mapping = {
            "data/panel_live_feed.json": [
                {
                    "id": "story-1",
                    "item_id": "story-1",
                    "news_key": "story-1",
                    "source": "ClashReport",
                    "source_url": "https://example.com/story-1",
                    "original_title": "New English headline",
                    "original_summary": "English summary for the new story.",
                    "panel_status": "new",
                }
            ],
            "data/editorial_queue.json": [],
            "data/editorial_history.json": [],
            "state.json": {},
        }

    def read_json(self, path, default):
        return deepcopy(self.mapping.get(path, default)), "sha"

    def write_json(self, path, value, sha, message):
        del sha, message
        self.mapping[path] = deepcopy(value)
        return {"sha": "next"}


def _client(data: MemoryData):
    app = create_app(
        {
            "TESTING": True,
            "WTF_CSRF_ENABLED": False,
            "SECRET_KEY": "test",
            "PANEL_PASSWORD_HASH": "x",
            "DATA_BACKEND": data,
            "LIVE_FEED_TRANSLATOR": lambda text: {
                "New English headline": "تیتر فارسی تازه",
                "English summary for the new story.": "خلاصه فارسی خبر تازه.",
            }.get(text, text),
        }
    )
    app.register_blueprint(live_api_bp)
    client = app.test_client()
    with client.session_transaction() as session:
        session["admin"] = True
    return client


def test_machine_localization_persists_persian_copy_for_dashboard_and_publish():
    data = MemoryData()
    response = _client(data).post("/api/live-feed/localize", json={"ids": ["story-1"]})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["items"][0]["title"] == "تیتر فارسی تازه"
    row = data.mapping["data/panel_live_feed.json"][0]
    assert row["persian_title"] == "تیتر فارسی تازه"
    assert row["persian_body"] == "خلاصه فارسی خبر تازه."


def test_publish_mode_machine_uses_machine_copy_even_when_luna_copy_exists():
    data = MemoryData()
    row = data.mapping["data/panel_live_feed.json"][0]
    row.update(
        {
            "persian_title": "ترجمه ماشینی مورد تأیید",
            "persian_body": "متن ماشینی مورد تأیید.",
            "final_persian_title": "نسخه متفاوت لونا",
            "final_persian_body": "متن متفاوت لونا.",
            "luna_translation_status": "passed",
        }
    )
    captured = {}

    def enqueue(command, **kwargs):
        captured["command"] = command
        captured.update(kwargs)
        return "cmd-machine"

    result = publish_story(data, "story-1", enqueue=enqueue, confirmed=True, copy_mode="machine")

    assert result["ok"] is True
    assert captured["command"] == "v3_publish"
    assert captured["title"] == "ترجمه ماشینی مورد تأیید"
    assert captured["body"] == "متن ماشینی مورد تأیید."


def test_publish_mode_luna_requires_passed_luna_copy_and_uses_it():
    data = MemoryData()
    row = data.mapping["data/panel_live_feed.json"][0]
    row.update(
        {
            "persian_title": "ترجمه ماشینی",
            "persian_body": "متن ماشینی.",
            "final_persian_title": "نسخه لونا",
            "final_persian_body": "متن لونا.",
            "luna_translation_status": "passed",
        }
    )
    captured = {}

    def enqueue(command, **kwargs):
        captured["command"] = command
        captured.update(kwargs)
        return "cmd-luna"

    result = publish_story(data, "story-1", enqueue=enqueue, confirmed=True, copy_mode="luna")

    assert result["ok"] is True
    assert captured["title"] == "نسخه لونا"
    assert captured["body"] == "متن لونا."


def test_v4_dashboard_contract_has_direct_publish_alarm_auto_localize_and_removes_published_card():
    js = Path("panel/static/newsroom-v4-dashboard.js").read_text(encoding="utf-8")
    template = Path("panel/templates/dashboard.html").read_text(encoding="utf-8")

    assert "انتشار مستقیم" in template
    assert "انتشار نسخه Luna" in template or "انتشار نسخه Luna" in js
    assert "publish-machine" in js
    assert "publish-luna" in js
    assert "/api/live-feed/localize" in js
    assert "/api/live-feed" in js
    assert "AudioContext" in js
    assert "card.remove()" in js
