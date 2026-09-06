from __future__ import annotations

import os
import sys

from . import fresh_x
from . import runtime as base
from . import runtime_v2 as v2
from . import runtime_v9 as v9
from .market_policy import market_summary_day, regular_market_allowed
from .services import send_telegram_photo as _send_telegram_photo
from .x_editorial_quality import rejection_reason

_installed = False
_original_parse_x = fresh_x.parse_fxtwitter_timeline


def _clean_brand_footer() -> list[str]:
    return [
        "",
        f'📡 <a href="{base.news_formatters.CHANNEL_URL}">بی‌خبر</a> ←',
        "مانیتور تحولات ایران",
    ]


def _quality_parse_x(payload, source_name: str, handle: str):
    items = _original_parse_x(payload, source_name, handle)
    accepted = []
    for item in items:
        reason = rejection_reason(getattr(item, "title", ""), source_name)
        if reason:
            print(
                f"NEWS_SUPPRESSED {reason} source={getattr(item, 'source', '')!r} "
                f"title={getattr(item, 'title', '')!r}"
            )
            continue
        accepted.append(item)
    return accepted


def _send_with_photo_tracking(text: str, bot_token: str, chat_id: str, *args, **kwargs) -> None:
    key = base._pending_auto_key
    item = base._pending_auto_item
    try:
        photo_url = fresh_x.media_url_for_item(item) if item is not None else ""
        if photo_url:
            try:
                _send_telegram_photo(photo_url, text, bot_token, chat_id, *args, **kwargs)
            except Exception as exc:
                # A bad/expired X image must never block the underlying news item.
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


def install_production_policies() -> None:
    global _installed
    if _installed:
        return

    # X newsroom quality: suppress context-dependent fragments and report/feature headlines.
    fresh_x.parse_fxtwitter_timeline = _quality_parse_x

    # Telegram news photos: base.install_integrations resolves this global when it wires sending.
    base._send_with_tracking = _send_with_photo_tracking

    # Clean channel footer. runtime_v2 used to reintroduce the pointing-finger emoji.
    v2._brand_footer_with_arrow = _clean_brand_footer
    base.news_formatters._brand_footer = _clean_brand_footer

    # Iran market policy: normal rate cards only during market hours; daily summary at 23:30.
    # Fridays and official Iranian holidays are handled inside market_policy.
    base.agent._market_quiet_hours = lambda now: not regular_market_allowed(now)
    base.agent._market_summary_day = market_summary_day

    _installed = True


def run(now=None) -> int:
    install_production_policies()
    return v9.run(now)


def monitor_loop(poll_seconds: int = 60, session_seconds: int = 240) -> int:
    install_production_policies()
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
