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
            "source_display": "رویترز",
            "source_url": "https://example.com/n1",
            "panel_status": "new",
            "updated_at": "2026-09-09T00:00:00+00:00",
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


def test_dashboard_has_bounded_v4_feed_without_legacy_sound_bundle(tmp_path):
    client = _client(tmp_path)
    html = client.get("/").get_data(as_text=True)
    assert 'id="v4LiveFeed"' in html
    assert 'data-story-id="n1"' in html
    assert "newsroom-v4-dashboard.js" in html
    assert 'id="soundToggle"' not in html
    assert "live.js" not in html


def test_v4_dashboard_updates_story_actions_without_full_page_reload(tmp_path):
    client = _client(tmp_path)
    js = client.get("/static/newsroom-v4-dashboard.js").get_data(as_text=True)
    assert "/api/panel/luna/preview/" in js
    assert "/api/panel/luna/publish/" in js
    assert "replaceChildren" in js
    assert "window.location.reload" not in js
    assert "DOMParser" not in js
