from __future__ import annotations

import hashlib
from dataclasses import dataclass

from .newsroom_v5_store import NewsroomV5Store

JOB_KINDS = {"translate_story", "editorial_story", "publish_story", "reconcile_publication"}


def retry_delay_seconds(attempt: int, *, seed: str = "", base_seconds: int = 15, max_seconds: int = 3600) -> int:
    attempt = max(1, int(attempt))
    base = min(max_seconds, base_seconds * (2 ** (attempt - 1)))
    digest = hashlib.sha256(f"{seed}:{attempt}".encode("utf-8")).digest()
    jitter_ratio = int.from_bytes(digest[:2], "big") / 65535.0
    jitter = int(min(max_seconds - base, max(1, base // 4)) * jitter_ratio)
    return min(max_seconds, base + jitter)


@dataclass(frozen=True)
class JobResult:
    job_id: str
    status: str
    error: str = ""


def enqueue_once(store: NewsroomV5Store, kind: str, *, story_id: str | None = None, payload: dict | None = None, key: str | None = None) -> dict:
    if kind not in JOB_KINDS:
        raise ValueError(f"unsupported V5 job kind: {kind}")
    job_id = key or (f"{kind}:{story_id}" if story_id else None)
    if job_id:
        existing = store.conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if existing and existing["status"] in {"pending", "running"}:
            return dict(existing)
        if existing and existing["status"] == "done":
            return dict(existing)
        if existing:
            store.conn.execute(
                "UPDATE jobs SET status='pending', available_at=datetime('now'), lease_owner=NULL, lease_until=NULL, updated_at=datetime('now') WHERE id=?",
                (job_id,),
            )
            return dict(store.conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())
    return store.enqueue_job(kind, story_id=story_id, payload=payload, job_id=job_id)


def retry_job(store: NewsroomV5Store, job_id: str, *, error: str, terminal_after: int = 8) -> JobResult:
    row = store.conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if row is None:
        raise KeyError(job_id)
    next_attempt = int(row["attempt_count"] or 0) + 1
    terminal = next_attempt >= max(1, int(terminal_after))
    delay = retry_delay_seconds(next_attempt, seed=str(row["story_id"] or job_id))
    store.retry_job(job_id, error=error, delay_seconds=delay, terminal=terminal)
    return JobResult(job_id=job_id, status="failed" if terminal else "retry", error=error)
