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


def test_live_feed_hides_stale_source_items_even_if_updated_recently():
    data = FakeData()
    payload = _client(data).get("/api/live-feed").get_json()
    ids = [row["id"] for row in payload["items"]]
    assert "fresh" in ids
    assert "old" not in ids


def test_localization_is_persisted_with_final_telegram_output():
    data = FakeData()
    response = _client(data).post("/api/live-feed/localize", json={"ids": ["fresh"]})
    assert response.status_code == 200
    row = next(row for row in data.files["data/panel_live_feed.json"] if row["item_id"] == "fresh")
    assert row["persian_title"] == "تیتر تازه"
    assert row["persian_body"] == "متن تازه"
    assert "تیتر تازه" in row["final_message"]
    assert "لینک منبع خبر" in row["final_message"]


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


def test_publish_live_item_queues_exact_persian_version_for_agent():
    data = FakeData()
    client = _client(data)
    client.post("/api/live-feed/localize", json={"ids": ["fresh"]})
    response = client.post("/api/command-center/live/fresh/publish")
    assert response.status_code == 202
    payload = response.get_json()
    assert payload["status"] == "queued"
    assert data.commands[-1]["action"] == "publish"
    assert data.commands[-1]["item_id"] == "fresh"
    assert data.commands[-1]["title"] == "تیتر تازه"
    assert data.commands[-1]["body"] == "متن تازه"
    queued = next(row for row in data.files["data/editorial_queue.json"] if row["id"] == "fresh")
    assert queued["persian_title"] == "تیتر تازه"


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


def test_panel_preview_and_live_actions_are_visible_in_light_theme():
    css = Path("panel/static/light-newsroom.css").read_text(encoding="utf-8")
    js = Path("panel/static/live.js").read_text(encoding="utf-8")
    assert ".module-preview" in css
    assert ".module-preview-body" in css
    assert "background:#fff" in css or "background:var(--panel)" in css
    assert "color:#171a1f" in css or "color:var(--text)" in css
    assert "خروجی نهایی تلگرام" in js
    assert "انتشار" in js
    assert "رد" in js
    assert "حذف" in js


def test_air_traffic_preview_api_exposes_browser_image_url():
    data = FakeData()
    data.files["data/air_traffic_preview.json"] = {
        "message": "وضعیت ترافیک هوایی خاورمیانه",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "image_path": "data/air_traffic_preview.png",
        "aircraft_count": 42,
    }
    payload = _client(data).get("/api/command-center/module/air-traffic/preview").get_json()
    assert payload["available"] is True
    assert payload["image_url"] == "/api/command-center/module/air-traffic/preview/image"
