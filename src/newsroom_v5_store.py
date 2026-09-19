from __future__ import annotations

import base64
import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from .newsroom_v5_db import connect, initialize, transaction


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row(row) -> dict | None:
    return dict(row) if row is not None else None


def _json(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _encode_cursor(published_at_source: str, story_id: str) -> str:
    raw = json.dumps([published_at_source or "", story_id], ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str) -> tuple[str, str]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        value = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
        if not isinstance(value, list) or len(value) != 2:
            raise ValueError
        return str(value[0] or ""), str(value[1])
    except Exception as exc:
        raise ValueError("invalid review cursor") from exc


class NewsroomV5Store:
    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        self.conn = connect(path)
        initialize(self.conn)

    def close(self) -> None:
        self.conn.close()

    def upsert_story(self, story: dict) -> dict:
        if not str(story.get("id") or "").strip():
            raise ValueError("story id is required")
        now = _now()
        values = {
            "id": str(story["id"]),
            "news_key": story.get("news_key"),
            "source_id": story.get("source_id"),
            "source_name": story.get("source_name") or story.get("source"),
            "source_url": story.get("source_url"),
            "source_item_id": story.get("source_item_id"),
            "original_title": story.get("original_title") or story.get("title"),
            "original_body": story.get("original_body") or story.get("original_summary") or story.get("summary"),
            "published_at_source": story.get("published_at_source") or story.get("published"),
            "discovered_at": story.get("discovered_at"),
            "state": story.get("state") or "received",
            "created_at": story.get("created_at") or now,
            "updated_at": story.get("updated_at") or now,
        }
        self.conn.execute(
            """
            INSERT INTO stories(
                id, news_key, source_id, source_name, source_url, source_item_id,
                original_title, original_body, published_at_source, discovered_at,
                state, created_at, updated_at
            ) VALUES (
                :id, :news_key, :source_id, :source_name, :source_url, :source_item_id,
                :original_title, :original_body, :published_at_source, :discovered_at,
                :state, :created_at, :updated_at
            )
            ON CONFLICT(id) DO UPDATE SET
                news_key=COALESCE(excluded.news_key, stories.news_key),
                source_id=COALESCE(excluded.source_id, stories.source_id),
                source_name=COALESCE(excluded.source_name, stories.source_name),
                source_url=COALESCE(excluded.source_url, stories.source_url),
                source_item_id=COALESCE(excluded.source_item_id, stories.source_item_id),
                original_title=COALESCE(excluded.original_title, stories.original_title),
                original_body=COALESCE(excluded.original_body, stories.original_body),
                published_at_source=COALESCE(excluded.published_at_source, stories.published_at_source),
                discovered_at=COALESCE(excluded.discovered_at, stories.discovered_at),
                state=excluded.state,
                updated_at=excluded.updated_at
            """,
            values,
        )
        return self.get_story(values["id"]) or values

    def get_story(self, story_id: str) -> dict | None:
        row = self.conn.execute(
            """
            SELECT s.*, t.title_fa, t.body_fa, t.backend AS translation_backend,
                   t.quality_passed, t.attempt_count AS translation_attempt_count,
                   t.last_error AS translation_last_error, t.translated_at,
                   e.importance, e.priority_class, e.publish_recommended, e.new_fact,
                   e.topic, e.reason AS editorial_reason, e.confidence, e.model AS editorial_model,
                   e.decided_at
            FROM stories s
            LEFT JOIN translations t ON t.story_id=s.id
            LEFT JOIN editorial_decisions e ON e.story_id=s.id
            WHERE s.id=?
            """,
            (story_id,),
        ).fetchone()
        return _row(row)

    def find_story(self, *, news_key: str | None = None, source_url: str | None = None) -> dict | None:
        if news_key:
            row = self.conn.execute("SELECT id FROM stories WHERE news_key=? ORDER BY updated_at DESC LIMIT 1", (news_key,)).fetchone()
            if row:
                return self.get_story(row[0])
        if source_url:
            row = self.conn.execute("SELECT id FROM stories WHERE source_url=? ORDER BY updated_at DESC LIMIT 1", (source_url,)).fetchone()
            if row:
                return self.get_story(row[0])
        return None

    def set_translation(
        self,
        story_id: str,
        *,
        title_fa: str,
        body_fa: str = "",
        backend: str = "",
        quality_passed: bool,
        attempt_count: int | None = None,
        last_error: str | None = None,
        translated_at: str | None = None,
    ) -> dict:
        existing = self.conn.execute("SELECT attempt_count FROM translations WHERE story_id=?", (story_id,)).fetchone()
        attempts = int(attempt_count if attempt_count is not None else ((existing[0] if existing else 0) + 1))
        self.conn.execute(
            """
            INSERT INTO translations(story_id,title_fa,body_fa,backend,quality_passed,attempt_count,last_error,translated_at)
            VALUES(?,?,?,?,?,?,?,?)
            ON CONFLICT(story_id) DO UPDATE SET
                title_fa=excluded.title_fa,
                body_fa=excluded.body_fa,
                backend=excluded.backend,
                quality_passed=excluded.quality_passed,
                attempt_count=excluded.attempt_count,
                last_error=excluded.last_error,
                translated_at=excluded.translated_at
            """,
            (story_id, title_fa or "", body_fa or "", backend or "", 1 if quality_passed else 0, attempts, last_error, translated_at or _now()),
        )
        return self.get_story(story_id) or {}

    def set_editorial_decision(self, story_id: str, **decision: Any) -> dict:
        self.conn.execute(
            """
            INSERT INTO editorial_decisions(
                story_id, importance, priority_class, publish_recommended, new_fact,
                topic, reason, confidence, model, decided_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(story_id) DO UPDATE SET
                importance=excluded.importance,
                priority_class=excluded.priority_class,
                publish_recommended=excluded.publish_recommended,
                new_fact=excluded.new_fact,
                topic=excluded.topic,
                reason=excluded.reason,
                confidence=excluded.confidence,
                model=excluded.model,
                decided_at=excluded.decided_at
            """,
            (
                story_id,
                decision.get("importance"),
                decision.get("priority_class"),
                1 if decision.get("publish_recommended") else 0,
                1 if decision.get("new_fact") else 0,
                decision.get("topic"),
                decision.get("reason"),
                decision.get("confidence"),
                decision.get("model"),
                decision.get("decided_at") or _now(),
            ),
        )
        return self.get_story(story_id) or {}

    def transition_story(self, story_id: str, expected_states: Iterable[str], new_state: str) -> bool:
        expected = tuple(dict.fromkeys(str(x) for x in expected_states))
        if not expected:
            return False
        placeholders = ",".join("?" for _ in expected)
        cur = self.conn.execute(
            f"UPDATE stories SET state=?, updated_at=? WHERE id=? AND state IN ({placeholders})",
            (new_state, _now(), story_id, *expected),
        )
        return cur.rowcount == 1

    def add_story_tombstone(
        self,
        story_id: str | None,
        *,
        news_key: str | None = None,
        source_url: str | None = None,
        reason: str = "rejected_manual",
    ) -> dict:
        if not news_key and not source_url:
            raise ValueError("tombstone requires news_key or source_url")
        identity = f"{news_key or ''}\x1f{source_url or ''}\x1f{reason}"
        tombstone_id = uuid.uuid5(uuid.NAMESPACE_URL, identity).hex
        self.conn.execute(
            """
            INSERT INTO story_tombstones(id,story_id,news_key,source_url,reason,created_at)
            VALUES(?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                story_id=COALESCE(excluded.story_id, story_tombstones.story_id),
                news_key=COALESCE(excluded.news_key, story_tombstones.news_key),
                source_url=COALESCE(excluded.source_url, story_tombstones.source_url)
            """,
            (tombstone_id, story_id, news_key, source_url, reason, _now()),
        )
        return dict(self.conn.execute("SELECT * FROM story_tombstones WHERE id=?", (tombstone_id,)).fetchone())

    def is_tombstoned(self, *, news_key: str | None = None, source_url: str | None = None) -> bool:
        clauses: list[str] = []
        params: list[str] = []
        if news_key:
            clauses.append("news_key=?")
            params.append(news_key)
        if source_url:
            clauses.append("source_url=?")
            params.append(source_url)
        if not clauses:
            return False
        row = self.conn.execute(
            f"SELECT 1 FROM story_tombstones WHERE {' OR '.join(clauses)} LIMIT 1",
            tuple(params),
        ).fetchone()
        return row is not None

    def list_review(self, limit: int = 25, cursor: str | None = None) -> dict:
        limit = max(1, min(int(limit), 100))
        params: list[Any] = []
        cursor_sql = ""
        if cursor:
            cursor_time, cursor_id = _decode_cursor(cursor)
            cursor_sql = "AND (COALESCE(s.published_at_source,'') < ? OR (COALESCE(s.published_at_source,'') = ? AND s.id < ?))"
            params.extend([cursor_time, cursor_time, cursor_id])
        params.append(limit + 1)
        rows = self.conn.execute(
            f"""
            SELECT s.*, t.title_fa, t.body_fa, t.backend AS translation_backend,
                   t.quality_passed, e.importance, e.priority_class, e.reason AS editorial_reason,
                   e.confidence
            FROM stories s
            JOIN translations t ON t.story_id=s.id AND t.quality_passed=1 AND LENGTH(TRIM(t.title_fa))>0
            LEFT JOIN editorial_decisions e ON e.story_id=s.id
            WHERE s.state='review' {cursor_sql}
            ORDER BY COALESCE(s.published_at_source,'') DESC, s.id DESC
            LIMIT ?
            """,
            tuple(params),
        ).fetchall()
        has_more = len(rows) > limit
        visible = rows[:limit]
        next_cursor = None
        if has_more and visible:
            last = visible[-1]
            next_cursor = _encode_cursor(str(last["published_at_source"] or ""), str(last["id"]))
        return {"items": [dict(row) for row in visible], "next_cursor": next_cursor}

    def list_published(self, limit: int = 50, cursor: str | None = None) -> dict:
        limit = max(1, min(int(limit), 100))
        params: list[Any] = []
        cursor_sql = ""
        if cursor:
            cursor_time, cursor_id = _decode_cursor(cursor)
            cursor_sql = "AND (COALESCE(s.published_at_source,'') < ? OR (COALESCE(s.published_at_source,'') = ? AND s.id < ?))"
            params.extend([cursor_time, cursor_time, cursor_id])
        params.append(limit + 1)
        rows = self.conn.execute(
            f"""
            SELECT s.*, t.title_fa, t.body_fa, p.telegram_message_id, p.published_at, p.copy_mode
            FROM stories s
            LEFT JOIN translations t ON t.story_id=s.id
            LEFT JOIN publications p ON p.story_id=s.id AND p.status='published'
            WHERE s.state='published' {cursor_sql}
            ORDER BY COALESCE(s.published_at_source,'') DESC, s.id DESC
            LIMIT ?
            """,
            tuple(params),
        ).fetchall()
        has_more = len(rows) > limit
        visible = rows[:limit]
        next_cursor = None
        if has_more and visible:
            last = visible[-1]
            next_cursor = _encode_cursor(str(last["published_at_source"] or ""), str(last["id"]))
        return {"items": [dict(row) for row in visible], "next_cursor": next_cursor}

    def create_publication_once(
        self,
        story_id: str,
        *,
        idempotency_key: str,
        copy_mode: str,
        title_fa: str,
        body_fa: str = "",
        status: str = "pending",
    ) -> dict:
        with transaction(self.conn):
            existing = self.conn.execute("SELECT * FROM publications WHERE idempotency_key=?", (idempotency_key,)).fetchone()
            if existing:
                return dict(existing)
            publication_id = uuid.uuid4().hex
            self.conn.execute(
                """
                INSERT INTO publications(id,story_id,idempotency_key,copy_mode,title_fa,body_fa,status,created_at)
                VALUES(?,?,?,?,?,?,?,?)
                """,
                (publication_id, story_id, idempotency_key, copy_mode, title_fa, body_fa or "", status, _now()),
            )
            return dict(self.conn.execute("SELECT * FROM publications WHERE id=?", (publication_id,)).fetchone())

    def get_publication(self, publication_id: str) -> dict | None:
        return _row(self.conn.execute("SELECT * FROM publications WHERE id=?", (publication_id,)).fetchone())

    def get_publication_by_key(self, idempotency_key: str) -> dict | None:
        return _row(self.conn.execute("SELECT * FROM publications WHERE idempotency_key=?", (idempotency_key,)).fetchone())

    def update_publication(self, publication_id: str, **fields: Any) -> dict | None:
        allowed = {"status", "telegram_message_id", "attempt_count", "last_error", "published_at"}
        updates = [(key, value) for key, value in fields.items() if key in allowed]
        if not updates:
            return self.get_publication(publication_id)
        sql = ", ".join(f"{key}=?" for key, _ in updates)
        self.conn.execute(f"UPDATE publications SET {sql} WHERE id=?", (*[v for _, v in updates], publication_id))
        return self.get_publication(publication_id)

    def enqueue_job(
        self,
        kind: str,
        *,
        story_id: str | None = None,
        payload: dict | None = None,
        available_at: str | None = None,
        job_id: str | None = None,
    ) -> dict:
        now = _now()
        job_id = job_id or uuid.uuid4().hex
        self.conn.execute(
            """
            INSERT INTO jobs(id,kind,story_id,payload_json,status,attempt_count,available_at,created_at,updated_at)
            VALUES(?,?,?,?, 'pending', 0, ?, ?, ?)
            ON CONFLICT(id) DO NOTHING
            """,
            (job_id, kind, story_id, _json(payload), available_at or now, now, now),
        )
        return dict(self.conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())

    def claim_jobs(self, kind: str, *, worker_id: str, limit: int = 1, lease_seconds: int = 60) -> list[dict]:
        now_dt = datetime.now(timezone.utc)
        now = now_dt.isoformat()
        lease_until = (now_dt + timedelta(seconds=max(1, int(lease_seconds)))).isoformat()
        limit = max(1, min(int(limit), 100))
        with transaction(self.conn):
            rows = self.conn.execute(
                """
                SELECT id FROM jobs
                WHERE kind=?
                  AND available_at<=?
                  AND (status='pending' OR (status='running' AND lease_until IS NOT NULL AND lease_until<=?))
                ORDER BY available_at, created_at, id
                LIMIT ?
                """,
                (kind, now, now, limit),
            ).fetchall()
            ids = [row[0] for row in rows]
            if not ids:
                return []
            placeholders = ",".join("?" for _ in ids)
            self.conn.execute(
                f"UPDATE jobs SET status='running', lease_owner=?, lease_until=?, updated_at=? WHERE id IN ({placeholders})",
                (worker_id, lease_until, now, *ids),
            )
            return [dict(row) for row in self.conn.execute(f"SELECT * FROM jobs WHERE id IN ({placeholders}) ORDER BY available_at, created_at, id", tuple(ids)).fetchall()]

    def finish_job(self, job_id: str) -> None:
        self.conn.execute(
            "UPDATE jobs SET status='done', lease_owner=NULL, lease_until=NULL, last_error=NULL, updated_at=? WHERE id=?",
            (_now(), job_id),
        )

    def retry_job(self, job_id: str, *, error: str, delay_seconds: float, terminal: bool = False) -> None:
        now_dt = datetime.now(timezone.utc)
        available_at = (now_dt + timedelta(seconds=max(0.0, float(delay_seconds)))).isoformat()
        self.conn.execute(
            """
            UPDATE jobs
            SET status=?, attempt_count=attempt_count+1, available_at=?, lease_owner=NULL,
                lease_until=NULL, last_error=?, updated_at=?
            WHERE id=?
            """,
            ("failed" if terminal else "pending", available_at, error, now_dt.isoformat(), job_id),
        )

    def upsert_source(self, source: dict) -> dict:
        source_id = str(source.get("id") or source.get("source_id") or "").strip()
        if not source_id:
            raise ValueError("source id is required")
        now = _now()
        self.conn.execute(
            """
            INSERT INTO sources(id,name,url,source_type,enabled,config_json,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name,
                url=excluded.url,
                source_type=excluded.source_type,
                enabled=excluded.enabled,
                config_json=excluded.config_json,
                updated_at=excluded.updated_at
            """,
            (
                source_id,
                str(source.get("name") or source.get("label") or source_id),
                str(source.get("url") or source.get("feed_url") or ""),
                str(source.get("type") or source.get("source_type") or ""),
                1 if source.get("enabled", True) else 0,
                _json(source),
                str(source.get("created_at") or now),
                now,
            ),
        )
        return dict(self.conn.execute("SELECT * FROM sources WHERE id=?", (source_id,)).fetchone())

    def list_sources(self) -> list[dict]:
        return [dict(row) for row in self.conn.execute("SELECT * FROM sources ORDER BY name, id").fetchall()]

    def append_audit(
        self,
        action: str,
        *,
        actor: str = "system",
        entity_type: str | None = None,
        entity_id: str | None = None,
        detail: dict | None = None,
    ) -> dict:
        row_id = uuid.uuid4().hex
        self.conn.execute(
            "INSERT INTO audit_log(id,actor,action,entity_type,entity_id,detail_json,created_at) VALUES(?,?,?,?,?,?,?)",
            (row_id, actor, action, entity_type, entity_id, _json(detail), _now()),
        )
        return dict(self.conn.execute("SELECT * FROM audit_log WHERE id=?", (row_id,)).fetchone())

    def append_luna_message(
        self,
        conversation_id: str,
        *,
        role: str,
        content: str,
        context: dict | None = None,
        message_id: str | None = None,
    ) -> dict:
        message_id = message_id or uuid.uuid4().hex
        self.conn.execute(
            "INSERT INTO luna_conversations(id,conversation_id,role,content,context_json,created_at) VALUES(?,?,?,?,?,?)",
            (message_id, conversation_id, role, content, _json(context), _now()),
        )
        return dict(self.conn.execute("SELECT * FROM luna_conversations WHERE id=?", (message_id,)).fetchone())

    def list_luna_messages(self, conversation_id: str, *, limit: int = 40) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT * FROM (
                SELECT * FROM luna_conversations WHERE conversation_id=? ORDER BY created_at DESC, id DESC LIMIT ?
            ) ORDER BY created_at, id
            """,
            (conversation_id, max(1, min(int(limit), 200))),
        ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            try:
                item["context"] = json.loads(item.pop("context_json") or "{}")
            except Exception:
                item["context"] = {}
            result.append(item)
        return result
