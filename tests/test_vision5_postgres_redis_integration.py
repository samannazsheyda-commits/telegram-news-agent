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
    assert duplicate["id"] == story_id

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
