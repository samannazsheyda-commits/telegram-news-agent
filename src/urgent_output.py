from __future__ import annotations

from .final_output import finalize_telegram_message


def normalize_urgent_message(value: str) -> str:
    """Route emergency output through the same final Telegram formatter guard."""
    return finalize_telegram_message(value)
