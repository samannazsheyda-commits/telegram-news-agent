from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from .fresh_x import fetch_profile_timeline
from .managed_sources import managed_source_rows
from .sources import NewsItem


def fetch_managed_x_realtime(*, session=requests) -> list[NewsItem]:
    """Fetch all enabled X accounts concurrently using direct profile timelines."""
    sources = []
    for row in managed_source_rows():
        if row.get("kind") != "x" or not row.get("active", True):
            continue
        handle = str(row.get("handle") or "").strip()
        if not handle:
            continue
        sources.append({"name": str(row.get("name") or handle.lstrip("@")), "handle": handle})

    merged: dict[str, NewsItem] = {}
    failures = 0
    if not sources:
        return []
    with ThreadPoolExecutor(max_workers=min(8, len(sources)), thread_name_prefix="bikhabar-x") as pool:
        futures = {pool.submit(fetch_profile_timeline, source, session=session): source for source in sources}
        for future in as_completed(futures):
            source = futures[future]
            try:
                items = future.result() or []
            except Exception as exc:
                failures += 1
                print(f"DIRECT_X_FAILED handle={source['handle']!r} error={type(exc).__name__}:{exc}", flush=True)
                continue
            for item in items:
                merged.setdefault(item.key, item)
    print(f"DIRECT_X_SCAN sources={len(sources)} failures={failures} items={len(merged)}", flush=True)
    return list(merged.values())
