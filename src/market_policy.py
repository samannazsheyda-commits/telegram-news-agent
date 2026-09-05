from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

TEHRAN = ZoneInfo("Asia/Tehran")


def is_iran_market_holiday(now: datetime) -> bool:
    local = now.astimezone(TEHRAN)
    # Friday is the regular weekly market holiday in Iran.
    if local.weekday() == 4:
        return True
    try:
        import holidays

        iran_holidays = holidays.country_holidays("IR", years=[local.year])
        return local.date() in iran_holidays
    except Exception:
        # If the holiday calendar is temporarily unavailable, keep the
        # deterministic weekly Friday closure rather than blocking weekdays.
        return False


def regular_market_allowed(now: datetime, *, is_holiday: bool | None = None) -> bool:
    local = now.astimezone(TEHRAN)
    holiday = is_iran_market_holiday(now) if is_holiday is None else bool(is_holiday)
    if holiday:
        return False
    # Normal market cards: 08:00 through the 22:00 hour. After that the
    # channel stays quiet until the 23:00 daily recap.
    return 8 <= local.hour <= 22


def market_summary_day(state: dict, now: datetime, *, is_holiday: bool | None = None) -> str | None:
    local = now.astimezone(TEHRAN)
    holiday = is_iran_market_holiday(now) if is_holiday is None else bool(is_holiday)
    if holiday or local.hour != 23:
        return None
    day = local.date().isoformat()
    data = state.get("market_day_prices") or {}
    if data.get("date") != day:
        return None
    if state.get("market_daily_summary_last_date") == day:
        return None
    required = ("first_usd", "last_usd", "first_gold", "last_gold")
    return day if all(data.get(key) is not None for key in required) else None
