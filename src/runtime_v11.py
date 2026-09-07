from __future__ import annotations

import sys
import time
from datetime import datetime, timezone

from . import runtime_v10 as v10
from .dedup_strict import is_strict_duplicate_story

base = v10.base
_installed = False
_original_select_top_stories = base.agent._select_top_stories
_PUBLISHED_STATUSES = {"published_manual", "published_auto"}


def _published_history_references() -> list[base.NewsItem]:
    refs: list[base.NewsItem] = []
    for record in base._store.history():
        if record.get("status") not in _PUBLISHED_STATUSES:
            continue
        key = str(record.get("news_key") or "")
        title = str(record.get("original_title") or "")
        if not key or not title:
            continue
        refs.append(
            base.NewsItem(
                key,
                str(record.get("source") or ""),
                title,
                str(record.get("original_summary") or ""),
                str(record.get("source_url") or ""),
                str(record.get("published_at_source") or ""),
            )
        )
    return refs


def _same_source_url(left: base.NewsItem, right: base.NewsItem) -> bool:
    a = (left.link or "").strip().rstrip("/")
    b = (right.link or "").strip().rstrip("/")
    return bool(a and b and a == b)


def _select_top_stories_with_published_history(candidates, references):
    published = _published_history_references()
    fresh = []
    skipped = []
    for item in candidates:
        if any(
            _same_source_url(item, old) or is_strict_duplicate_story(item, old)
            for old in published
        ):
            skipped.append(item)
            print(
                f"NEWS_SUPPRESSED published_history_duplicate source={item.source!r} "
                f"title={item.title!r}"
            )
            continue
        fresh.append(item)

    selected, normal_skipped = _original_select_top_stories(fresh, references)
    return selected, skipped + normal_skipped


def install_production_policies() -> None:
    global _installed
    if _installed:
        return
    v10.install_production_policies()
    base.agent._select_top_stories = _select_top_stories_with_published_history
    _installed = True


def run(now=None) -> int:
    install_production_policies()
    resolved_now = now or datetime.now(timezone.utc)
    v10._retry_todays_false_bundles(resolved_now)
    v10._publish_daily_flagships(resolved_now)
    return v10.v9.run(resolved_now)


def monitor_loop(poll_seconds: int = 60, session_seconds: int = 240) -> int:
    poll_seconds = max(1, int(poll_seconds))
    session_seconds = max(poll_seconds, int(session_seconds))
    started = time.monotonic()
    while True:
        cycle_started = time.monotonic()
        if cycle_started - started >= session_seconds:
            return 0
        rc = run()
        if rc != 0:
            return rc
        cycle_finished = time.monotonic()
        if cycle_finished - started + poll_seconds > session_seconds:
            return 0
        time.sleep(max(0.0, poll_seconds - (cycle_finished - cycle_started)))


def _cli() -> int:
    if "--monitor" in sys.argv[1:]:
        return monitor_loop(
            poll_seconds=int(v10.os.environ.get("POLL_SECONDS", "60")),
            session_seconds=int(v10.os.environ.get("SESSION_SECONDS", "240")),
        )
    return run()


if __name__ == "__main__":
    raise SystemExit(_cli())
