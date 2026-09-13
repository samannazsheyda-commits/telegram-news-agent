from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class StoryRecord:
    story_id: str
    source_item_id: str
    source: str
    source_url: str
    title: str
    summary: str
    published_at: str
    fetched_at: str
    media: list[dict]
    source_priority: str
    fingerprint: str
    decision_state: str
    decision_reason: str
    duplicate_of: str
    publish_state: str
    last_publish_error: str
    telegram_message_id: int | None
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class PublishAttempt:
    story_id: str
    attempt_no: int
    state: str
    error: str
    telegram_message_id: int | None
    started_at: str
    finished_at: str


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _media_json(media) -> str:
    value = media if isinstance(media, list) else []
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _parse_media(value: str) -> list[dict]:
    try:
        parsed = json.loads(str(value or "[]"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    if not isinstance(parsed, list):
        return []
    return [dict(row) for row in parsed if isinstance(row, dict)]


class NewsroomV3Store:
    """SQLite/WAL authoritative state for Newsroom V3."""

    _DECISION_STATES = {"ready", "waiting", "rejected", "duplicate"}

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, timeout=5)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._create_schema()

    def _create_schema(self) -> None:
        with self._conn:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS stories (
                    story_id TEXT PRIMARY KEY,
                    source_item_id TEXT NOT NULL DEFAULT '',
                    source TEXT NOT NULL DEFAULT '',
                    source_url TEXT NOT NULL DEFAULT '',
                    title TEXT NOT NULL DEFAULT '',
                    summary TEXT NOT NULL DEFAULT '',
                    published_at TEXT NOT NULL DEFAULT '',
                    fetched_at TEXT NOT NULL DEFAULT '',
                    media_json TEXT NOT NULL DEFAULT '[]',
                    source_priority TEXT NOT NULL DEFAULT 'normal',
                    fingerprint TEXT NOT NULL DEFAULT '',
                    decision_state TEXT NOT NULL,
                    decision_reason TEXT NOT NULL DEFAULT '',
                    duplicate_of TEXT NOT NULL DEFAULT '',
                    publish_state TEXT NOT NULL DEFAULT 'not_attempted',
                    last_publish_error TEXT NOT NULL DEFAULT '',
                    telegram_message_id INTEGER,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_v3_stories_source_url
                    ON stories(source_url);
                CREATE INDEX IF NOT EXISTS idx_v3_stories_fingerprint
                    ON stories(fingerprint);
                CREATE INDEX IF NOT EXISTS idx_v3_stories_states
                    ON stories(decision_state, publish_state);

                CREATE TABLE IF NOT EXISTS publish_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    story_id TEXT NOT NULL,
                    attempt_no INTEGER NOT NULL,
                    state TEXT NOT NULL,
                    error TEXT NOT NULL DEFAULT '',
                    telegram_message_id INTEGER,
                    started_at TEXT NOT NULL,
                    finished_at TEXT NOT NULL DEFAULT '',
                    FOREIGN KEY(story_id) REFERENCES stories(story_id) ON DELETE CASCADE,
                    UNIQUE(story_id, attempt_no)
                );

                CREATE INDEX IF NOT EXISTS idx_v3_publish_attempts_story
                    ON publish_attempts(story_id, attempt_no);
                """
            )
            self._ensure_story_columns()

    def _ensure_story_columns(self) -> None:
        existing = {
            str(row["name"])
            for row in self._conn.execute("PRAGMA table_info(stories)").fetchall()
        }
        migrations = {
            "fetched_at": "TEXT NOT NULL DEFAULT ''",
            "media_json": "TEXT NOT NULL DEFAULT '[]'",
            "source_priority": "TEXT NOT NULL DEFAULT 'normal'",
        }
        for name, definition in migrations.items():
            if name not in existing:
                self._conn.execute(f"ALTER TABLE stories ADD COLUMN {name} {definition}")

    def close(self) -> None:
        self._conn.close()

    def journal_mode(self) -> str:
        row = self._conn.execute("PRAGMA journal_mode").fetchone()
        return str(row[0] if row else "")

    def upsert_story(
        self,
        *,
        story_id: str,
        source_item_id: str,
        source: str,
        source_url: str,
        title: str,
        summary: str,
        published_at: str,
        fingerprint: str,
        decision_state: str,
        decision_reason: str = "",
        duplicate_of: str = "",
        fetched_at: str = "",
        media=None,
        source_priority: str = "normal",
    ) -> StoryRecord:
        now = _utc_now()
        encoded_media = _media_json(media)
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO stories (
                    story_id, source_item_id, source, source_url, title, summary,
                    published_at, fetched_at, media_json, source_priority,
                    fingerprint, decision_state, decision_reason, duplicate_of,
                    publish_state, last_publish_error, telegram_message_id,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'not_attempted', '', NULL, ?, ?)
                ON CONFLICT(story_id) DO UPDATE SET
                    source_item_id=excluded.source_item_id,
                    source=excluded.source,
                    source_url=excluded.source_url,
                    title=excluded.title,
                    summary=excluded.summary,
                    published_at=excluded.published_at,
                    fetched_at=excluded.fetched_at,
                    media_json=excluded.media_json,
                    source_priority=excluded.source_priority,
                    fingerprint=excluded.fingerprint,
                    decision_state=excluded.decision_state,
                    decision_reason=excluded.decision_reason,
                    duplicate_of=excluded.duplicate_of,
                    updated_at=excluded.updated_at
                """,
                (
                    story_id,
                    source_item_id,
                    source,
                    source_url,
                    title,
                    summary,
                    published_at,
                    str(fetched_at or ""),
                    encoded_media,
                    str(source_priority or "normal"),
                    fingerprint,
                    decision_state,
                    decision_reason,
                    duplicate_of,
                    now,
                    now,
                ),
            )
        record = self.get_story(story_id)
        if record is None:
            raise RuntimeError("story upsert did not persist")
        return record

    def get_story(self, story_id: str) -> StoryRecord | None:
        row = self._conn.execute(
            "SELECT * FROM stories WHERE story_id = ?",
            (story_id,),
        ).fetchone()
        return self._story_from_row(row) if row is not None else None

    def set_decision(
        self,
        story_id: str,
        state: str,
        *,
        reason: str = "",
        duplicate_of: str = "",
    ) -> StoryRecord:
        current = self.get_story(story_id)
        if current is None:
            raise KeyError(story_id)
        resolved = str(state or "").strip().lower()
        if resolved not in self._DECISION_STATES:
            raise ValueError(f"invalid decision state: {state}")
        resolved_duplicate = str(duplicate_of or "").strip()
        if resolved == "duplicate" and not resolved_duplicate:
            raise ValueError("duplicate_of is required for duplicate decision")
        if resolved != "duplicate":
            resolved_duplicate = ""
        now = _utc_now()
        with self._conn:
            self._conn.execute(
                """
                UPDATE stories
                SET decision_state=?, decision_reason=?, duplicate_of=?, updated_at=?
                WHERE story_id=?
                """,
                (resolved, str(reason or ""), resolved_duplicate, now, story_id),
            )
        updated = self.get_story(story_id)
        if updated is None:
            raise RuntimeError("decision update did not persist")
        return updated

    def find_canonical_story(
        self,
        *,
        source_url: str,
        fingerprint: str,
        exclude_story_id: str = "",
    ) -> StoryRecord | None:
        url = str(source_url or "").strip()
        fp = str(fingerprint or "").strip()
        excluded = str(exclude_story_id or "").strip()
        if not url and not fp:
            return None
        row = self._conn.execute(
            """
            SELECT *
            FROM stories
            WHERE decision_state='ready'
              AND story_id <> ?
              AND (
                    (? <> '' AND source_url = ?)
                 OR (? <> '' AND fingerprint = ?)
              )
            ORDER BY
                CASE WHEN ? <> '' AND source_url = ? THEN 0 ELSE 1 END,
                created_at ASC,
                story_id ASC
            LIMIT 1
            """,
            (excluded, url, url, fp, fp, url, url),
        ).fetchone()
        return self._story_from_row(row) if row is not None else None

    def list_publishable(self, *, limit: int = 10) -> list[StoryRecord]:
        bounded = max(1, min(100, int(limit)))
        rows = self._conn.execute(
            """
            SELECT *
            FROM stories
            WHERE decision_state='ready'
              AND publish_state IN ('not_attempted', 'failed')
              AND telegram_message_id IS NULL
            ORDER BY
                CASE WHEN publish_state='failed' THEN 0 ELSE 1 END,
                created_at ASC,
                story_id ASC
            LIMIT ?
            """,
            (bounded,),
        ).fetchall()
        return [self._story_from_row(row) for row in rows]

    def begin_publish(self, story_id: str) -> PublishAttempt:
        story = self.get_story(story_id)
        if story is None:
            raise KeyError(story_id)
        if story.publish_state == "published":
            raise ValueError("story is already published")
        if story.publish_state == "publishing":
            raise ValueError("story already has an active publish attempt")

        row = self._conn.execute(
            "SELECT COALESCE(MAX(attempt_no), 0) FROM publish_attempts WHERE story_id = ?",
            (story_id,),
        ).fetchone()
        attempt_no = int(row[0] if row else 0) + 1
        now = _utc_now()
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO publish_attempts (
                    story_id, attempt_no, state, error, telegram_message_id,
                    started_at, finished_at
                ) VALUES (?, ?, 'publishing', '', NULL, ?, '')
                """,
                (story_id, attempt_no, now),
            )
            self._conn.execute(
                """
                UPDATE stories
                SET publish_state='publishing', last_publish_error='', updated_at=?
                WHERE story_id=?
                """,
                (now, story_id),
            )
        return PublishAttempt(
            story_id=story_id,
            attempt_no=attempt_no,
            state="publishing",
            error="",
            telegram_message_id=None,
            started_at=now,
            finished_at="",
        )

    def mark_publish_failed(self, story_id: str, error: str) -> None:
        attempt = self._active_attempt(story_id)
        now = _utc_now()
        detail = str(error or "publish_failed")
        with self._conn:
            self._conn.execute(
                """
                UPDATE publish_attempts
                SET state='failed', error=?, finished_at=?
                WHERE story_id=? AND attempt_no=?
                """,
                (detail, now, story_id, attempt.attempt_no),
            )
            self._conn.execute(
                """
                UPDATE stories
                SET publish_state='failed', last_publish_error=?, updated_at=?
                WHERE story_id=?
                """,
                (detail, now, story_id),
            )

    def mark_published(self, story_id: str, *, telegram_message_id: int) -> None:
        attempt = self._active_attempt(story_id)
        message_id = int(telegram_message_id)
        now = _utc_now()
        with self._conn:
            self._conn.execute(
                """
                UPDATE publish_attempts
                SET state='published', error='', telegram_message_id=?, finished_at=?
                WHERE story_id=? AND attempt_no=?
                """,
                (message_id, now, story_id, attempt.attempt_no),
            )
            self._conn.execute(
                """
                UPDATE stories
                SET publish_state='published', last_publish_error='',
                    telegram_message_id=?, updated_at=?
                WHERE story_id=?
                """,
                (message_id, now, story_id),
            )

    def list_publish_attempts(self, story_id: str) -> list[PublishAttempt]:
        rows = self._conn.execute(
            """
            SELECT story_id, attempt_no, state, error, telegram_message_id,
                   started_at, finished_at
            FROM publish_attempts
            WHERE story_id=?
            ORDER BY attempt_no ASC
            """,
            (story_id,),
        ).fetchall()
        return [self._attempt_from_row(row) for row in rows]

    def _active_attempt(self, story_id: str) -> PublishAttempt:
        row = self._conn.execute(
            """
            SELECT story_id, attempt_no, state, error, telegram_message_id,
                   started_at, finished_at
            FROM publish_attempts
            WHERE story_id=? AND state='publishing'
            ORDER BY attempt_no DESC
            LIMIT 1
            """,
            (story_id,),
        ).fetchone()
        if row is None:
            raise ValueError("story has no active publish attempt")
        return self._attempt_from_row(row)

    @staticmethod
    def _story_from_row(row: sqlite3.Row) -> StoryRecord:
        return StoryRecord(
            story_id=str(row["story_id"]),
            source_item_id=str(row["source_item_id"]),
            source=str(row["source"]),
            source_url=str(row["source_url"]),
            title=str(row["title"]),
            summary=str(row["summary"]),
            published_at=str(row["published_at"]),
            fetched_at=str(row["fetched_at"]),
            media=_parse_media(str(row["media_json"])),
            source_priority=str(row["source_priority"] or "normal"),
            fingerprint=str(row["fingerprint"]),
            decision_state=str(row["decision_state"]),
            decision_reason=str(row["decision_reason"]),
            duplicate_of=str(row["duplicate_of"]),
            publish_state=str(row["publish_state"]),
            last_publish_error=str(row["last_publish_error"]),
            telegram_message_id=(
                int(row["telegram_message_id"])
                if row["telegram_message_id"] is not None
                else None
            ),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    @staticmethod
    def _attempt_from_row(row: sqlite3.Row) -> PublishAttempt:
        return PublishAttempt(
            story_id=str(row["story_id"]),
            attempt_no=int(row["attempt_no"]),
            state=str(row["state"]),
            error=str(row["error"]),
            telegram_message_id=(
                int(row["telegram_message_id"])
                if row["telegram_message_id"] is not None
                else None
            ),
            started_at=str(row["started_at"]),
            finished_at=str(row["finished_at"]),
        )
