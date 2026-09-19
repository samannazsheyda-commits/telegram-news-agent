from __future__ import annotations

from panel.app_v5 import create_app
from src.newsroom_v5_events import NewsroomEventBroker
from src.newsroom_v5_store import NewsroomV5Store


def _app(tmp_path):
    store = NewsroomV5Store(tmp_path / "newsroom.db")
    broker = NewsroomEventBroker(max_events=20)
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "test",
        "WTF_CSRF_ENABLED": False,
        "NEWSROOM_V5_STORE": store,
        "NEWSROOM_V5_EVENTS": broker,
        "NEWSROOM_V5_UI_ENABLED": True,
    })
    return app, broker


def _login(client):
    with client.session_transaction() as session:
        session["admin"] = True


def test_sse_requires_authentication(tmp_path):
    app, _ = _app(tmp_path)
    response = app.test_client().get("/api/v5/events")
    assert response.status_code in {302, 401}


def test_sse_replays_event_after_last_event_id(tmp_path):
    app, broker = _app(tmp_path)
    first = broker.publish("story_added", {"story_id": "a"})
    broker.publish("story_updated", {"story_id": "a"})
    client = app.test_client(); _login(client)

    response = client.get(
        "/api/v5/events",
        headers={"Last-Event-ID": str(first.id)},
        buffered=False,
    )
    assert response.status_code == 200
    assert response.mimetype == "text/event-stream"
    chunk = next(response.response).decode("utf-8")
    assert "event: story_updated" in chunk
    assert '"story_id":"a"' in chunk
    response.close()


def test_replay_gap_emits_refetch_instruction(tmp_path):
    app, broker = _app(tmp_path)
    broker.max_events = 2
    broker.publish("story_added", {"story_id": "a"})
    broker.publish("story_added", {"story_id": "b"})
    broker.publish("story_added", {"story_id": "c"})
    client = app.test_client(); _login(client)
    response = client.get("/api/v5/events", headers={"Last-Event-ID": "0"}, buffered=False)
    chunk = next(response.response).decode("utf-8")
    assert "event: refetch_required" in chunk
    response.close()
