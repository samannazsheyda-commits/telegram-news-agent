from __future__ import annotations

import re
from pathlib import Path

from werkzeug.security import generate_password_hash

from panel.app import create_app
from panel.command_center import bp as command_center_bp
from panel.live_api import _final_message
from src.final_output import finalize_telegram_message
from src.formatters import format_news
from src.sources import NewsItem


class FakeData:
    def __init__(self):
        self.files = {
            "data/newsroom_settings.json": {"auto_publish": True, "emergency_lock": False},
            "data/panel_live_feed.json": [],
            "data/editorial_queue.json": [],
            "state.json": {
                "last_cycle_at": "2026-09-10T15:00:00+00:00",
                "last_publication_at": "2026-09-10T14:59:58+00:00",
                "telegram_state": "ok",
                "last_sources_ok": 8,
                "last_sources_failed": 2,
                "last_items_fetched": 31,
                "last_panel_commands": 1,
                "last_cycle_rc": 0,
            },
        }

    def read_json(self, path, default):
        return self.files.get(path, default), "sha"

    def write_json(self, path, value, sha, message):
        self.files[path] = value
        return {"content": {"sha": "next"}}

    def mark_news_seen(self, key):
        return None


def _csrf(html: str) -> str:
    match = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert match
    return match.group(1)


def _client():
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "test",
        "PANEL_PASSWORD_HASH": generate_password_hash("pass"),
        "DATA_BACKEND": FakeData(),
        "LIVE_FEED_TRANSLATOR": lambda text: text,
    })
    app.register_blueprint(command_center_bp)
    client = app.test_client()
    page = client.get("/login").get_data(as_text=True)
    client.post("/login", data={"password": "pass", "csrf_token": _csrf(page)})
    return client


def test_status_reports_real_two_second_agent_poll_target():
    payload = _client().get("/api/command-center/status").get_json()
    assert payload["poll_seconds"] == 2


def test_health_api_exposes_real_cycle_counters():
    payload = _client().get("/api/command-center/health").get_json()
    assert payload["sources_ok"] == 8
    assert payload["sources_failed"] == 2
    assert payload["items_fetched"] == 31
    assert payload["panel_commands"] == 1
    assert payload["cycle_rc"] == 0


def test_panel_final_message_runs_the_same_last_mile_guard_as_telegram():
    row = {
        "item_id": "n1",
        "source": "Middle East Spectator / Telegram",
        "source_url": "https://t.me/Middle_East_Spectator/123",
        "title": "BREAKING explosion reported near Tehran @Middle_East_Spectator",
        "summary": "ALERT blast heard in Tehran",
        "published_at_source": "2026-09-10T12:00:00+00:00",
    }
    title_fa = "فوری؛ انفجار در نزدیکی تهران"
    body_fa = "صدای انفجار در تهران گزارش شده است"
    legacy = NewsItem(
        key="n1",
        source=row["source"],
        title=row["title"],
        summary=row["summary"],
        link=row["source_url"],
        published=row["published_at_source"],
    )
    expected = finalize_telegram_message(format_news(legacy, title_fa, body_fa))
    assert _final_message(row, title_fa, body_fa) == expected


def test_dashboard_has_real_health_cycle_counters():
    html = Path("panel/templates/dashboard.html").read_text(encoding="utf-8")
    js = Path("panel/static/live.js").read_text(encoding="utf-8")
    for element_id in ("healthSources", "healthFetched", "healthCommands"):
        assert f'id="{element_id}"' in html
        assert element_id in js
