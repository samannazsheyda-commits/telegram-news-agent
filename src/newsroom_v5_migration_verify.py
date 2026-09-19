from __future__ import annotations

from pathlib import Path

from .newsroom_v5_migration import build_migration_projection
from .newsroom_v5_store import NewsroomV5Store


def verify_local_snapshot(root: str | Path, store: NewsroomV5Store) -> dict:
    projection = build_migration_projection(root)
    expected_by_id = {row["id"]: row for row in projection["stories"]}
    actual_rows = {
        row["id"]: dict(row)
        for row in store.conn.execute("SELECT * FROM stories").fetchall()
    }
    conflicts: list[str] = []

    for story_id, expected in expected_by_id.items():
        actual = actual_rows.get(story_id)
        if actual is None:
            conflicts.append(f"missing_story:{story_id}")
            continue
        if actual.get("state") != expected.get("state"):
            conflicts.append(f"state_mismatch:{story_id}:{expected.get('state')}:{actual.get('state')}")

    expected_terminal = {
        row["id"]: row["state"]
        for row in projection["stories"]
        if row.get("state") in {"published", "rejected", "duplicate", "irrelevant"}
    }
    for story_id, state in expected_terminal.items():
        actual = actual_rows.get(story_id)
        if actual and actual.get("state") != state:
            conflicts.append(f"terminal_resurrection:{story_id}:{state}:{actual.get('state')}")

    expected_tombstone_ids = {row["story_id"] for row in projection["tombstones"]}
    actual_tombstone_ids = {
        row[0]
        for row in store.conn.execute("SELECT story_id FROM story_tombstones WHERE story_id IS NOT NULL").fetchall()
    }
    for story_id in sorted(expected_tombstone_ids - actual_tombstone_ids):
        conflicts.append(f"missing_tombstone:{story_id}")

    expected_translated = {row["story_id"] for row in projection["translations"]}
    actual_translated = {
        row[0]
        for row in store.conn.execute("SELECT story_id FROM translations WHERE quality_passed=1 AND LENGTH(TRIM(title_fa))>0").fetchall()
    }
    for story_id in sorted(expected_translated - actual_translated):
        conflicts.append(f"missing_translation:{story_id}")

    expected_sources = {row["id"] for row in projection["sources"]}
    actual_sources = {row[0] for row in store.conn.execute("SELECT id FROM sources").fetchall()}
    for source_id in sorted(expected_sources - actual_sources):
        conflicts.append(f"missing_source:{source_id}")

    active_states = {"received", "translated", "editorial_ready", "review", "publishing"}
    expected_active = {row["id"] for row in projection["stories"] if row.get("state") in active_states}
    actual_active = {row["id"] for row in actual_rows.values() if row.get("state") in active_states}
    if expected_active - actual_active:
        conflicts.append("active_story_loss:" + ",".join(sorted(expected_active - actual_active)))

    expected_published = {row["id"] for row in projection["stories"] if row.get("state") == "published"}
    actual_published = {row["id"] for row in actual_rows.values() if row.get("state") == "published"}
    if expected_published - actual_published:
        conflicts.append("published_identity_loss:" + ",".join(sorted(expected_published - actual_published)))

    return {
        "ok": not conflicts,
        "unresolved_conflicts": conflicts,
        "expected": {
            "stories": len(expected_by_id),
            "active": len(expected_active),
            "published": len(expected_published),
            "rejected_tombstones": len(expected_tombstone_ids),
            "sources": len(expected_sources),
            "persian_ready": len(expected_translated),
        },
        "actual": {
            "stories": len(actual_rows),
            "active": len(actual_active),
            "published": len(actual_published),
            "rejected_tombstones": len(actual_tombstone_ids),
            "sources": len(actual_sources),
            "persian_ready": len(actual_translated),
        },
    }
