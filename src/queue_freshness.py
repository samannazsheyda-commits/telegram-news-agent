from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .editorial_store import LocalEditorialStore
from . import runtime_v13

SETTINGS_PATH = Path("data/newsroom_settings.json")


def load_settings(path: str | Path = SETTINGS_PATH) -> dict:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def freshness_hours(settings: dict) -> int:
    try:
        return max(1, min(6, int(settings.get("freshness_hours") or 2)))
    except (TypeError, ValueError):
        return 2


def expire_stale_queue(
    now: datetime | None = None,
    *,
    settings: dict | None = None,
    store: LocalEditorialStore | None = None,
) -> int:
    resolved_now = now or datetime.now(timezone.utc)
    settings = settings or load_settings()
    store = store or LocalEditorialStore()
    cutoff = resolved_now - timedelta(hours=freshness_hours(settings))
    moved = 0

    for record in list(store.queue()):
        if str(record.get("status") or "pending") != "pending":
            continue
        published = runtime_v13.base.agent._published_dt(str(record.get("published_at_source") or ""))
        if published is None or published >= cutoff:
            continue
        item_id = str(record.get("id") or "").strip()
        if not item_id:
            continue
        try:
            store.move_to_history(item_id, status="superseded")
            moved += 1
        except KeyError:
            continue
    return moved


def main() -> None:
    moved = expire_stale_queue()
    print(f"STALE_QUEUE_EXPIRED moved={moved}")


if __name__ == "__main__":
    main()
