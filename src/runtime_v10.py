from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timezone

from . import fresh_x
from . import runtime as base
from . import runtime_v2 as v2
from . import runtime_v9 as v9
from .market_policy import market_summary_day, regular_market_allowed
from .phones import (
    create_phone_telegraph_page,
    fetch_flagship_phone_prices,
    format_phone_telegraph_post,
    phone_flagships_due,
)
from .services import send_telegram_photo as _send_telegram_photo
from .x_editorial_quality import rejection_reason

_installed = False
_original_parse_x = fresh_x.parse_fxtwitter_timeline
_PHONE_40_REPUBLISH_DATE = "2026-09-06"
_PHONE_40_REPUBLISH_STATE_KEY = "phone_flagships_republish_40_date"
_PHONE_FRESH_REPUBLISH_STATE_KEY = "phone_flagships_fresh_republish_2_date"
_PHONE_PERSIAN_PAGE_STATE_KEY = "phone_flagships_persian_page_republish_date"


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


def _phone_flagships_due_with_one_time_republish(state: dict, now: datetime) -> bool:
    local_date = now.astimezone(base.agent.TEHRAN).date().isoformat()
    if (
        local_date == _PHONE_40_REPUBLISH_DATE
        and state.get(_PHONE_40_REPUBLISH_STATE_KEY) != local_date
    ):
        return True
    return phone_flagships_due(state, now)


def _phone_flagships_due_with_fresh_republish(state: dict, now: datetime) -> bool:
    local_date = now.astimezone(base.agent.TEHRAN).date().isoformat()
    if (
        local_date == _PHONE_40_REPUBLISH_DATE
        and state.get(_PHONE_FRESH_REPUBLISH_STATE_KEY) != local_date
    ):
        state[_PHONE_FRESH_REPUBLISH_STATE_KEY] = local_date
        return True
    return _phone_flagships_due_with_one_time_republish(state, now)


def _phone_flagships_due_with_persian_page_republish(state: dict, now: datetime) -> bool:
    local_date = now.astimezone(base.agent.TEHRAN).date().isoformat()
    if (
        local_date == _PHONE_40_REPUBLISH_DATE
        and state.get(_PHONE_PERSIAN_PAGE_STATE_KEY) != local_date
    ):
        state[_PHONE_PERSIAN_PAGE_STATE_KEY] = local_date
        return True
    return _phone_flagships_due_with_fresh_republish(state, now)


def _publish_daily_flagships(now: datetime) -> None:
    state = base.agent.load_state(base.agent.STATE_PATH)
    if not _phone_flagships_due_with_persian_page_republish(state, now):
        return

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return

    try:
        prices = fetch_flagship_phone_prices()
        page_url = create_phone_telegraph_page(prices, now=now)
        text = format_phone_telegraph_post(page_url, len(prices), now=now)
        v9._send_with_telegraph_preview(text, token, chat_id)
        local_date = now.astimezone(base.agent.TEHRAN).date().isoformat()
        state["phone_flagships_last_sent_date"] = local_date
        state["phone_flagships_last_prices"] = {item.name: item.price_toman for item in prices}
        state["phone_flagships_last_page_url"] = page_url
        if local_date == _PHONE_40_REPUBLISH_DATE:
            state[_PHONE_40_REPUBLISH_STATE_KEY] = local_date
            state[_PHONE_FRESH_REPUBLISH_STATE_KEY] = local_date
            state[_PHONE_PERSIAN_PAGE_STATE_KEY] = local_date
        base.agent.save_state(state, base.agent.STATE_PATH)
    except Exception as exc:
        print(f"Phone flagship price error: {exc}", file=sys.stderr)


def install_production_policies() -> None:
    global _installed
    if _installed:
        return

    fresh_x.parse_fxtwitter_timeline = _quality_parse_x
    base._send_with_tracking = _send_with_photo_tracking
    v2._brand_footer_with_arrow = _clean_brand_footer
    base.news_formatters._brand_footer = _clean_brand_footer
    base.agent._market_quiet_hours = lambda now: not regular_market_allowed(now)
    base.agent._market_summary_day = market_summary_day

    base.agent._weather_noon_due = lambda state, now: False
    base.agent._weather_night_due = lambda state, now: False

    _installed = True


def run(now=None) -> int:
    install_production_policies()
    resolved_now = now or datetime.now(timezone.utc)
    _publish_daily_flagships(resolved_now)
    return v9.run(resolved_now)


def monitor_loop(poll_seconds: int = 60, session_seconds: int = 240) -> int:
    poll_seconds = max(1, int(poll_seconds))
    session_seconds = max(poll_seconds, int(session_seconds))
    started = time.monotonic()
    while True:
        cycle_started = time.monotonic()
        if cycle_started - started >= session_seconds:
            return 0
        rc = run()
        if rc != 0:
            return rc
        cycle_finished = time.monotonic()
        if cycle_finished - started + poll_seconds > session_seconds:
            return 0
        time.sleep(max(0.0, poll_seconds - (cycle_finished - cycle_started)))


def _cli() -> int:
    if "--monitor" in sys.argv[1:]:
        return monitor_loop(
            poll_seconds=int(os.environ.get("POLL_SECONDS", "60")),
            session_seconds=int(os.environ.get("SESSION_SECONDS", "240")),
        )
    return run()


if __name__ == "__main__":
    raise SystemExit(_cli())
