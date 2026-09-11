from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from .ai_newsroom import AIConfig
from .editorial_store import LocalEditorialStore
from .event_ledger import EventLedger
from .groq_newsroom_ai import GroqConfig, LocalFirstGroqNewsAI
from .local_semantic_ai import LocalFirstNewsAI
from .newsroom_raw_intake import build_raw_fetchers
from .newsroom_v2 import run_cycle
from .panel_live_feed import LiveFeedStore
from .strict_translation import StrictTelegramNewsroomPublisher


def run_once(
    *,
    shadow: bool,
    fetchers=None,
    publisher=None,
    data_dir: str | Path = "data",
    now: datetime | None = None,
    settings: dict | None = None,
) -> dict:
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    ledger = EventLedger(data_dir / "event_ledger.json")
    feed = LiveFeedStore(data_dir / "panel_live_feed.json")
    editorial = LocalEditorialStore(data_dir / "editorial_queue.json", data_dir / "editorial_history.json")
    fetchers = fetchers if fetchers is not None else build_raw_fetchers()

    hf_config = AIConfig.from_env()
    groq_config = GroqConfig.from_env()
    ai_mode = groq_config.mode
    ai = None
    ai_provider = "none"
    if ai_mode != "off" and groq_config.api_key:
        ai = LocalFirstGroqNewsAI(groq_config)
        ai_provider = "groq"
    elif hf_config.mode != "off" and hf_config.token:
        # Backward-compatible emergency fallback. Production prefers Groq as soon
        # as GROQ_API_KEY is present, so exhausted Hugging Face credits are not
        # touched on the normal path.
        ai = LocalFirstNewsAI(hf_config)
        ai_mode = hf_config.mode
        ai_provider = "huggingface"

    if publisher is None:
        publisher = StrictTelegramNewsroomPublisher(
            os.environ.get("TELEGRAM_BOT_TOKEN", ""),
            os.environ.get("TELEGRAM_CHAT_ID", "@bikhabaar"),
            ai=ai,
            ai_mode=ai_mode,
        )
    effective_settings = {
        "auto_publish": True,
        "freshness_hours": int(os.environ.get("NEWSROOM_V2_PANEL_FRESHNESS_HOURS", "12")),
        "panel_max_records": int(os.environ.get("NEWSROOM_V2_PANEL_MAX_RECORDS", "500")),
        "ai_newsroom_mode": ai_mode,
    }
    if settings:
        effective_settings.update(settings)
    summary = run_cycle(
        fetchers,
        ledger,
        feed,
        editorial,
        publisher,
        effective_settings,
        now or datetime.now(timezone.utc),
        shadow=shadow,
        ai=ai,
    )
    result = summary.__dict__.copy()
    result["mode"] = "shadow" if shadow else "production"
    result["telegram_writes"] = 0 if shadow else summary.published
    result["ai_newsroom_mode"] = ai_mode
    result["ai_available"] = bool(ai is not None and ai.available)
    result["ai_provider"] = ai_provider
    return result


def monitor(*, shadow: bool, poll_seconds: int, session_seconds: int) -> int:
    started = time.monotonic()
    cycles = 0
    while True:
        result = run_once(shadow=shadow)
        cycles += 1
        print(json.dumps({"cycle": cycles, **result}, ensure_ascii=False, sort_keys=True), flush=True)
        if session_seconds <= 0 or time.monotonic() - started >= session_seconds:
            return 0
        remaining = session_seconds - (time.monotonic() - started)
        if remaining <= 0:
            return 0
        time.sleep(min(max(1, poll_seconds), remaining))


def main() -> int:
    parser = argparse.ArgumentParser(description="Newsroom V2 runtime")
    parser.add_argument("--shadow", action="store_true")
    parser.add_argument("--monitor", action="store_true")
    args = parser.parse_args()
    if args.monitor:
        return monitor(
            shadow=args.shadow,
            poll_seconds=max(1, int(os.environ.get("POLL_SECONDS", "2"))),
            session_seconds=max(0, int(os.environ.get("SESSION_SECONDS", "270"))),
        )
    print(json.dumps(run_once(shadow=args.shadow), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
