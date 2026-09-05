from __future__ import annotations

import os
import sys

from . import main as agent
from . import runtime_v3 as v3
from .cars import create_car_telegraph_page, format_car_telegraph_post

_car_policy_installed = False


def install_car_telegraph_policy() -> None:
    global _car_policy_installed
    if _car_policy_installed:
        return

    def _format_car_page(prices, previous=None):
        page_url = create_car_telegraph_page(prices, previous or {})
        return format_car_telegraph_post(page_url, len(prices))

    agent.format_car_prices = _format_car_page
    _car_policy_installed = True


def run(now=None) -> int:
    install_car_telegraph_policy()
    return v3.run(now)


def monitor_loop(poll_seconds: int = 60, session_seconds: int = 240) -> int:
    install_car_telegraph_policy()
    return v3.monitor_loop(poll_seconds=poll_seconds, session_seconds=session_seconds)


def _cli() -> int:
    if "--monitor" in sys.argv[1:]:
        return monitor_loop(
            poll_seconds=int(os.environ.get("POLL_SECONDS", "60")),
            session_seconds=int(os.environ.get("SESSION_SECONDS", "240")),
        )
    return run()


if __name__ == "__main__":
    raise SystemExit(_cli())
