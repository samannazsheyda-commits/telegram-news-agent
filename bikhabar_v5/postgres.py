from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .schema import POSTGRES_SCHEMA
from .states import require_transition


class StoryNotFoundError(LookupError):
    """Raised when a Vision 5 story id does not exist."""


class PostgresCore:
    """Transactional PostgreSQL store for the standalone Vision 5 runtime."""

    def __init__(self, database_url: str, *, connection: Connection | None = None) -> None:
        self.database_url = str(database_url or "").strip()
        if not self.database_url and connection is None:
            raise ValueError("database_url is required")
        self.connection = connection or Connection.connect(
            self.database_url,
            autocommit=True,
            row_factory=dict_row,
        )

    def initialize(self) -> None:
        with self.connection.transaction():
            self.connection.execute(POSTGRES_SCHEMA)

    def close(self) -> None:
        self.connection.close()

    def reset_for_test(self) -> None:
        """Clear isolated Vision 5 tables for integration-test setup."""
        with self.connection.transaction():
            self.connection.execute(
                """
                TRUNCATE TABLE
                    sessions, users, service_health, collector_runs,
                    publish_attempts, luna_conversations, newsroom_rules,
                    reject_blocklist, audit_log, story_events, stories, sources
                RESTART IDENTITY CASCADE
                """
            )

    def upsert_source(self, source: Mapping[str, Any]) -> dict[str, Any]:
        source_id = str(source.get("id") or uuid.uuid4())
        kind = str(source.get("kind") or "").strip().lower()
        identity = str(source.get("identity") or "").strip()
        display_name = str(source.get("display_name") or "").strip()
        if not kind or not identity or not display_name:
            raise ValueError("source kind, identity and display_name are required")

        with self.connection.transaction():
            row = self.connection.execute(
                """
                INSERT INTO sources (
                    id, kind, identity, display_name, enabled, priority,
                    category, reliability_score
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (kind, identity) DO UPDATE SET
                    display_name = EXCLUDED.display_name,
                    enabled = EXCLUDED.enabled,
                    priority = EXCLUDED.priority,
                    category = EXCLUDED.category,
                    reliability_score = EXCLUDED.reliability_score,
                    updated_at = now()
                RETURNING *
                """,
                (
                    source_id,
                    kind,
                    identity,
                    display_name,
                    bool(source.get("enabled", True)),
                    int(source.get("priority") or 0),
                    source.get("category"),
                    source.get("reliability_score"),
                ),
            ).fetchone()
        return dict(row)

    def ingest_story(self, story: Mapping[str, Any]) -> tuple[dict[str, Any], bool]:
        story_id = str(story.get("id") or uuid.uuid4())
        source_id = str(story.get("source_id") or "").strip() or None
        source = str(story.get("source") or "").strip()
        fingerprint = str(story.get("fingerprint") or "").strip() or None
        source_url = str(story.get("source_url") or "").strip() or None
        if not source:
            raise ValueError("story source is required")

        with self.connection.transaction():
            blocked = self._blocked_story(fingerprint=fingerprint, source_url=source_url)
            if blocked is not None:
                return blocked, False

            inserted = self.connection.execute(
                """
                INSERT INTO stories (
                    id, source_id, source, source_url, original_title,
                    original_text, media_json, published_at_source, fingerprint
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
                RETURNING *
                """,
                (
                    story_id,
                    source_id,
                    source,
                    source_url,
                    str(story.get("original_title") or ""),
                    str(story.get("original_text") or ""),
                    Jsonb(dict(story.get("media_json") or {})),
                    story.get("published_at_source"),
                    fingerprint,
                ),
            ).fetchone()

            if inserted is None:
                duplicate = self._duplicate_story(fingerprint=fingerprint, source_url=source_url)
                if duplicate is None:
                    raise RuntimeError("story insert conflicted without a matching canonical story")
                return duplicate, False

            self._record_event(
                story_id=story_id,
                event_type="INGESTED",
                from_status=None,
                to_status="NEW",
                actor="collector",
                detail={"source_id": source_id, "source_url": source_url},
            )
            self._record_audit(
                actor="collector",
                action="story_ingested",
                entity_type="story",
                entity_id=story_id,
                status="succeeded",
                detail={"source_id": source_id},
            )
            return dict(inserted), True

    def transition_story(
        self,
        story_id: str,
        target: str,
        *,
        actor: str,
        detail: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self.connection.transaction():
            current = self._story_for_update(story_id)
            source, destination = require_transition(str(current["status"]), target)
            updated = self.connection.execute(
                """
                UPDATE stories
                SET status = %s, decision_actor = %s, updated_at = now()
                WHERE id = %s
                RETURNING *
                """,
                (destination, actor, story_id),
            ).fetchone()
            self._record_event(
                story_id=story_id,
                event_type="STATE_TRANSITION",
                from_status=source,
                to_status=destination,
                actor=actor,
                detail=detail,
            )
            self._record_audit(
                actor=actor,
                action="story_transitioned",
                entity_type="story",
                entity_id=story_id,
                status="succeeded",
                detail={"from_status": source, "to_status": destination, **dict(detail or {})},
            )
            return dict(updated)

    def reject_story(self, story_id: str, *, reason: str, actor: str) -> dict[str, Any]:
        rejection_reason = str(reason or "").strip()
        if not rejection_reason:
            raise ValueError("reject reason is required")

        with self.connection.transaction():
            current = self._story_for_update(story_id)
            source, destination = require_transition(str(current["status"]), "REJECTED_PERMANENT")
            updated = self.connection.execute(
                """
                UPDATE stories
                SET status = %s, reject_reason = %s, decision_actor = %s, updated_at = now()
                WHERE id = %s
                RETURNING *
                """,
                (destination, rejection_reason, actor, story_id),
            ).fetchone()
            self.connection.execute(
                """
                INSERT INTO reject_blocklist (story_id, fingerprint, source_url, reason)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT DO NOTHING
                """,
                (story_id, current.get("fingerprint"), current.get("source_url"), rejection_reason),
            )
            self._record_event(
                story_id=story_id,
                event_type="REJECTED_PERMANENT",
                from_status=source,
                to_status=destination,
                actor=actor,
                detail={"reason": rejection_reason},
            )
            self._record_audit(
                actor=actor,
                action="story_rejected_permanent",
                entity_type="story",
                entity_id=story_id,
                status="succeeded",
                detail={"reason": rejection_reason},
            )
            return dict(updated)

    def is_blocked(self, *, fingerprint: str | None = None, source_url: str | None = None) -> bool:
        return self._blocked_story(
            fingerprint=str(fingerprint or "").strip() or None,
            source_url=str(source_url or "").strip() or None,
        ) is not None

    def story_events(self, story_id: str) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """
            SELECT * FROM story_events
            WHERE story_id = %s
            ORDER BY id ASC
            """,
            (story_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def _story_for_update(self, story_id: str) -> dict[str, Any]:
        row = self.connection.execute(
            "SELECT * FROM stories WHERE id = %s FOR UPDATE",
            (story_id,),
        ).fetchone()
        if row is None:
            raise StoryNotFoundError(f"Vision 5 story not found: {story_id}")
        return dict(row)

    def _duplicate_story(
        self,
        *,
        fingerprint: str | None,
        source_url: str | None,
    ) -> dict[str, Any] | None:
        row = self.connection.execute(
            """
            SELECT * FROM stories
            WHERE (%s IS NOT NULL AND fingerprint = %s)
               OR (%s IS NOT NULL AND source_url = %s)
            ORDER BY created_at ASC
            LIMIT 1
            """,
            (fingerprint, fingerprint, source_url, source_url),
        ).fetchone()
        return dict(row) if row is not None else None

    def _blocked_story(
        self,
        *,
        fingerprint: str | None,
        source_url: str | None,
    ) -> dict[str, Any] | None:
        if fingerprint is None and source_url is None:
            return None
        row = self.connection.execute(
            """
            SELECT stories.*
            FROM reject_blocklist
            JOIN stories ON stories.id = reject_blocklist.story_id
            WHERE (%s IS NOT NULL AND reject_blocklist.fingerprint = %s)
               OR (%s IS NOT NULL AND reject_blocklist.source_url = %s)
            ORDER BY reject_blocklist.id ASC
            LIMIT 1
            """,
            (fingerprint, fingerprint, source_url, source_url),
        ).fetchone()
        return dict(row) if row is not None else None

    def _record_event(
        self,
        *,
        story_id: str,
        event_type: str,
        from_status: str | None,
        to_status: str | None,
        actor: str,
        detail: Mapping[str, Any] | None,
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO story_events (
                story_id, event_type, from_status, to_status, actor, detail_json
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (story_id, event_type, from_status, to_status, actor, Jsonb(dict(detail or {}))),
        )

    def _record_audit(
        self,
        *,
        actor: str,
        action: str,
        entity_type: str,
        entity_id: str,
        status: str,
        detail: Mapping[str, Any] | None,
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO audit_log (
                actor, action, entity_type, entity_id, status, detail_json
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (actor, action, entity_type, entity_id, status, Jsonb(dict(detail or {}))),
        )
