from __future__ import annotations

import os
import sys

from . import runtime_v2 as v2
from . import runtime_v7 as v7
from .dedup_strict import is_strict_duplicate_story

_installed = False


def install_strict_dedup_policy() -> None:
    global _installed
    if _installed:
        return
    v7.install_easy_news_flow()
    # runtime.py resolves this global at fetch time. Replace only semantic dedup;
    # all source, translation, formatting and editorial policies remain unchanged.
    v2.base.is_duplicate_story = is_strict_duplicate_story
    _installed = True


def run(now=None) -> int:
    install_strict_dedup_policy()
    return v7.run(now)


def monitor_loop(poll_seconds: int = 60, session_seconds: int = 240) -> int:
    install_strict_dedup_policy()
    return v7.monitor_loop(poll_seconds=poll_seconds, session_seconds=session_seconds)


def _cli() -> int:
    if "--monitor" in sys.argv[1:]:
        return monitor_loop(
            poll_seconds=int(os.environ.get("POLL_SECONDS", "60")),
            session_seconds=int(os.environ.get("SESSION_SECONDS", "240")),
        )
    return run()


if __name__ == "__main__":
    raise SystemExit(_cli())
