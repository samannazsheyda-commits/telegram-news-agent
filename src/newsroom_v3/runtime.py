from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from ..newsroom_raw_intake import build_raw_fetchers
from .outbox import NewsroomV3PublisherWorker
from .shadow import NewsroomV3ShadowPipeline
from .store import NewsroomV3Store


def _atomic_write_json(path: str | Path, payload: dict) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, target)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def _collect(fetchers) -> tuple[list, int, int]:
    items = []
    sources_ok = 0
    sources_failed = 0
    for fetcher in list(fetchers or []):
        try:
            items.extend(list(fetcher() or []))
            sources_ok += 1
        except Exception:
            sources_failed += 1
    return items, sources_ok, sources_failed


def run_once(
    *,
    data_dir: str | Path = "data",
    fetchers=None,
    now: datetime | None = None,
    shadow: bool = True,
    publisher=None,
    publish_limit: int = 1,
) -> dict:
    """Run one V3 cycle.

    Shadow mode is the default and never invokes a publisher. Non-shadow mode is
    deliberately bounded by `publish_limit` so it can be used as a canary before
    any full cutover.
    """
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)

    directory = Path(data_dir)
    directory.mkdir(parents=True, exist_ok=True)
    store = NewsroomV3Store(directory / "newsroom_v3.sqlite3")
    try:
        resolved_fetchers = build_raw_fetchers() if fetchers is None else fetchers
        items, sources_ok, sources_failed = _collect(resolved_fetchers)
        shadow_result = NewsroomV3ShadowPipeline(store).run(items, now=current_time)

        telegram_writes = 0
        publish_results = []
        if not shadow:
            if publisher is None:
                raise ValueError("publisher is required for V3 canary mode")
            worker = NewsroomV3PublisherWorker(store, publisher)
            for story in store.list_publishable(limit=max(1, int(publish_limit))):
                result = worker.publish_story(story.story_id)
                publish_results.append(result)
                if result.state == "published":
                    telegram_writes += 1

        return {
            "mode": "shadow" if shadow else "canary",
            "sources_ok": sources_ok,
            "sources_failed": sources_failed,
            "processed": shadow_result.processed,
            "ready": shadow_result.ready,
            "waiting": shadow_result.waiting,
            "rejected": shadow_result.rejected,
            "duplicates": shadow_result.duplicates,
            "telegram_writes": telegram_writes,
            "story_ids": list(shadow_result.story_ids),
            "publish_results": [result.__dict__.copy() for result in publish_results],
        }
    finally:
        store.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Newsroom V3 shadow runtime")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--status-file")
    args = parser.parse_args()
    result = run_once(data_dir=args.data_dir, shadow=True)
    if args.status_file:
        _atomic_write_json(args.status_file, result)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
