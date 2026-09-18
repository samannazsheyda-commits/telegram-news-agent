from panel.app import create_app
from panel.v4 import bp as v4_bp
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
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "test-secret",
        "PANEL_PASSWORD_HASH": "x",
        "DATA_BACKEND": data,
        "LIVE_FEED_TRANSLATOR": lambda x: x,
    })
    app.register_blueprint(v4_bp)
    return app


def _client(tmp_path):
    app = _app(tmp_path)
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["admin"] = True
    return client


def test_dashboard_is_lightweight_and_incoming_page_owns_story_cards(tmp_path):
    client = _client(tmp_path)
    dashboard = client.get("/").get_data(as_text=True)
    incoming = client.get("/incoming").get_data(as_text=True)
    assert 'id="incomingCount"' in dashboard
    assert 'data-news-card="n1"' not in dashboard
    assert 'data-news-card="n1"' in incoming
    assert "خبر تازه" in incoming
    assert "newsroom-v4.js" in dashboard
    assert "live.js" not in dashboard


def test_v4_dashboard_uses_lightweight_snapshot_polling_without_page_reload(tmp_path):
    client = _client(tmp_path)
    html = client.get("/").get_data(as_text=True)
    assert "/api/v4/snapshot" in html
    assert "15000" in html
    assert "location.reload" not in html
    assert "setInterval(refreshLiveFeed, 1000)" not in html
