from __future__ import annotations

from panel.app_v5 import create_app
from src.newsroom_v5_store import NewsroomV5Store


def _seed(store: NewsroomV5Store, story_id: str, when: str, *, state: str = "review", translated: bool = True):
    store.upsert_story({
        "id": story_id,
        "news_key": story_id,
        "source_id": "src",
        "source_name": "منبع تست",
        "source_url": f"https://example.test/{story_id}",
        "source_item_id": story_id,
        "original_title": f"Original {story_id}",
        "original_body": "Original body",
        "published_at_source": when,
        "state": state,
    })
    if translated:
        store.set_translation(
            story_id,
            title_fa=f"تیتر فارسی {story_id}",
            body_fa=f"متن فارسی {story_id}",
            backend="test",
            quality_passed=True,
        )
    store.set_editorial_decision(
        story_id,
        importance="80",
        priority_class="high",
        publish_recommended=False,
        new_fact=True,
        topic="iran",
        reason="خبر مهم",
        confidence=0.9,
        model="test",
    )


def _app(tmp_path):
    store = NewsroomV5Store(tmp_path / "newsroom.db")
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "test",
        "WTF_CSRF_ENABLED": False,
        "NEWSROOM_V5_STORE": store,
        "NEWSROOM_V5_UI_ENABLED": True,
    })
    return app, store


def _login(client):
    with client.session_transaction() as session:
        session["admin"] = True


def test_review_returns_only_persian_ready_review_in_source_time_order(tmp_path):
    app, store = _app(tmp_path)
    _seed(store, "b", "2026-09-20T11:00:00+00:00")
    _seed(store, "a", "2026-09-20T11:00:00+00:00")
    _seed(store, "old", "2026-09-20T10:00:00+00:00")
    _seed(store, "raw", "2026-09-20T12:00:00+00:00", translated=False)
    _seed(store, "published", "2026-09-20T13:00:00+00:00", state="published")
    _seed(store, "rejected", "2026-09-20T14:00:00+00:00", state="rejected")

    client = app.test_client(); _login(client)
    response = client.get("/api/v5/review?limit=2")
    assert response.status_code == 200
    payload = response.get_json()
    assert [item["id"] for item in payload["items"]] == ["b", "a"]
    assert payload["next_cursor"]
    item = payload["items"][0]
    assert item["title_fa"].startswith("تیتر فارسی")
    assert item["published_at_source"] == "2026-09-20T11:00:00+00:00"
    assert item["source_name"] == "منبع تست"
    assert item["actions"]["publish"].endswith("/b/publish")

    next_response = client.get("/api/v5/review", query_string={"limit": 2, "cursor": payload["next_cursor"]})
    assert [item["id"] for item in next_response.get_json()["items"]] == ["old"]


def test_review_has_no_business_cap_and_can_traverse_more_than_100_items(tmp_path):
    app, store = _app(tmp_path)
    for index in range(125):
        _seed(store, f"s-{index:03d}", f"2026-09-20T10:{index // 60:02d}:{index % 60:02d}+00:00")

    client = app.test_client(); _login(client)
    seen = []
    cursor = None
    while True:
        response = client.get("/api/v5/review", query_string={"limit": 25, **({"cursor": cursor} if cursor else {})})
        assert response.status_code == 200
        payload = response.get_json()
        seen.extend(item["id"] for item in payload["items"])
        cursor = payload["next_cursor"]
        if not cursor:
            break
    assert len(seen) == 125
    assert len(set(seen)) == 125


def test_story_reject_is_durable_and_emits_authoritative_state(tmp_path):
    app, store = _app(tmp_path)
    _seed(store, "s1", "2026-09-20T10:00:00+00:00")
    client = app.test_client(); _login(client)

    response = client.post("/api/v5/story/s1/reject", json={"confirmed": True})
    assert response.status_code == 200
    assert response.get_json()["state"] == "rejected"
    assert store.get_story("s1")["state"] == "rejected"
    assert store.is_tombstoned(news_key="s1", source_url="https://example.test/s1")


def test_publish_is_idempotent_and_copy_edit_is_persian_only(tmp_path):
    app, store = _app(tmp_path)
    _seed(store, "s1", "2026-09-20T10:00:00+00:00")
    client = app.test_client(); _login(client)

    bad = client.patch("/api/v5/story/s1/copy", json={"title_fa": "English title", "body_fa": ""})
    assert bad.status_code == 400
    edit = client.patch("/api/v5/story/s1/copy", json={"title_fa": "تیتر نهایی فارسی", "body_fa": "متن نهایی فارسی"})
    assert edit.status_code == 200

    first = client.post("/api/v5/story/s1/publish", headers={"Idempotency-Key": "tap-1"}, json={"confirmed": True})
    second = client.post("/api/v5/story/s1/publish", headers={"Idempotency-Key": "tap-1"}, json={"confirmed": True})
    assert first.status_code == 202
    assert second.status_code == 202
    assert first.get_json()["publication_id"] == second.get_json()["publication_id"]
    assert store.conn.execute("SELECT COUNT(*) FROM publications").fetchone()[0] == 1


def test_mutations_require_confirmation_and_authentication(tmp_path):
    app, store = _app(tmp_path)
    _seed(store, "s1", "2026-09-20T10:00:00+00:00")
    client = app.test_client()
    assert client.get("/api/v5/review").status_code in {302, 401}
    _login(client)
    response = client.post("/api/v5/story/s1/reject", json={})
    assert response.status_code == 400
    assert store.get_story("s1")["state"] == "review"
