from __future__ import annotations


REQUIRED_TABLES = frozenset(
    {
        "sources",
        "stories",
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
    }
)

POSTGRES_SCHEMA = r"""
CREATE TABLE IF NOT EXISTS sources (
    id UUID PRIMARY KEY,
    kind TEXT NOT NULL,
    identity TEXT NOT NULL,
    display_name TEXT NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    priority INTEGER NOT NULL DEFAULT 0,
    category TEXT,
    reliability_score NUMERIC(5,2),
    last_fetch_at TIMESTAMPTZ,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(kind, identity)
);

CREATE TABLE IF NOT EXISTS stories (
    id UUID PRIMARY KEY,
    source_id UUID REFERENCES sources(id),
    source TEXT NOT NULL,
    source_url TEXT,
    original_title TEXT,
    original_text TEXT,
    media_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    published_at_source TIMESTAMPTZ,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    google_title TEXT,
    google_body TEXT,
    luna_title TEXT,
    luna_body TEXT,
    final_title TEXT,
    final_body TEXT,
    importance INTEGER,
    category TEXT,
    status TEXT NOT NULL DEFAULT 'NEW' CHECK (status IN (
        'NEW','GOOGLE_TRANSLATING','GOOGLE_TRANSLATED','READY_FOR_REVIEW',
        'LUNA_TRANSLATED','APPROVED','PUBLISHING','PUBLISHED',
        'REJECTED_PERMANENT','PUBLISH_FAILED'
    )),
    fingerprint TEXT,
    telegram_message_id BIGINT,
    reject_reason TEXT,
    decision_actor TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS stories_fingerprint_unique
    ON stories(fingerprint) WHERE fingerprint IS NOT NULL AND fingerprint <> '';
CREATE UNIQUE INDEX IF NOT EXISTS stories_source_url_unique
    ON stories(source_url) WHERE source_url IS NOT NULL AND source_url <> '';
CREATE INDEX IF NOT EXISTS stories_review_order_idx
    ON stories(status, published_at_source DESC NULLS LAST, received_at DESC);

CREATE TABLE IF NOT EXISTS story_events (
    id BIGSERIAL PRIMARY KEY,
    story_id UUID NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    from_status TEXT,
    to_status TEXT,
    actor TEXT NOT NULL,
    detail_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS audit_log (
    id BIGSERIAL PRIMARY KEY,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT,
    status TEXT NOT NULL,
    detail_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS reject_blocklist (
    id BIGSERIAL PRIMARY KEY,
    story_id UUID,
    fingerprint TEXT,
    source_url TEXT,
    reason TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (fingerprint IS NOT NULL OR source_url IS NOT NULL)
);
CREATE UNIQUE INDEX IF NOT EXISTS reject_blocklist_fingerprint_unique
    ON reject_blocklist(fingerprint) WHERE fingerprint IS NOT NULL AND fingerprint <> '';
CREATE UNIQUE INDEX IF NOT EXISTS reject_blocklist_url_unique
    ON reject_blocklist(source_url) WHERE source_url IS NOT NULL AND source_url <> '';

CREATE TABLE IF NOT EXISTS newsroom_rules (
    id BIGSERIAL PRIMARY KEY,
    rule_key TEXT NOT NULL UNIQUE,
    rule_json JSONB NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    updated_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS luna_conversations (
    id UUID PRIMARY KEY,
    user_id TEXT NOT NULL,
    messages_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    context_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS publish_attempts (
    id UUID PRIMARY KEY,
    story_id UUID NOT NULL REFERENCES stories(id),
    idempotency_key TEXT NOT NULL UNIQUE,
    copy_mode TEXT NOT NULL,
    payload_json JSONB NOT NULL,
    status TEXT NOT NULL,
    telegram_message_id BIGINT,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    ambiguous BOOLEAN NOT NULL DEFAULT FALSE,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS collector_runs (
    id UUID PRIMARY KEY,
    source_id UUID REFERENCES sources(id),
    status TEXT NOT NULL,
    received_count INTEGER NOT NULL DEFAULT 0,
    inserted_count INTEGER NOT NULL DEFAULT 0,
    duplicate_count INTEGER NOT NULL DEFAULT 0,
    error_text TEXT,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS service_health (
    service_name TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    detail_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    checked_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sessions (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    csrf_secret TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE OR REPLACE FUNCTION prevent_source_timestamp_change()
RETURNS trigger AS $$
BEGIN
    IF OLD.published_at_source IS DISTINCT FROM NEW.published_at_source THEN
        RAISE EXCEPTION 'published_at_source is immutable';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS stories_source_timestamp_immutable ON stories;
CREATE TRIGGER stories_source_timestamp_immutable
BEFORE UPDATE OF published_at_source ON stories
FOR EACH ROW EXECUTE FUNCTION prevent_source_timestamp_change();
""".strip()
