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


def build_hormuz_preview() -> dict:
    """Build a source-backed Hormuz preview without fabricating unavailable counts."""
    report_date = datetime.now(timezone.utc).astimezone(TEHRAN).date()
    report = fetch_hormuz_traffic_report(report_date)
    return {
        "message": format_hormuz_report(report),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "observed_count": report.observed_count,
        "available_for_publish": report.observed_count is not None,
        "source": "Kpler / Vortexa / Reuters",
    }


def publish_hormuz_now() -> bool:
    preview = build_hormuz_preview()
    if not preview.get("available_for_publish"):
        raise RuntimeError("hormuz_measurable_count_unavailable")
    token, chat_id = _credentials()
    send_telegram(preview["message"], token, chat_id)
    return True


def _market_message() -> str:
    from . import runtime_v9 as v9

    v9.install_persian_only_output()
    snapshot = v9.v7.v2._original_market_fetch()
    now = datetime.now(timezone.utc)
    message = v9.v7.v2.base.agent.format_market(snapshot, now)
    if not str(message or "").strip():
        raise RuntimeError("market_message_empty")
    return str(message)


def build_market_preview() -> dict:
    """Build the live market message for panel preview without publishing."""
    return {
        "message": _market_message(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "live market feed",
    }


def publish_market_now() -> bool:
    message = _market_message()
    token, chat_id = _credentials()
    send_telegram(message, token, chat_id)
    return True
