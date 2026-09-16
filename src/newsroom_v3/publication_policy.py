from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .store import NewsroomV3Store, StoryRecord


TEHRAN = ZoneInfo("Asia/Tehran")


def tehran_day_bounds(now: datetime) -> tuple[datetime, datetime]:
    resolved = now
    if resolved.tzinfo is None:
        resolved = resolved.replace(tzinfo=timezone.utc)
    local = resolved.astimezone(TEHRAN)
    start_local = local.replace(hour=0, minute=0, second=0, microsecond=0)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def count_successful_publications(store: NewsroomV3Store, *, now: datetime) -> int:
    start_utc, end_utc = tehran_day_bounds(now)
    row = store._conn.execute(
        """
        SELECT COUNT(*)
        FROM publish_attempts
        WHERE state='published'
          AND finished_at >= ?
          AND finished_at < ?
        """,
        (start_utc.isoformat(), end_utc.isoformat()),
    ).fetchone()
    return int(row[0] if row else 0)


def list_recent_published(store: NewsroomV3Store, *, limit: int = 25) -> list[StoryRecord]:
    bounded = max(1, min(100, int(limit)))
    rows = store._conn.execute(
        """
        SELECT *
        FROM stories
        WHERE publish_state='published'
          AND telegram_message_id IS NOT NULL
        ORDER BY updated_at DESC, story_id DESC
        LIMIT ?
        """,
        (bounded,),
    ).fetchall()
    return [store._story_from_row(row) for row in rows]
