from __future__ import annotations

import os
import sys

from . import runtime_v2 as v2
from . import runtime_v4 as v4
from .fresh_x import fetch_fresh_x_news_items

_fresh_x_installed = False


def install_fresh_x_policy() -> None:
    global _fresh_x_installed
    if _fresh_x_installed:
        return

    # runtime_v2 resolves this global at scan time, so replacing it here makes the
    # entire existing editorial/output stack consume fresh canonical X statuses.
    v2.fetch_builtin_x_news_items = fetch_fresh_x_news_items

    # Every X item follows the same minimal acceptance rule: valid timestamp,
    # same Tehran-local day, and Iran relevance. Special accounts are no longer
    # routed through the older commentary/company filters.
    v2._is_newsroom_x = lambda item: str(getattr(item, "source", "")).endswith(" / X")

    # Barak Ravid, Araghchi, Mohsen Rezaei, Sepah News and TankerTrackers are now
    # in the fresh timeline registry. Keep only the non-X NOTAM utility here and
    # stop the old custom-X path from re-introducing stale Google-indexed posts.
    v2._PRESERVED_SPECIAL_SOURCES = {"NOTAM / Airspace"}
    v2._original_custom_fetch = lambda: []

    _fresh_x_installed = True


def run(now=None) -> int:
    install_fresh_x_policy()
    return v4.run(now)


def monitor_loop(poll_seconds: int = 60, session_seconds: int = 240) -> int:
    install_fresh_x_policy()
    return v4.monitor_loop(poll_seconds=poll_seconds, session_seconds=session_seconds)


def _cli() -> int:
    if "--monitor" in sys.argv[1:]:
        return monitor_loop(
            poll_seconds=int(os.environ.get("POLL_SECONDS", "60")),
            session_seconds=int(os.environ.get("SESSION_SECONDS", "240")),
        )
    return run()


if __name__ == "__main__":
    raise SystemExit(_cli())
