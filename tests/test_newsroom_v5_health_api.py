from __future__ import annotations

from panel.app_v5 import create_app
from src.newsroom_v5_db import SCHEMA_VERSION
from src.newsroom_v5_pipeline import NewsroomV5Pipeline
from src.newsroom_v5_publish import prepare_publication
from src.newsroom_v5_store import NewsroomV5Store


def _app(tmp_path):
    store = NewsroomV5Store(tmp_path / "newsroom.db")
    app = create_app({
        "TESTING": True, "SECRET_KEY": "test", "WTF_CSRF_ENABLED": False,
        "NEWSROOM_V5_STORE": store, "NEWSROOM_V5_UI_ENABLED": True,
    })
    client = app.test_client()
    with client.session_transaction() as session:
        session["admin"] = True
    return app, store, client


def test_health_requires_login(tmp_path):
    app, _store, _client = _app(tmp_path)
    assert app.test_client().get("/api/v5/health").status_code in {302, 401}


def test_health_reports_backlog_outbox_and_reconciliation_without_story_text(tmp_path):
    _app_, store, client = _app(tmp_path)
    NewsroomV5Pipeline(store, lightweight_translator=lambda _t: "").ingest({
        "id": "raw1", "source_item_id": "raw1", "source_id": "reuters",
        "source_url": "https://example.test/raw1", "original_title": "Secret English headline",
        "published_at_source": "2026-09-20T10:00:00+00:00",
    })
    store.upsert_story({"id": "p1", "news_key": "p1", "source_id": "reuters", "source_url": "https://example.test/p1",
                        "original_title": "x", "published_at_source": "2026-09-20T10:00:00+00:00", "state": "review"})
    store.set_translation("p1", title_fa="تیتر", body_fa="", backend="t", quality_passed=True)
    publication = prepare_publication(store, "p1", idempotency_key="k")
    store.update_publication(publication["id"], status="reconcile")

    data = client.get("/api/v5/health").get_json()
    assert data["schema_version"] == SCHEMA_VERSION
    assert data["stories"]["awaiting_translation"] == 1
    assert data["jobs"]["translate_story"]["pending"] == 1
    assert data["jobs"]["translate_story"]["oldest_pending_age_seconds"] is not None
    assert data["publications"]["reconcile"] == 1
    assert data["attention_required"] is True
    assert data["auto_publish_enabled"] is False
    assert "Secret English headline" not in client.get("/api/v5/health").get_data(as_text=True)
