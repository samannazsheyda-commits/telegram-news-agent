from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from werkzeug.security import generate_password_hash

from panel.app import create_app
from panel.command_center import bp as command_center_bp
from src.editorial_store import LocalEditorialStore
from src.event_ledger import EventLedger
from src.newsroom_models import RawNewsItem
from src.newsroom_v2 import run_cycle
from src.panel_command_router import _apply_module
from src.panel_live_feed import LiveFeedStore


class FakeData:
    def __init__(self):
        self.files = {
            "data/newsroom_settings.json": {"auto_publish": True, "emergency_lock": False},
            "data/panel_live_feed.json": [
                {
                    "item_id": "live-1",
                    "source": "Reuters",
                    "source_url": "https://example.com/live-1",
                    "title": "Iran launches a missile",
                    "summary": "The missile was launched toward a military target.",
                    "panel_status": "new",
                    "published_at_source": "2026-09-09T21:00:00+00:00",
                    "updated_at": "2026-09-09T21:00:01+00:00",
                }
            ],
            "data/editorial_queue.json": [],
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


def _panel(data: FakeData):
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "test",
        "PANEL_PASSWORD_HASH": generate_password_hash("pass"),
        "DATA_BACKEND": data,
        "LIVE_FEED_TRANSLATOR": lambda text: text,
    })
    app.register_blueprint(command_center_bp)
    return app


def _login(client) -> str:
    page = client.get("/login").get_data(as_text=True)
    token = _csrf(page)
    client.post("/login", data={"password": "pass", "csrf_token": token})
    html = client.get("/").get_data(as_text=True)
    meta = re.search(r'<meta name="csrf-token" content="([^"]+)"', html)
    assert meta
    return meta.group(1)


def test_promote_live_to_review_keeps_the_visible_persian_edit_text():
    data = FakeData()
    client = _panel(data).test_client()
    csrf = _login(client)
    response = client.post(
        "/api/command-center/live/live-1/review",
        json={
            "title_fa": "ایران یک موشک شلیک کرد",
            "body_fa": "این موشک به سوی یک هدف نظامی شلیک شد.",
        },
        headers={"X-CSRFToken": csrf},
    )
    assert response.status_code == 200
    queued = data.files["data/editorial_queue.json"][0]
    assert queued["persian_title"] == "ایران یک موشک شلیک کرد"
    assert queued["persian_body"] == "این موشک به سوی یک هدف نظامی شلیک شد."


def test_emergency_lock_blocks_real_module_publication_but_not_preview(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("data").mkdir()
    Path("data/newsroom_settings.json").write_text(
        '{"auto_publish": false, "emergency_lock": true}', encoding="utf-8"
    )

    with patch("src.panel_modules.publish_market_now", return_value=True) as publish:
        with pytest.raises(RuntimeError, match="publication_paused"):
            _apply_module({"action": "market_now", "command_id": "market-live"})
        publish.assert_not_called()

    with patch("src.panel_modules.build_market_preview", return_value={"message": "پیش‌نمایش بازار"}):
        result = _apply_module({"action": "market_preview", "command_id": "market-preview"})
    assert result["status"] == "succeeded"
    assert "پیش‌نمایش" in result["message"]


def _raw(now: datetime) -> RawNewsItem:
    return RawNewsItem(
        source="Reuters",
        source_url="https://example.com/quiet-test",
        source_item_id="quiet-test",
        published_at=(now.replace(minute=max(0, now.minute - 10))).isoformat(),
        fetched_at=now.isoformat(),
        title="Jordan intercepts Iranian missiles over its airspace",
        summary="Jordan says the missiles were intercepted during the attack.",
        source_priority="normal",
    )


def _stores(tmp_path):
    return (
        EventLedger(tmp_path / "ledger.json"),
        LiveFeedStore(tmp_path / "live.json"),
        LocalEditorialStore(tmp_path / "queue.json", tmp_path / "history.json"),
    )


def test_quiet_mode_cross_midnight_really_suppresses_auto_publish(tmp_path):
    # 22:30 UTC = 02:00 Tehran on the next local day; this is inside 23:00–06:00.
    now = datetime(2026, 9, 9, 22, 30, tzinfo=timezone.utc)
    ledger, live, editorial = _stores(tmp_path)
    summary = run_cycle(
        fetcher=lambda: [_raw(now)],
        ledger=ledger,
        live_feed=live,
        editorial_store=editorial,
        publisher=lambda item: (_ for _ in ()).throw(AssertionError("quiet mode must not publish")),
        settings={
            "auto_publish": True,
            "quiet_mode": True,
            "quiet_start": "23:00",
            "quiet_end": "06:00",
            "freshness_hours": 3,
        },
        now=now,
    )
    assert summary.published == 0
    assert summary.review_items == 1
    assert len(editorial.queue()) == 1
    assert live.records()[0].panel_status == "waiting"
    assert editorial.queue()[0]["rejection_reason"] == "quiet_mode"
