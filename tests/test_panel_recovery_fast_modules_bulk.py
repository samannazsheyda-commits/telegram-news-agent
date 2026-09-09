from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from werkzeug.security import generate_password_hash

from panel.app import create_app
from panel.command_center import MODULES
from panel.live_api import bp as live_api_bp
from src.panel_command_router import _apply_clear, _apply_module


class FakeData:
    def __init__(self):
        self.files = {
            "data/panel_live_feed.json": [
                {
                    "item_id": f"n{i}",
                    "title": f"Iran issued a new operational notice number {i}",
                    "persian_title": f"ایران اطلاعیه عملیاتی شماره {i} را صادر کرد",
                    "source": "Reuters",
                    "source_url": f"https://example.com/{i}",
                    "published_at_source": f"2026-09-09T11:{i % 60:02d}:00+00:00",
                    "discovered_at": f"2026-09-09T11:{i % 60:02d}:02+00:00",
                    "updated_at": f"2026-09-09T11:{i % 60:02d}:03+00:00",
                    "panel_status": "new",
                }
                for i in range(60)
            ],
            "data/newsroom_settings.json": {"auto_publish": True, "emergency_lock": False},
            "data/editorial_queue.json": [],
            "data/editorial_history.json": [],
        }

    def read_json(self, path, default):
        return self.files.get(path, default), "sha"

    def write_json(self, path, value, sha, message):
        self.files[path] = value
        return {"content": {"sha": "next"}}

    def mark_news_seen(self, key):
        return None


def _login(client):
    import re
    page = client.get("/login").get_data(as_text=True)
    token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', page).group(1)
    client.post("/login", data={"password": "pass", "csrf_token": token})


def test_live_feed_api_is_fast_json_and_never_calls_translator():
    data = FakeData()
    calls = []
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "test",
        "PANEL_PASSWORD_HASH": generate_password_hash("pass"),
        "DATA_BACKEND": data,
        "LIVE_FEED_TRANSLATOR": lambda text: calls.append(text) or "ترجمه",
    })
    app.register_blueprint(live_api_bp)
    client = app.test_client()
    _login(client)
    response = client.get("/api/live-feed")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert len(payload["items"]) <= 80
    assert calls == []
    assert payload["items"][0]["title_fa"].startswith("ایران")
    assert payload["items"][0]["original_title"].startswith("Iran")


def test_live_refresh_uses_json_endpoint_not_full_dashboard_html():
    js = Path("panel/static/live.js").read_text(encoding="utf-8")
    assert "/api/live-feed" in js
    assert "fetch(window.location.pathname" not in js
    assert "DOMParser" not in js


def test_tanker_and_market_modules_are_real_and_available():
    assert MODULES["tanker"]["available"] is True
    assert MODULES["tanker"]["action"] == "tanker_now"
    assert MODULES["market"]["available"] is True
    assert MODULES["market"]["action"] == "market_now"


def test_runtime_dispatches_tanker_and_market_modules(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with patch("src.panel_modules.publish_hormuz_now", return_value=True) as tanker:
        result = _apply_module({"action": "tanker_now", "command_id": "t1"})
        assert result["status"] == "succeeded"
        tanker.assert_called_once_with()
    with patch("src.panel_modules.publish_market_now", return_value=True) as market:
        result = _apply_module({"action": "market_now", "command_id": "m1"})
        assert result["status"] == "succeeded"
        market.assert_called_once_with()


def test_bulk_clear_supports_live_feed(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("data").mkdir()
    Path("data/panel_live_feed.json").write_text('[{"item_id":"a"},{"item_id":"b"},{"item_id":"c"}]', encoding="utf-8")
    result = _apply_clear({"command_id": "c1", "scope": "live", "ids": ["a", "c"]})
    assert result["status"] == "succeeded"
    text = Path("data/panel_live_feed.json").read_text(encoding="utf-8")
    assert '"b"' in text
    assert '"a"' not in text


def test_dashboard_has_bulk_live_controls():
    combined = Path("panel/templates/dashboard.html").read_text(encoding="utf-8") + Path("panel/static/live.js").read_text(encoding="utf-8")
    assert 'id="liveSelectAll"' in combined
    assert 'id="liveBulkDelete"' in combined
