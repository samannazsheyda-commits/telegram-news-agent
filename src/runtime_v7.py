from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

from . import runtime_v2 as v2
from . import runtime_v6 as v6

_easy_news_flow_installed = False
_original_strict_rejection = v2._strict_rejection_reason
_original_translate = v2.translate_news_to_fa


def _is_x_item(item) -> bool:
    return str(getattr(item, "source", "")).endswith(" / X")


def _published_dt(item):
    return v2.base.agent._published_dt(getattr(item, "published", "")) or datetime.min.replace(tzinfo=timezone.utc)


def _select_one_story(candidates, references):
    """Publish exactly one newest eligible item per monitor cycle.

    Distinct X status IDs are not semantically deduplicated here. Exact reposts are
    still blocked by the existing news_seen/published-key state before selection.
    """
    if not candidates:
        return [], []
    newest = max(candidates, key=_published_dt)
    return [newest], []


def _easy_rejection_reason(item, now):
    # Fresh X ingestion has already applied the single content rule: Iran relevance.
    # Do not reject a distinct X post for age, editorial score, company/news value,
    # wording, or semantic similarity. Exact published keys remain blocked upstream.
    if _is_x_item(item):
        return None
    return _original_strict_rejection(item, now)


def _translate_or_original(value, session=None):
    translated = _original_translate(value, session=session)
    # Translation failure must not silently kill an otherwise valid X post.
    return translated or str(value or "").strip()


def install_easy_news_flow() -> None:
    global _easy_news_flow_installed
    if _easy_news_flow_installed:
        return
    v6.install_output_policy()
    v2._strict_rejection_reason = _easy_rejection_reason
    v2.translate_news_to_fa = _translate_or_original
    v2.base.agent._select_top_stories = _select_one_story
    _easy_news_flow_installed = True


def run(now=None) -> int:
    install_easy_news_flow()
    return v6.run(now)


def monitor_loop(poll_seconds: int = 60, session_seconds: int = 240) -> int:
    install_easy_news_flow()
    return v6.monitor_loop(poll_seconds=poll_seconds, session_seconds=session_seconds)


def _cli() -> int:
    if "--monitor" in sys.argv[1:]:
        return monitor_loop(
            poll_seconds=int(os.environ.get("POLL_SECONDS", "60")),
            session_seconds=int(os.environ.get("SESSION_SECONDS", "240")),
        )
    return run()


if __name__ == "__main__":
    raise SystemExit(_cli())
