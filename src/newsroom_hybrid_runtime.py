from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone

from . import runtime_v13 as v13
from .newsroom_runtime_v2 import run_once as run_v2_once


def run_ancillary_cycle(now: datetime) -> int:
    """Run legacy non-news features while preventing legacy news/Truth publication."""
    v13.install_production_policies()
    v13.expire_previous_day_queue(now)
    original_news = v13.base.agent.fetch_news_items
    original_truth = v13.base.agent.fetch_truth_posts
    try:
        v13.base.agent.fetch_news_items = lambda: []
        v13.base.agent.fetch_truth_posts = lambda: []
        v13._publish_phone_once_per_day(now)
        return int(v13.v12.v11.v10.v9.v8.run(now) or 0)
    finally:
        v13.base.agent.fetch_news_items = original_news
        v13.base.agent.fetch_truth_posts = original_truth


def run_cycle(*, shadow: bool, now: datetime | None = None) -> dict:
    resolved_now = now or datetime.now(timezone.utc)
    ancillary_rc = run_ancillary_cycle(resolved_now)
    if ancillary_rc != 0:
        return {"rc": ancillary_rc, "mode": "shadow" if shadow else "production", "published": 0, "telegram_writes": 0}
    result = run_v2_once(shadow=shadow, now=resolved_now)
    return {"rc": 0, **result}


def monitor(*, shadow: bool, poll_seconds: int, session_seconds: int) -> int:
    poll_seconds = max(1, int(poll_seconds))
    session_seconds = max(poll_seconds, int(session_seconds))
    started = time.monotonic()
    cycle = 0
    while True:
        cycle_started = time.monotonic()
        if cycle_started - started >= session_seconds:
            return 0
        result = run_cycle(shadow=shadow)
        cycle += 1
        print(json.dumps({"cycle": cycle, **result}, ensure_ascii=False, sort_keys=True), flush=True)
        if int(result.get("rc") or 0) != 0:
            return int(result["rc"])
        cycle_finished = time.monotonic()
        if cycle_finished - started + poll_seconds > session_seconds:
            return 0
        time.sleep(max(0.0, poll_seconds - (cycle_finished - cycle_started)))


def main() -> int:
    parser = argparse.ArgumentParser(description="Hybrid production runtime: V13 ancillary services + Newsroom V2 news")
    parser.add_argument("--shadow", action="store_true")
    parser.add_argument("--monitor", action="store_true")
    args = parser.parse_args()
    if args.monitor:
        return monitor(
            shadow=args.shadow,
            poll_seconds=int(os.environ.get("POLL_SECONDS", "60")),
            session_seconds=int(os.environ.get("SESSION_SECONDS", "270")),
        )
    print(json.dumps(run_cycle(shadow=args.shadow), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
