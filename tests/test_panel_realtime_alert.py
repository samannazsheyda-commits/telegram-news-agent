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


def test_dashboard_has_realtime_feed_and_sound_toggle(tmp_path):
    client = _client(tmp_path)
    html = client.get("/").get_data(as_text=True)
    assert 'id="liveFeed"' in html
    assert 'id="soundToggle"' in html
    assert 'id="newNewsBadge"' in html
    assert 'data-news-id="n1"' in html
    assert "live.js" in html


def test_live_js_updates_feed_without_page_reload_and_keeps_sound_preference(tmp_path):
    client = _client(tmp_path)
    js = client.get("/static/live.js").get_data(as_text=True)
    assert "setInterval(refreshLiveFeed, 3000)" in js
    assert "AudioContext" in js
    assert "localStorage" in js
    assert "DOMParser" in js
    assert "replaceChildren" in js
    assert "location.reload" not in js
