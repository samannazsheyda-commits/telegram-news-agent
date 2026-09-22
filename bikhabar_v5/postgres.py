from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .identity import ensure_story_identity
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

    def list_sources(self) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT * FROM sources ORDER BY enabled DESC, priority DESC, display_name ASC"
        ).fetchall()
        return [dict(row) for row in rows]

    def set_source_enabled(self, source_id: str, *, enabled: bool, actor: str) -> dict[str, Any]:
        with self.connection.transaction():
            row = self.connection.execute(
                """
                UPDATE sources SET enabled = %s, updated_at = now()
                WHERE id = %s
                RETURNING *
                """,
                (bool(enabled), source_id),
            ).fetchone()
            if row is None:
                raise LookupError(f"source not found: {source_id}")
            self._record_audit(
                actor=actor,
                action="source_enabled" if enabled else "source_disabled",
                entity_type="source",
                entity_id=source_id,
                status="succeeded",
                detail={},
            )
            return dict(row)

    def record_collector_run(
        self,
        source_id: str,
        *,
        status: str,
        received: int,
        inserted: int,
        error: str | None = None,
    ) -> dict[str, Any]:
        run_id = str(uuid.uuid4())
        received_count = max(0, int(received))
        inserted_count = max(0, int(inserted))
        with self.connection.transaction():
            row = self.connection.execute(
                """
                INSERT INTO collector_runs (
                    id, source_id, status, received_count, inserted_count,
                    duplicate_count, error_text, started_at, finished_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, now(), now())
                RETURNING *
                """,
                (
                    run_id,
                    source_id,
                    str(status),
                    received_count,
                    inserted_count,
                    max(0, received_count - inserted_count),
                    str(error)[:4000] if error else None,
                ),
            ).fetchone()
            self.connection.execute(
                """
                UPDATE sources
                SET last_fetch_at = now(), last_error = %s, updated_at = now()
                WHERE id = %s
                """,
                (str(error)[:4000] if error else None, source_id),
            )
            return dict(row)

    def ingest_story(self, story: Mapping[str, Any]) -> tuple[dict[str, Any], bool]:
        story = ensure_story_identity(story)
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

    def import_legacy_story(self, story: Mapping[str, Any], *, actor: str) -> dict[str, Any]:
        status = str(story.get("status") or "").strip().upper()
        if status not in {"PUBLISHED", "REJECTED_PERMANENT"}:
            raise ValueError("only terminal legacy history can be imported")
        story_id = str(story.get("id") or uuid.uuid4())
        source_url = str(story.get("source_url") or "").strip() or None
        fingerprint = str(story.get("fingerprint") or "").strip() or None
        if fingerprint is None and source_url:
            fingerprint = ensure_story_identity(story).get("fingerprint")
        with self.connection.transaction():
            row = self.connection.execute(
                """
                INSERT INTO stories (
                    id, source, source_url, original_title, original_text,
                    media_json, published_at_source, final_title, final_body,
                    status, fingerprint, telegram_message_id, reject_reason,
                    decision_actor
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
                RETURNING *
                """,
                (
                    story_id,
                    str(story.get("source") or "Legacy"),
                    source_url,
                    str(story.get("original_title") or ""),
                    str(story.get("original_text") or ""),
                    Jsonb(dict(story.get("media_json") or {})),
                    story.get("published_at_source"),
                    str(story.get("final_title") or ""),
                    str(story.get("final_body") or ""),
                    status,
                    fingerprint,
                    story.get("telegram_message_id"),
                    story.get("reject_reason"),
                    actor,
                ),
            ).fetchone()
            if row is None:
                existing = self.connection.execute(
                    """
                    SELECT * FROM stories
                    WHERE id = %s
                       OR (%s IS NOT NULL AND source_url = %s)
                       OR (%s IS NOT NULL AND fingerprint = %s)
                    LIMIT 1
                    """,
                    (story_id, source_url, source_url, fingerprint, fingerprint),
                ).fetchone()
                if existing is None:
                    raise RuntimeError("legacy story conflicted without an existing row")
                return dict(existing)
            if status == "REJECTED_PERMANENT" and (fingerprint or source_url):
                self.connection.execute(
                    """
                    INSERT INTO reject_blocklist (story_id, fingerprint, source_url, reason)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT DO NOTHING
                    """,
                    (story_id, fingerprint, source_url, str(story.get("reject_reason") or "legacy_reject")),
                )
            self._record_event(
                story_id=story_id,
                event_type="LEGACY_IMPORTED",
                from_status=None,
                to_status=status,
                actor=actor,
                detail={"legacy_id": story.get("legacy_id")},
            )
            self._record_audit(
                actor=actor,
                action="legacy_story_imported",
                entity_type="story",
                entity_id=story_id,
                status="succeeded",
                detail={"terminal_status": status},
            )
            return dict(row)

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

    def record_translation(
        self,
        story_id: str,
        *,
        provider: str,
        title: str,
        body: str,
        actor: str,
    ) -> dict[str, Any]:
        normalized_provider = str(provider or "").strip().lower()
        translated_title = str(title or "").strip()
        translated_body = str(body or "").strip()
        if normalized_provider not in {"google", "luna"}:
            raise ValueError("translation provider must be google or luna")
        if not translated_title:
            raise ValueError("translated title is required")

        expected_target = "GOOGLE_TRANSLATED" if normalized_provider == "google" else "LUNA_TRANSLATED"
        title_column = "google_title" if normalized_provider == "google" else "luna_title"
        body_column = "google_body" if normalized_provider == "google" else "luna_body"
        with self.connection.transaction():
            current = self._story_for_update(story_id)
            source, destination = require_transition(str(current["status"]), expected_target)
            updated = self.connection.execute(
                f"""
                UPDATE stories
                SET {title_column} = %s, {body_column} = %s, status = %s, updated_at = now()
                WHERE id = %s
                RETURNING *
                """,
                (translated_title, translated_body, destination, story_id),
            ).fetchone()
            detail = {"provider": normalized_provider}
            self._record_event(
                story_id=story_id,
                event_type="TRANSLATED",
                from_status=source,
                to_status=destination,
                actor=actor,
                detail=detail,
            )
            self._record_audit(
                actor=actor,
                action="story_translated",
                entity_type="story",
                entity_id=story_id,
                status="succeeded",
                detail=detail,
            )
            return dict(updated)

    def get_story(self, story_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM stories WHERE id = %s",
            (story_id,),
        ).fetchone()
        return dict(row) if row is not None else None

    def list_stories(
        self,
        *,
        statuses: tuple[str, ...],
        query: str,
        source: str,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        normalized_statuses = tuple(str(value).strip().upper() for value in statuses if value)
        page_number = max(1, int(page))
        limit = max(1, min(int(page_size), 100))
        clauses: list[str] = []
        parameters: list[Any] = []
        if normalized_statuses:
            clauses.append("status = ANY(%s)")
            parameters.append(list(normalized_statuses))
        search = str(query or "").strip()
        if search:
            clauses.append(
                "concat_ws(' ', original_title, original_text, google_title, google_body, "
                "luna_title, luna_body, final_title, final_body) ILIKE %s"
            )
            parameters.append(f"%{search}%")
        source_filter = str(source or "").strip()
        if source_filter:
            clauses.append("source ILIKE %s")
            parameters.append(f"%{source_filter}%")
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        total_row = self.connection.execute(
            f"SELECT count(*) AS total FROM stories {where}",
            tuple(parameters),
        ).fetchone()
        rows = self.connection.execute(
            f"""
            SELECT * FROM stories
            {where}
            ORDER BY published_at_source DESC NULLS LAST, received_at DESC, id DESC
            LIMIT %s OFFSET %s
            """,
            (*parameters, limit, (page_number - 1) * limit),
        ).fetchall()
        return {
            "items": [dict(row) for row in rows],
            "total": int(total_row["total"]),
            "page": page_number,
            "page_size": limit,
        }

    def story_ids_by_status(self, status: str, *, limit: int = 100) -> list[str]:
        rows = self.connection.execute(
            """
            SELECT id FROM stories
            WHERE status = %s
            ORDER BY received_at ASC, id ASC
            LIMIT %s
            """,
            (str(status).strip().upper(), max(1, min(int(limit), 500))),
        ).fetchall()
        return [str(row["id"]) for row in rows]

    def save_review(
        self,
        story_id: str,
        *,
        title: str,
        body: str,
        copy_mode: str,
        actor: str,
        approve: bool,
    ) -> dict[str, Any]:
        final_title = str(title or "").strip()
        final_body = str(body or "").strip()
        normalized_mode = str(copy_mode or "").strip().lower()
        if not final_title:
            raise ValueError("final title is required")
        if normalized_mode not in {"google", "luna", "edited"}:
            raise ValueError("copy_mode must be google, luna or edited")

        with self.connection.transaction():
            current = self._story_for_update(story_id)
            current_status = str(current["status"])
            destination = current_status
            if approve:
                _source, destination = require_transition(current_status, "APPROVED")
            elif current_status not in {"READY_FOR_REVIEW", "LUNA_TRANSLATED"}:
                raise ValueError(f"story cannot be reviewed in state {current_status}")
            updated = self.connection.execute(
                """
                UPDATE stories
                SET final_title = %s, final_body = %s, status = %s,
                    decision_actor = %s, updated_at = now()
                WHERE id = %s
                RETURNING *
                """,
                (final_title, final_body, destination, actor, story_id),
            ).fetchone()
            detail = {"copy_mode": normalized_mode, "approved": bool(approve)}
            self._record_event(
                story_id=story_id,
                event_type="REVIEW_APPROVED" if approve else "REVIEW_SAVED",
                from_status=current_status,
                to_status=destination,
                actor=actor,
                detail=detail,
            )
            self._record_audit(
                actor=actor,
                action="story_approved" if approve else "story_review_saved",
                entity_type="story",
                entity_id=story_id,
                status="succeeded",
                detail=detail,
            )
            return dict(updated)

    def prepare_publish(
        self,
        story_id: str,
        *,
        idempotency_key: str,
        copy_mode: str,
        payload: Mapping[str, Any],
        actor: str,
        allow_retry: bool,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        key = str(idempotency_key or "").strip()
        if not key:
            raise ValueError("publish idempotency_key is required")
        with self.connection.transaction():
            story = self._story_for_update(story_id)
            existing_row = self.connection.execute(
                "SELECT * FROM publish_attempts WHERE idempotency_key = %s FOR UPDATE",
                (key,),
            ).fetchone()
            if existing_row is not None:
                existing = dict(existing_row)
                existing["resumed"] = True
                if existing["status"] in {"completed", "ambiguous", "sending"}:
                    if existing["status"] == "sending":
                        existing["ambiguous"] = True
                    return story, existing
                if not allow_retry:
                    raise ValueError("failed publish requires an explicit controlled retry")
                source, destination = require_transition(str(story["status"]), "PUBLISHING")
                updated_story = self.connection.execute(
                    "UPDATE stories SET status = %s, updated_at = now() WHERE id = %s RETURNING *",
                    (destination, story_id),
                ).fetchone()
                attempt_row = self.connection.execute(
                    """
                    UPDATE publish_attempts
                    SET status = 'sending', ambiguous = FALSE, last_error = NULL,
                        attempt_count = attempt_count + 1, updated_at = now()
                    WHERE id = %s
                    RETURNING *
                    """,
                    (existing["id"],),
                ).fetchone()
                self._record_event(
                    story_id=story_id,
                    event_type="PUBLISH_RETRY_STARTED",
                    from_status=source,
                    to_status=destination,
                    actor=actor,
                    detail={"attempt_id": str(existing["id"])},
                )
                attempt = dict(attempt_row)
                attempt["resumed"] = False
                return dict(updated_story), attempt

            source, destination = require_transition(str(story["status"]), "PUBLISHING")
            actual_payload = dict(payload or {}) or {
                "text": f"{story.get('final_title') or ''}\n\n{story.get('final_body') or ''}".strip(),
                "media": dict(story.get("media_json") or {}),
            }
            attempt_id = str(uuid.uuid4())
            attempt_row = self.connection.execute(
                """
                INSERT INTO publish_attempts (
                    id, story_id, idempotency_key, copy_mode, payload_json,
                    status, attempt_count, ambiguous
                )
                VALUES (%s, %s, %s, %s, %s, 'sending', 1, FALSE)
                RETURNING *
                """,
                (attempt_id, story_id, key, copy_mode, Jsonb(actual_payload)),
            ).fetchone()
            updated_story = self.connection.execute(
                "UPDATE stories SET status = %s, updated_at = now() WHERE id = %s RETURNING *",
                (destination, story_id),
            ).fetchone()
            self._record_event(
                story_id=story_id,
                event_type="PUBLISH_STARTED",
                from_status=source,
                to_status=destination,
                actor=actor,
                detail={"attempt_id": attempt_id},
            )
            self._record_audit(
                actor=actor,
                action="publish_started",
                entity_type="story",
                entity_id=story_id,
                status="succeeded",
                detail={"attempt_id": attempt_id, "idempotency_key": key},
            )
            attempt = dict(attempt_row)
            attempt["resumed"] = False
            return dict(updated_story), attempt

    def complete_publish(
        self,
        story_id: str,
        attempt_id: str,
        *,
        telegram_message_id: int,
        actor: str,
    ) -> dict[str, Any]:
        message_id = int(telegram_message_id)
        if message_id <= 0:
            raise ValueError("telegram_message_id must be positive")
        with self.connection.transaction():
            story = self._story_for_update(story_id)
            source, destination = require_transition(str(story["status"]), "PUBLISHED")
            attempt = self.connection.execute(
                "SELECT * FROM publish_attempts WHERE id = %s AND story_id = %s FOR UPDATE",
                (attempt_id, story_id),
            ).fetchone()
            if attempt is None:
                raise LookupError("publish attempt not found")
            self.connection.execute(
                """
                UPDATE publish_attempts
                SET status = 'completed', telegram_message_id = %s,
                    ambiguous = FALSE, updated_at = now()
                WHERE id = %s
                """,
                (message_id, attempt_id),
            )
            updated = self.connection.execute(
                """
                UPDATE stories
                SET status = %s, telegram_message_id = %s, updated_at = now()
                WHERE id = %s
                RETURNING *
                """,
                (destination, message_id, story_id),
            ).fetchone()
            detail = {"attempt_id": str(attempt_id), "telegram_message_id": message_id}
            self._record_event(
                story_id=story_id,
                event_type="PUBLISHED",
                from_status=source,
                to_status=destination,
                actor=actor,
                detail=detail,
            )
            self._record_audit(
                actor=actor,
                action="publish_completed",
                entity_type="story",
                entity_id=story_id,
                status="succeeded",
                detail=detail,
            )
            return dict(updated)

    def fail_publish(
        self,
        story_id: str,
        attempt_id: str,
        *,
        error: str,
        ambiguous: bool,
        actor: str,
    ) -> dict[str, Any]:
        with self.connection.transaction():
            story = self._story_for_update(story_id)
            source, destination = require_transition(str(story["status"]), "PUBLISH_FAILED")
            attempt_status = "ambiguous" if ambiguous else "failed"
            attempt = self.connection.execute(
                """
                UPDATE publish_attempts
                SET status = %s, ambiguous = %s, last_error = %s, updated_at = now()
                WHERE id = %s AND story_id = %s
                RETURNING *
                """,
                (attempt_status, bool(ambiguous), str(error or "")[:4000], attempt_id, story_id),
            ).fetchone()
            if attempt is None:
                raise LookupError("publish attempt not found")
            updated = self.connection.execute(
                "UPDATE stories SET status = %s, updated_at = now() WHERE id = %s RETURNING *",
                (destination, story_id),
            ).fetchone()
            detail = {"attempt_id": str(attempt_id), "ambiguous": bool(ambiguous), "error": str(error)}
            self._record_event(
                story_id=story_id,
                event_type="PUBLISH_FAILED",
                from_status=source,
                to_status=destination,
                actor=actor,
                detail=detail,
            )
            self._record_audit(
                actor=actor,
                action="publish_failed",
                entity_type="story",
                entity_id=story_id,
                status="failed",
                detail=detail,
            )
            return dict(updated)

    def reconcile_publish(
        self,
        story_id: str,
        attempt_id: str,
        *,
        telegram_message_id: int,
        actor: str,
    ) -> dict[str, Any]:
        message_id = int(telegram_message_id)
        if message_id <= 0:
            raise ValueError("telegram_message_id must be positive")
        with self.connection.transaction():
            story = self._story_for_update(story_id)
            attempt = self.connection.execute(
                "SELECT * FROM publish_attempts WHERE id = %s AND story_id = %s FOR UPDATE",
                (attempt_id, story_id),
            ).fetchone()
            if attempt is None or not bool(attempt["ambiguous"]):
                raise ValueError("publish attempt is not ambiguous")
            source, publishing = require_transition(str(story["status"]), "PUBLISHING")
            _publishing, destination = require_transition(publishing, "PUBLISHED")
            self.connection.execute(
                """
                UPDATE publish_attempts
                SET status = 'completed', telegram_message_id = %s,
                    ambiguous = FALSE, updated_at = now()
                WHERE id = %s
                """,
                (message_id, attempt_id),
            )
            updated = self.connection.execute(
                """
                UPDATE stories
                SET status = %s, telegram_message_id = %s, updated_at = now()
                WHERE id = %s
                RETURNING *
                """,
                (destination, message_id, story_id),
            ).fetchone()
            detail = {"attempt_id": str(attempt_id), "telegram_message_id": message_id}
            self._record_event(
                story_id=story_id,
                event_type="PUBLISH_RECONCILED",
                from_status=source,
                to_status=destination,
                actor=actor,
                detail=detail,
            )
            self._record_audit(
                actor=actor,
                action="publish_reconciled",
                entity_type="story",
                entity_id=story_id,
                status="succeeded",
                detail=detail,
            )
            return dict(updated)

    def upsert_newsroom_rule(
        self,
        rule_key: str,
        rule: Mapping[str, Any],
        *,
        actor: str,
    ) -> dict[str, Any]:
        key = str(rule_key or "").strip()
        if not key:
            raise ValueError("rule_key is required")
        with self.connection.transaction():
            row = self.connection.execute(
                """
                INSERT INTO newsroom_rules (rule_key, rule_json, enabled, updated_by)
                VALUES (%s, %s, TRUE, %s)
                ON CONFLICT (rule_key) DO UPDATE SET
                    rule_json = EXCLUDED.rule_json,
                    enabled = TRUE,
                    updated_by = EXCLUDED.updated_by,
                    updated_at = now()
                RETURNING *
                """,
                (key, Jsonb(dict(rule)), actor),
            ).fetchone()
            self._record_audit(
                actor=actor,
                action="newsroom_rule_upserted",
                entity_type="newsroom_rule",
                entity_id=key,
                status="succeeded",
                detail={},
            )
            return dict(row)

    def list_newsroom_rules(self) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT * FROM newsroom_rules WHERE enabled = TRUE ORDER BY rule_key ASC"
        ).fetchall()
        return [dict(row) for row in rows]

    def get_newsroom_rule(self, rule_key: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM newsroom_rules WHERE rule_key = %s",
            (str(rule_key),),
        ).fetchone()
        return dict(row) if row is not None else None

    def get_service_health(self, service_name: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM service_health WHERE service_name = %s",
            (str(service_name),),
        ).fetchone()
        return dict(row) if row is not None else None

    def update_service_health(
        self,
        service_name: str,
        *,
        status: str,
        detail: Mapping[str, Any],
    ) -> dict[str, Any]:
        row = self.connection.execute(
            """
            INSERT INTO service_health (service_name, status, detail_json)
            VALUES (%s, %s, %s)
            ON CONFLICT (service_name) DO UPDATE SET
                status = EXCLUDED.status,
                detail_json = EXCLUDED.detail_json,
                checked_at = now()
            RETURNING *
            """,
            (str(service_name), str(status), Jsonb(dict(detail))),
        ).fetchone()
        return dict(row)

    def list_service_health(self) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT * FROM service_health ORDER BY service_name ASC"
        ).fetchall()
        return [dict(row) for row in rows]

    def dashboard_metrics(self) -> dict[str, int]:
        row = self.connection.execute(
            """
            SELECT
                (SELECT count(*) FROM sources) AS sources_total,
                count(*) FILTER (WHERE status IN ('READY_FOR_REVIEW', 'LUNA_TRANSLATED')) AS review_ready,
                count(*) FILTER (WHERE status = 'APPROVED') AS approved,
                count(*) FILTER (WHERE status = 'PUBLISH_FAILED') AS publish_failed,
                count(*) FILTER (
                    WHERE status = 'PUBLISHED' AND updated_at >= date_trunc('day', now())
                ) AS published_today
            FROM stories
            """
        ).fetchone()
        return {key: int(value or 0) for key, value in dict(row).items()}

    def list_audit(self, *, limit: int = 100) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT * FROM audit_log ORDER BY id DESC LIMIT %s",
            (max(1, min(int(limit), 500)),),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_luna_conversation(self, user_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM luna_conversations WHERE user_id = %s",
            (str(user_id),),
        ).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["messages"] = list(result.pop("messages_json") or [])
        result["context"] = dict(result.pop("context_json") or {})
        return result

    def save_luna_conversation(
        self,
        user_id: str,
        *,
        messages: list[dict[str, Any]],
        context: Mapping[str, Any],
    ) -> dict[str, Any]:
        conversation_id = str(uuid.uuid4())
        row = self.connection.execute(
            """
            INSERT INTO luna_conversations (id, user_id, messages_json, context_json)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE SET
                messages_json = EXCLUDED.messages_json,
                context_json = EXCLUDED.context_json,
                updated_at = now()
            RETURNING *
            """,
            (conversation_id, str(user_id), Jsonb(messages), Jsonb(dict(context))),
        ).fetchone()
        return dict(row)

    def record_operator_audit(
        self,
        *,
        actor: str,
        action: str,
        entity_type: str,
        entity_id: str,
        status: str,
        detail: Mapping[str, Any],
    ) -> None:
        with self.connection.transaction():
            self._record_audit(
                actor=actor,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                status=status,
                detail=detail,
            )

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
