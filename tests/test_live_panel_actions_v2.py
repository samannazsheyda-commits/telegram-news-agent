from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from panel.app import create_app
from panel.command_center import bp as command_center_bp
from panel.live_api import bp as live_api_bp
from src.hormuz import HormuzTrafficReport


class FakeData:
    def __init__(self):
        now = datetime.now(timezone.utc)
        self.files = {
            "data/newsroom_settings.json": {
                "auto_publish": True,
                "emergency_lock": False,
                "freshness_hours": 3,
                "quiet_mode": False,
                "quiet_start": "00:00",
                "quiet_end": "07:00",
            },
            "data/editorial_queue.json": [],
            "data/editorial_history.json": [],
            "data/panel_live_feed.json": [
                {
                    "item_id": "fresh",
                    "news_key": "fresh-key",
                    "source": "Reuters",
                    "source_url": "https://example.com/fresh",
                    "title": "Fresh headline",
                    "summary": "Fresh body",
                    "published_at_source": (now - timedelta(minutes=5)).isoformat(),
                    "discovered_at": now.isoformat(),
                    "updated_at": now.isoformat(),
                    "panel_status": "new",
                },
                {
                    "item_id": "old",
                    "news_key": "old-key",
                    "source": "Reuters",
                    "source_url": "https://example.com/old",
                    "title": "Old headline",
                    "summary": "Old body",
                    "published_at_source": (now - timedelta(hours=6)).isoformat(),
                    "discovered_at": (now - timedelta(hours=6)).isoformat(),
                    "updated_at": now.isoformat(),
                    "panel_status": "new",
                },
            ],
            "state.json": {},
        }
        self.commands = []

    def read_json(self, path, default):
        return self.files.get(path, default), "sha"

    def write_json(self, path, value, sha, message):
        del sha, message
        self.files[path] = value
        if path.startswith("panel_commands/"):
            self.commands.append(value)
        return {"sha": "next"}

    def mark_news_seen(self, key):
        state = dict(self.files.get("state.json", {}))
        seen = list(state.get("news_seen") or [])
        if key not in seen:
            seen.insert(0, key)
        state["news_seen"] = seen
        self.files["state.json"] = state


def _app(data: FakeData):
    app = create_app({
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
        "SECRET_KEY": "test",
        "PANEL_PASSWORD_HASH": "x",
        "DATA_BACKEND": data,
        "LIVE_FEED_TRANSLATOR": lambda text: {
            "Fresh headline": "تیتر تازه",
            "Fresh body": "متن تازه",
        }.get(text, text),
    })
    app.register_blueprint(command_center_bp)
    app.register_blueprint(live_api_bp)
    return app


def _client(data: FakeData):
    client = _app(data).test_client()
    with client.session_transaction() as sess:
        sess["admin"] = True
    return client


def _fake_literal_translation(text: str) -> str:
    return {
        "Fresh headline": "تیتر تازه",
        "Fresh body": "متن تازه",
    }.get(text, text)


def test_live_feed_hides_stale_source_items_even_if_updated_recently():
    data = FakeData()
    payload = _client(data).get("/api/live-feed").get_json()
    ids = [row["id"] for row in payload["items"]]
    assert "fresh" in ids
    assert "old" not in ids


def test_localization_is_preview_only_and_never_persisted_as_final_copy(monkeypatch):
    monkeypatch.setattr("panel.live_api._translate_persian", _fake_literal_translation)
    data = FakeData()
    response = _client(data).post("/api/live-feed/localize", json={"ids": ["fresh"]})
    assert response.status_code == 200
    item = response.get_json()["items"][0]
    assert item["title"] == "تیتر تازه"
    assert item["body"] == "متن تازه"
    assert item["translation_mode"] == "machine"
    assert item["final_message"] == ""

    row = next(row for row in data.files["data/panel_live_feed.json"] if row["item_id"] == "fresh")
    assert "persian_title" not in row
    assert "persian_body" not in row
    assert "final_message" not in row


def test_delete_live_item_is_immediate_not_dependent_on_agent_cycle():
    data = FakeData()
    response = _client(data).post("/api/command-center/clear", json={"scope": "live", "ids": ["fresh"]})
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "succeeded"
    assert all(row["item_id"] != "fresh" for row in data.files["data/panel_live_feed.json"])
    assert data.commands == []


def test_reject_live_item_is_immediate_and_recorded():
    data = FakeData()
    response = _client(data).post("/api/command-center/live/fresh/reject")
    assert response.status_code == 200
    assert response.get_json()["status"] == "rejected"
    assert all(row["item_id"] != "fresh" for row in data.files["data/panel_live_feed.json"])
    rejected = next(row for row in data.files["data/editorial_history.json"] if row["id"] == "fresh")
    assert rejected["status"] == "rejected_manual"
    assert "fresh-key" in data.files["state.json"]["news_seen"]


def test_preview_localization_does_not_authorize_legacy_direct_publish(monkeypatch):
    monkeypatch.setattr("panel.live_api._translate_persian", _fake_literal_translation)
    data = FakeData()
    client = _client(data)
    localized = client.post("/api/live-feed/localize", json={"ids": ["fresh"]})
    assert localized.status_code == 200
    response = client.post("/api/command-center/live/fresh/publish")
    assert response.status_code == 409
    assert response.get_json()["error"] == "final_not_ready"
    assert data.commands == []


def test_hormuz_preview_still_renders_when_precise_count_is_unavailable(monkeypatch):
    import src.panel_modules as modules

    report = HormuzTrafficReport(
        report_date=datetime.now(timezone.utc).date(),
        observed_count=None,
        previous_count=None,
        rolling_average=None,
        vessel_details=(),
        notes=("برای این روز آمار دقیق و قابل استناد کشتی‌ها منتشر نشده است.",),
        sources=("Kpler", "Vortexa", "Reuters"),
    )
    monkeypatch.setattr(modules, "fetch_hormuz_traffic_report", lambda *_args, **_kwargs: report)
    preview = modules.build_hormuz_preview()
    assert "آمار دقیق و قابل استناد" in preview["message"]
    assert preview["available_for_publish"] is False


def test_panel_v4_actions_are_visible_in_light_theme():
    css = Path("panel/static/newsroom-v4.css").read_text(encoding="utf-8")
    js = Path("panel/static/newsroom-live.js").read_text(encoding="utf-8")
    assert "--v4-bg:#f4f7fb" in css
    assert "ترجمه ماشینی" in js
    assert "ترجمه و ویراستاری با لونا" in js
    assert "انتشار نسخه لونا" in js
    assert "رد" in js
