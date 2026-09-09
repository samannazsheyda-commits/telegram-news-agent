from __future__ import annotations

import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from .hormuz import fetch_hormuz_traffic_report, format_hormuz_report
from .services import send_telegram

TEHRAN = ZoneInfo("Asia/Tehran")


def _credentials() -> tuple[str, str]:
    token = str(os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    chat_id = str(os.environ.get("TELEGRAM_CHAT_ID") or "@bikhabaar").strip()
    if not token or not chat_id:
        raise RuntimeError("telegram_credentials_missing")
    return token, chat_id


def publish_hormuz_now() -> bool:
    report_date = datetime.now(timezone.utc).astimezone(TEHRAN).date()
    report = fetch_hormuz_traffic_report(report_date)
    # Never manufacture tanker counts. If no measurable count exists, fail the
    # manual command instead of sending a misleading empty statistics post.
    if report.observed_count is None:
        raise RuntimeError("hormuz_measurable_count_unavailable")
    message = format_hormuz_report(report)
    token, chat_id = _credentials()
    send_telegram(message, token, chat_id)
    return True


def publish_market_now() -> bool:
    # Reuse the live market fetch/format stack rather than the historical
    # one-off hard-coded market post.
    from . import runtime_v9 as v9

    v9.install_persian_only_output()
    snapshot = v9.v7.v2._original_market_fetch()
    now = datetime.now(timezone.utc)
    message = v9.v7.v2.base.agent.format_market(snapshot, now)
    if not str(message or "").strip():
        raise RuntimeError("market_message_empty")
    token, chat_id = _credentials()
    send_telegram(message, token, chat_id)
    return True
