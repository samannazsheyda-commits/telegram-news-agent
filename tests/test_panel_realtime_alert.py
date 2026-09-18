from pathlib import Path

from panel.app import create_app
from src.local_json_repository import LocalJsonRepository


def _app(tmp_path):
    data = LocalJsonRepository(tmp_path)
    data.write_json("data/panel_live_feed.json", [
        {
            "id": "n1",
            "title": "خبر تازه",
            "persian_title": "خبر تازه",
            "source": "Reuters",
            "source_url": "https://example.com/n1",
            "panel_status": "new",
            "updated_at": "2026-09-18T12:00:00+00:00",
        }
    ], None, "seed")
    return create_app({
        "TESTING": True,
        "SECRET_KEY": "test-secret",
        "PANEL_PASSWORD_HASH": "x",
        "DATA_BACKEND": data,
        "LIVE_FEED_TRANSLATOR": lambda x: x,
    })


def _client(tmp_path):
    app = _app(tmp_path)
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["admin"] = True
    return client


def test_dashboard_has_realtime_feed_and_real_operator_controls(tmp_path):
    client = _client(tmp_path)
    html = client.get("/").get_data(as_text=True)
    assert 'id="liveFeed"' in html
    assert 'id="refreshFeed"' in html
    assert 'id="publishingToggle"' in html
    assert 'id="dailyLimitInput"' in html
    assert "newsroom-live.js" in html
    assert "newsroom-actions.js" in html


def test_v4_live_js_updates_without_page_reload_and_throttles_hidden_tabs(tmp_path):
    del tmp_path
    js = Path("panel/static/newsroom-live.js").read_text(encoding="utf-8")
    assert "/api/live-feed" in js
    assert "/api/newsroom/v4/status" in js
    assert "document.hidden ? 60000 : 15000" in js
    assert "AbortController" in js
    assert "location.reload" not in js
    assert "machineTranslate(autoIds" in js
