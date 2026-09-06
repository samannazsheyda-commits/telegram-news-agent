from __future__ import annotations

import os
import sys

from . import runtime as base
from . import runtime_v9 as v9
from .fresh_x import media_url_for_item
from .services import send_telegram_photo as _send_telegram_photo

_installed = False


def _send_with_photo_tracking(text: str, bot_token: str, chat_id: str, *args, **kwargs) -> None:
    key = base._pending_auto_key
    item = base._pending_auto_item
    try:
        photo_url = media_url_for_item(item) if item is not None else ""
        if photo_url:
            try:
                _send_telegram_photo(photo_url, text, bot_token, chat_id, *args, **kwargs)
            except Exception as exc:
                print(f"NEWS_PHOTO_FALLBACK key={key!r} error={exc}", file=sys.stderr)
                base._original_send_telegram(text, bot_token, chat_id, *args, **kwargs)
        else:
            base._original_send_telegram(text, bot_token, chat_id, *args, **kwargs)
    except Exception:
        base._pending_auto_key = None
        base._pending_auto_item = None
        raise

    if key:
        try:
            base._store.mark_auto_published(key)
        except Exception as exc:
            print(f"Editorial auto transition error: {exc}", file=sys.stderr)
        if item is not None:
            base._sent_news_items.append(item)
    base._pending_auto_key = None
    base._pending_auto_item = None


def install_photo_news_output() -> None:
    global _installed
    if _installed:
        return
    # base.install_integrations resolves this module global when wiring Telegram.
    base._send_with_tracking = _send_with_photo_tracking
    _installed = True


def run(now=None) -> int:
    install_photo_news_output()
    return v9.run(now)


def monitor_loop(poll_seconds: int = 60, session_seconds: int = 240) -> int:
    install_photo_news_output()
    return v9.monitor_loop(poll_seconds=poll_seconds, session_seconds=session_seconds)


def _cli() -> int:
    if "--monitor" in sys.argv[1:]:
        return monitor_loop(
            poll_seconds=int(os.environ.get("POLL_SECONDS", "60")),
            session_seconds=int(os.environ.get("SESSION_SECONDS", "240")),
        )
    return run()


if __name__ == "__main__":
    raise SystemExit(_cli())
