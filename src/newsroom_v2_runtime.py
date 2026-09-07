from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from .editorial_store import LocalEditorialStore
from .event_ledger import EventLedger
from .newsroom_raw_intake import build_raw_fetchers
from .newsroom_v2 import run_cycle
from .panel_live_feed import LiveFeedStore


def _never_publish(_item):
    raise RuntimeError("shadow_mode_publish_blocked")


def _settings() -> dict:
    return {
        "auto_publish": True,
        "freshness_hours": int(os.environ.get("NEWSROOM_V2_FRESHNESS_HOURS", "6")),
        "panel_max_records": int(os.environ.get("NEWSROOM_V2_PANEL_MAX_RECORDS", "500")),
    }


def _run_one(ledger, feed, editorial) -> dict:
    summary = run_cycle(
        build_raw_fetchers(),
        ledger,
        feed,
        editorial,
        _never_publish,
        _settings(),
        datetime.now(timezone.utc),
        shadow=True,
    )
    payload = summary.__dict__.copy()
    payload["telegram_writes"] = 0
    return payload


def run_shadow_cycle() -> dict:
    ledger = EventLedger("data/event_ledger.json")
    feed = LiveFeedStore("data/panel_live_feed.json")
    editorial = LocalEditorialStore("data/editorial_queue.json", "data/editorial_history.json")
    first = _run_one(ledger, feed, editorial)
    second = _run_one(ledger, feed, editorial)
    return {
        "mode": "shadow_double_cycle",
        "first": first,
        "second": second,
        "panel_feed_count": len(feed.records()),
        "telegram_writes": 0,
    }


def main() -> None:
    print(json.dumps(run_shadow_cycle(), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
