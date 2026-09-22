from __future__ import annotations

import os
import uuid

import pytest


pytestmark = pytest.mark.skipif(
    os.environ.get("BIKHABAR_V5_INTEGRATION") != "1",
    reason="Vision 5 integration services are only enabled in the dedicated CI job",
)


def _db_url() -> str:
    return os.environ["BIKHABAR_V5_DATABASE_URL"]


def _redis_url() -> str:
    return os.environ["BIKHABAR_V5_REDIS_URL"]


def test_postgres_core_ingest_transition_audit_and_permanent_reject():
    from bikhabar_v5.postgres import PostgresCore

    core = PostgresCore(_db_url())
    core.initialize()
    core.reset_for_test()

    source_id = str(uuid.uuid4())
    core.upsert_source(
        {
            "id": source_id,
            "kind": "rss",
            "identity": "https://example.com/feed.xml",
            "display_name": "Example",
        }
    )

    story_id = str(uuid.uuid4())
    story, inserted = core.ingest_story(
        {
            "id": story_id,
            "source_id": source_id,
            "source": "Example",
            "source_url": "https://example.com/news/1",
            "original_title": "Original",
            "original_text": "Body",
            "published_at_source": "2026-09-21T18:00:00+00:00",
            "fingerprint": "fp-real-1",
        }
    )
    assert inserted is True
    assert story["status"] == "NEW"

    duplicate, inserted_again = core.ingest_story(
        {
            "id": str(uuid.uuid4()),
            "source_id": source_id,
            "source": "Example",
            "source_url": "https://example.com/news/1",
            "original_title": "Duplicate",
            "fingerprint": "fp-real-1",
            "published_at_source": "2026-09-21T18:00:00+00:00",
        }
    )
    assert inserted_again is False
    assert duplicate["id"] == uuid.UUID(story_id)

    transitioned = core.transition_story(story_id, "GOOGLE_TRANSLATING", actor="collector")
    assert transitioned["status"] == "GOOGLE_TRANSLATING"
    events = core.story_events(story_id)
    assert events[-1]["from_status"] == "NEW"
    assert events[-1]["to_status"] == "GOOGLE_TRANSLATING"

    rejected = core.reject_story(story_id, reason="operator_reject", actor="human")
    assert rejected["status"] == "REJECTED_PERMANENT"
    assert core.is_blocked(fingerprint="fp-real-1", source_url="https://example.com/news/1") is True

    blocked_story, blocked_inserted = core.ingest_story(
        {
            "id": str(uuid.uuid4()),
            "source_id": source_id,
            "source": "Example",
            "source_url": "https://example.com/news/1",
            "original_title": "Must not return",
            "fingerprint": "fp-real-1",
            "published_at_source": "2026-09-21T18:00:00+00:00",
        }
    )
    assert blocked_inserted is False
    assert blocked_story["status"] == "REJECTED_PERMANENT"
    core.close()


def test_postgres_source_timestamp_is_immutable_at_database_level():
    import psycopg
    from bikhabar_v5.postgres import PostgresCore

    core = PostgresCore(_db_url())
    core.initialize()
    core.reset_for_test()
    source_id = str(uuid.uuid4())
    story_id = str(uuid.uuid4())
    core.upsert_source({"id": source_id, "kind": "manual", "identity": "manual:test", "display_name": "Manual"})
    core.ingest_story(
        {
            "id": story_id,
            "source_id": source_id,
            "source": "Manual",
            "source_url": "https://example.com/immutable",
            "original_title": "Immutable timestamp",
            "fingerprint": "fp-immutable",
            "published_at_source": "2026-09-21T18:00:00+00:00",
        }
    )

    with pytest.raises(psycopg.errors.RaiseException):
        with core.connection.transaction():
            core.connection.execute(
                "UPDATE stories SET published_at_source=%s WHERE id=%s",
                ("2026-09-21T19:00:00+00:00", story_id),
            )
    core.close()


def test_postgres_panel_query_review_and_history_contract():
    from bikhabar_v5.postgres import PostgresCore

    core = PostgresCore(_db_url())
    core.initialize()
    core.reset_for_test()
    source_id = str(uuid.uuid4())
    story_id = str(uuid.uuid4())
    core.upsert_source(
        {"id": source_id, "kind": "rss", "identity": "panel:test", "display_name": "Panel Source"}
    )
    core.ingest_story(
        {
            "id": story_id,
            "source_id": source_id,
            "source": "Panel Source",
            "source_url": "https://example.com/panel-story",
            "original_title": "Panel story",
            "original_text": "Panel body",
            "published_at_source": "2026-09-22T09:00:00+00:00",
        }
    )
    core.transition_story(story_id, "GOOGLE_TRANSLATING", actor="translation-worker")
    core.record_translation(
        story_id,
        provider="google",
        title="تیتر فارسی پنل",
        body="متن فارسی پنل",
        actor="translation-worker",
    )
    core.transition_story(story_id, "READY_FOR_REVIEW", actor="translation-worker")

    result = core.list_stories(
        statuses=("READY_FOR_REVIEW",), query="فارسی", source="Panel", page=1, page_size=25
    )
    assert result["total"] == 1
    assert result["items"][0]["id"] == uuid.UUID(story_id)
    assert core.get_story(story_id)["published_at_source"].isoformat().startswith("2026-09-22T09:00:00")

    approved = core.save_review(
        story_id,
        title="تیتر نهایی پنل",
        body="متن نهایی پنل",
        copy_mode="edited",
        actor="editor",
        approve=True,
    )
    assert approved["status"] == "APPROVED"
    assert approved["final_title"] == "تیتر نهایی پنل"
    publishing, attempt = core.prepare_publish(
        story_id,
        idempotency_key=f"telegram:{story_id}",
        copy_mode="final",
        payload={"text": "تیتر نهایی پنل\n\nمتن نهایی پنل"},
        actor="publisher",
        allow_retry=False,
    )
    assert publishing["status"] == "PUBLISHING"
    assert attempt["attempt_count"] == 1
    published = core.complete_publish(
        story_id,
        attempt["id"],
        telegram_message_id=12345,
        actor="publisher",
    )
    assert published["status"] == "PUBLISHED"
    history = core.list_stories(statuses=("PUBLISHED",), query="", source="", page=1, page_size=25)
    assert history["items"][0]["telegram_message_id"] == 12345
    core.close()


def test_redis_stream_queue_round_trip_and_ack():
    from bikhabar_v5.queue import RedisJobQueue

    queue = RedisJobQueue(_redis_url())
    kind = f"integration-{uuid.uuid4().hex[:8]}"
    group = "vision5-tests"
    job_id = queue.enqueue(kind, {"story_id": "s1", "purpose": "translate"})
    rows = queue.read(kind, group=group, consumer="ci", count=1, block_ms=1500)
    assert len(rows) == 1
    assert rows[0]["job_id"] == job_id
    assert rows[0]["payload"]["story_id"] == "s1"
    assert queue.ack(kind, group=group, message_id=rows[0]["message_id"]) == 1


def test_postgres_luna_memory_rules_and_operator_audit_contract():
    from bikhabar_v5.postgres import PostgresCore

    core = PostgresCore(_db_url())
    core.initialize()
    core.reset_for_test()
    core.upsert_newsroom_rule("tone", {"value": "رسمی"}, actor="editor")
    assert core.list_newsroom_rules()[0]["rule_key"] == "tone"

    core.save_luna_conversation(
        "editor",
        messages=[{"role": "user", "content": "سلام"}],
        context={"story_id": None},
    )
    conversation = core.get_luna_conversation("editor")
    assert conversation["messages"][0]["content"] == "سلام"
    core.record_operator_audit(
        actor="editor",
        action="luna_chat",
        entity_type="conversation",
        entity_id="editor",
        status="succeeded",
        detail={"tokens": 10},
    )
    audit = core.connection.execute(
        "SELECT action FROM audit_log WHERE action = 'luna_chat'"
    ).fetchone()
    assert audit["action"] == "luna_chat"
    core.close()


def test_postgres_sources_settings_health_and_dashboard_contract():
    from bikhabar_v5.postgres import PostgresCore

    core = PostgresCore(_db_url())
    core.initialize()
    core.reset_for_test()
    source = core.upsert_source(
        {"kind": "rss", "identity": "https://example.com/feed", "display_name": "Example"}
    )
    assert core.list_sources()[0]["display_name"] == "Example"
    disabled = core.set_source_enabled(str(source["id"]), enabled=False, actor="editor")
    assert disabled["enabled"] is False

    core.upsert_newsroom_rule(
        "runtime_settings",
        {"freshness_hours": 6, "daily_limit": 50, "auto_publish": False},
        actor="editor",
    )
    assert core.get_newsroom_rule("runtime_settings")["rule_json"]["daily_limit"] == 50
    core.update_service_health("collector", status="healthy", detail={"lag_seconds": 2})
    assert core.get_service_health("collector")["status"] == "healthy"
    assert core.list_service_health()[0]["service_name"] == "collector"
    assert core.dashboard_metrics()["sources_total"] == 1
    assert core.list_audit(limit=10)
    legacy_id = str(uuid.uuid4())
    imported = core.import_legacy_story(
        {
            "id": legacy_id,
            "source": "Legacy",
            "source_url": "https://example.com/legacy-published",
            "original_title": "Legacy title",
            "final_title": "تیتر قدیمی",
            "final_body": "متن قدیمی",
            "status": "PUBLISHED",
            "telegram_message_id": 555,
            "media_json": {},
        },
        actor="migration",
    )
    assert imported["status"] == "PUBLISHED"
    assert core.import_legacy_story(
        {"id": legacy_id, "source": "Legacy", "status": "PUBLISHED", "media_json": {}},
        actor="migration",
    )["id"] == uuid.UUID(legacy_id)
    core.close()
