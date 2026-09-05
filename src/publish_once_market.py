from __future__ import annotations

import os
from datetime import datetime, timezone

from .formatters import _brand_footer, _datetime_fa
from .services import load_state, save_state, send_telegram

STATE_PATH = os.environ.get("STATE_PATH", "state.json")
POST_KEY = "manual_market_summary_2026-09-05_2330_simple"


def build_message() -> str:
    now = datetime.now(timezone.utc)
    lines = [
        "📊 <b>جمع‌بندی بازار روز</b>",
        "",
        "🇺🇸 دلار آزاد: <b>۲۲۷٬۲۰۵ تومان</b>  🔺 <b>۲٫۷۸٪</b>",
        "🟡 طلای ۱۸ عیار: <b>۲۳٬۶۷۴٬۴۰۰ تومان / گرم</b>  🔺 <b>۰٫۶۶٪</b>",
        "🛢 نفت برنت: <b>۹۶٫۲۸ دلار / بشکه</b>  ➖ بدون تغییر",
        "🛢 نفت غرب تگزاس: <b>۹۱٫۴۸ دلار / بشکه</b>  ➖ بدون تغییر",
        "",
        f"⏰ {_datetime_fa(now)}",
        '📌 <a href="https://www.tgju.org/">منبع بازار: شبکه اطلاع‌رسانی طلا و ارز</a>',
        '📌 <a href="https://finance.yahoo.com/">منبع نفت: یاهو فایننس</a>',
    ]
    lines += _brand_footer()
    return "\n".join(lines).strip()


def main() -> int:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return 2

    state = load_state(STATE_PATH)
    sent = set(state.get("one_off_posts_sent") or [])
    if POST_KEY in sent:
        print("ONE_OFF_MARKET already_sent")
        return 0

    send_telegram(build_message(), token, chat_id)
    sent.add(POST_KEY)
    state["one_off_posts_sent"] = sorted(sent)
    save_state(state, STATE_PATH)
    print("ONE_OFF_MARKET sent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
