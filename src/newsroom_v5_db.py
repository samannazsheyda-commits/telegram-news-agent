from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_meta (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS stories (
    id TEXT PRIMARY KEY,
    news_key TEXT,
    source_id TEXT,
    source_name TEXT,
    source_url TEXT,
    source_item_id TEXT,
    original_title TEXT,
    original_body TEXT,
    published_at_source TEXT,
    discovered_at TEXT,
    state TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_stories_state_time_id
    ON stories(state, published_at_source DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_stories_news_key ON stories(news_key);
CREATE INDEX IF NOT EXISTS idx_stories_source_url ON stories(source_url);
CREATE INDEX IF NOT EXISTS idx_stories_source_identity ON stories(source_id, source_item_id);

CREATE TABLE IF NOT EXISTS translations (
    story_id TEXT PRIMARY KEY REFERENCES stories(id) ON DELETE CASCADE,
    title_fa TEXT NOT NULL DEFAULT '',
    body_fa TEXT NOT NULL DEFAULT '',
    backend TEXT NOT NULL DEFAULT '',
    quality_passed INTEGER NOT NULL DEFAULT 0,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    translated_at TEXT
);

CREATE TABLE IF NOT EXISTS editorial_decisions (
    story_id TEXT PRIMARY KEY REFERENCES stories(id) ON DELETE CASCADE,
    importance TEXT,
    priority_class TEXT,
    publish_recommended INTEGER NOT NULL DEFAULT 0,
    new_fact INTEGER NOT NULL DEFAULT 0,
    topic TEXT,
    reason TEXT,
    confidence REAL,
    model TEXT,
    decided_at TEXT
);

CREATE TABLE IF NOT EXISTS publications (
    id TEXT PRIMARY KEY,
    story_id TEXT NOT NULL REFERENCES stories(id) ON DELETE RESTRICT,
    idempotency_key TEXT NOT NULL UNIQUE,
    copy_mode TEXT NOT NULL,
    title_fa TEXT NOT NULL,
    body_fa TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    telegram_message_id TEXT,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    created_at TEXT NOT NULL,
    published_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_publications_story ON publications(story_id);
CREATE INDEX IF NOT EXISTS idx_publications_status ON publications(status, created_at);

CREATE TABLE IF NOT EXISTS story_tombstones (
    id TEXT PRIMARY KEY,
    story_id TEXT REFERENCES stories(id) ON DELETE SET NULL,
    news_key TEXT,
    source_url TEXT,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tombstones_news_key ON story_tombstones(news_key);
CREATE INDEX IF NOT EXISTS idx_tombstones_source_url ON story_tombstones(source_url);
CREATE UNIQUE INDEX IF NOT EXISTS idx_tombstones_identity_reason
    ON story_tombstones(COALESCE(news_key, ''), COALESCE(source_url, ''), reason);

CREATE TABLE IF NOT EXISTS sources (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL DEFAULT '',
    url TEXT NOT NULL DEFAULT '',
    source_type TEXT NOT NULL DEFAULT '',
    enabled INTEGER NOT NULL DEFAULT 1,
    config_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    story_id TEXT REFERENCES stories(id) ON DELETE CASCADE,
    payload_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'pending',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    available_at TEXT NOT NULL,
    lease_until TEXT,
    lease_owner TEXT,
    last_error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_jobs_claim
    ON jobs(kind, status, available_at, lease_until, created_at);

CREATE TABLE IF NOT EXISTS luna_conversations (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    context_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_luna_conversation_time
    ON luna_conversations(conversation_id, created_at, id);

CREATE TABLE IF NOT EXISTS audit_log (
    id TEXT PRIMARY KEY,
    actor TEXT NOT NULL DEFAULT 'system',
    action TEXT NOT NULL,
    entity_type TEXT,
    entity_id TEXT,
    detail_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_entity_time
    ON audit_log(entity_type, entity_id, created_at);
"""


def connect(path: str | Path) -> sqlite3.Connection:
    raw = str(path)
    if raw != ":memory:":
        Path(raw).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(raw, timeout=5.0, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    if raw != ":memory:":
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def initialize(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA)
    row = conn.execute("SELECT version FROM schema_meta LIMIT 1").fetchone()
    if row is None:
        conn.execute("INSERT INTO schema_meta(version) VALUES (?)", (SCHEMA_VERSION,))
    elif int(row[0]) != SCHEMA_VERSION:
        raise RuntimeError(f"unsupported newsroom schema version: {row[0]}")


@contextmanager
def transaction(conn: sqlite3.Connection, *, immediate: bool = True) -> Iterator[sqlite3.Connection]:
    if conn.in_transaction:
        savepoint = f"sp_{id(conn)}"
        conn.execute(f"SAVEPOINT {savepoint}")
        try:
            yield conn
        except Exception:
            conn.execute(f"ROLLBACK TO {savepoint}")
            conn.execute(f"RELEASE {savepoint}")
            raise
        else:
            conn.execute(f"RELEASE {savepoint}")
        return

    conn.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
    try:
        yield conn
    except Exception:
        conn.rollback()
        raise
    else:
        conn.commit()
