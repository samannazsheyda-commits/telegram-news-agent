from __future__ import annotations

import os
import sys

from . import runtime as base
from . import runtime_v2 as v2

_policy_installed = False
_original_low_value = base.is_low_value_company_news
_original_recent_duplicate = base._is_recent_duplicate


def _is_x_item(item) -> bool:
    return str(getattr(item, "source", "")).endswith(" / X")


def install_x_publish_all_policy() -> None:
    global _policy_installed
    if _policy_installed:
        return

    def low_value(item):
        if _is_x_item(item):
            return False
        return _original_low_value(item)

    def recent_duplicate(item, references):
        # X posts must follow the same event-level semantic dedup as every other
        # source. Distinct material developments still survive because the
        # underlying duplicate classifier preserves new precise facts/times/sites.
        return _original_recent_duplicate(item, references)

    base.is_low_value_company_news = low_value
    base._is_recent_duplicate = recent_duplicate
    _policy_installed = True


def run(now=None) -> int:
    install_x_publish_all_policy()
    return v2.run(now)


def monitor_loop(poll_seconds: int = 60, session_seconds: int = 240) -> int:
    install_x_publish_all_policy()
    return v2.monitor_loop(poll_seconds=poll_seconds, session_seconds=session_seconds)


def _cli() -> int:
    if "--monitor" in sys.argv[1:]:
        return monitor_loop(
            poll_seconds=int(os.environ.get("POLL_SECONDS", "60")),
            session_seconds=int(os.environ.get("SESSION_SECONDS", "240")),
        )
    return run()


if __name__ == "__main__":
    raise SystemExit(_cli())
