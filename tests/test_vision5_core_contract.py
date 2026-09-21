from __future__ import annotations

import pytest


EXPECTED_STATES = (
    "NEW",
    "GOOGLE_TRANSLATING",
    "GOOGLE_TRANSLATED",
    "READY_FOR_REVIEW",
    "LUNA_TRANSLATED",
    "APPROVED",
    "PUBLISHING",
    "PUBLISHED",
    "REJECTED_PERMANENT",
    "PUBLISH_FAILED",
)


def test_v5_schema_contains_final_handoff_tables_and_postgres_guards():
    from bikhabar_v5.schema import POSTGRES_SCHEMA, REQUIRED_TABLES

    assert {
        "stories",
        "sources",
        "story_events",
        "audit_log",
        "reject_blocklist",
        "newsroom_rules",
        "luna_conversations",
        "publish_attempts",
        "collector_runs",
        "service_health",
        "users",
        "sessions",
    }.issubset(REQUIRED_TABLES)

    sql = POSTGRES_SCHEMA.lower()
    for table in REQUIRED_TABLES:
        assert f"create table if not exists {table}" in sql
    assert "published_at_source" in sql
    assert "prevent_source_timestamp_change" in sql
    assert "unique" in sql and "fingerprint" in sql


def test_v5_state_machine_uses_only_handoff_states_and_terminal_states_are_terminal():
    from bikhabar_v5.states import CANONICAL_STATES, InvalidStateTransition, transition_allowed

    assert CANONICAL_STATES == EXPECTED_STATES
    assert transition_allowed("NEW", "GOOGLE_TRANSLATING") is True
    assert transition_allowed("GOOGLE_TRANSLATING", "GOOGLE_TRANSLATED") is True
    assert transition_allowed("GOOGLE_TRANSLATED", "READY_FOR_REVIEW") is True
    assert transition_allowed("READY_FOR_REVIEW", "LUNA_TRANSLATED") is True
    assert transition_allowed("READY_FOR_REVIEW", "APPROVED") is True
    assert transition_allowed("APPROVED", "PUBLISHING") is True
    assert transition_allowed("PUBLISHING", "PUBLISHED") is True
    assert transition_allowed("PUBLISHING", "PUBLISH_FAILED") is True
    assert transition_allowed("PUBLISH_FAILED", "PUBLISHING") is True
    assert transition_allowed("READY_FOR_REVIEW", "REJECTED_PERMANENT") is True

    assert transition_allowed("PUBLISHED", "PUBLISHING") is False
    assert transition_allowed("REJECTED_PERMANENT", "READY_FOR_REVIEW") is False
    with pytest.raises(InvalidStateTransition):
        transition_allowed("made_up", "NEW")


def test_v5_redis_queue_names_are_namespaced_and_never_use_legacy_queue_keys():
    from bikhabar_v5.queue import RedisJobQueue

    queue = RedisJobQueue("redis://127.0.0.1:6379/5")
    assert queue.key("translate") == "bikhabar:v5:jobs:translate"
    assert queue.key("publish") == "bikhabar:v5:jobs:publish"
    assert "v2" not in queue.key("translate")
    assert "v3" not in queue.key("translate")
    assert "v4" not in queue.key("translate")
