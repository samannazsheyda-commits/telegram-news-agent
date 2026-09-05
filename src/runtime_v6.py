from __future__ import annotations

import os
import sys

from . import runtime_v2 as v2
from . import runtime_v5 as v5

_output_policy_installed = False


def _format_news_with_bottom_flags(item, title_fa: str, summary_fa: str, marker_override=None) -> str:
    text = v2._original_news_format(item, title_fa, summary_fa, marker_override=marker_override)
    if not text:
        return text
    flags = v2._country_flags(item, title_fa, summary_fa)
    if not flags:
        return text

    # Flags belong at the bottom of each news card: after timestamp/source link,
    # immediately before the channel-brand footer.
    footer_markers = ("\n👉🏻 📡 ", "\n📡 ")
    for marker in footer_markers:
        if marker in text:
            return text.replace(marker, f"\n\n{flags}\n{marker}", 1)
    return f"{text}\n\n{flags}"


def install_output_policy() -> None:
    global _output_policy_installed
    if _output_policy_installed:
        return
    v5.install_fresh_x_policy()
    v2._format_news_with_flags = _format_news_with_bottom_flags
    _output_policy_installed = True


def run(now=None) -> int:
    install_output_policy()
    return v5.run(now)


def monitor_loop(poll_seconds: int = 60, session_seconds: int = 240) -> int:
    install_output_policy()
    return v5.monitor_loop(poll_seconds=poll_seconds, session_seconds=session_seconds)


def _cli() -> int:
    if "--monitor" in sys.argv[1:]:
        return monitor_loop(
            poll_seconds=int(os.environ.get("POLL_SECONDS", "60")),
            session_seconds=int(os.environ.get("SESSION_SECONDS", "240")),
        )
    return run()


if __name__ == "__main__":
    raise SystemExit(_cli())
