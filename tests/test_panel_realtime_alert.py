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


def test_live_feed_api_returns_latest_items_for_authenticated_user(tmp_path):
    app = _app(tmp_path)
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["admin"] = True
    response = client.get("/api/live")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["items"][0]["id"] == "n1"
    assert payload["items"][0]["display_title"] == "خبر تازه"
    assert "generated_at" in payload


def test_dashboard_has_realtime_feed_and_sound_toggle(tmp_path):
    app = _app(tmp_path)
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["admin"] = True
    html = client.get("/").get_data(as_text=True)
    assert 'id="liveFeed"' in html
    assert 'id="soundToggle"' in html
    assert 'id="newNewsBadge"' in html
    assert "live.js" in html
