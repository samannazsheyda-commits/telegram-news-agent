from __future__ import annotations

import re
from html import escape

from .sources import MarketSnapshot, NewsItem, TruthPost

CHANNEL_URL = "https://t.me/bikhabaar"


def _safe(value: str) -> str:
    return escape((value or "").strip(), quote=True)


def _norm(value: str) -> str:
    value = re.sub(r"\s+-\s+[^-]{2,80}$", "", value or "")
    return re.sub(r"[^a-z0-9\u0600-\u06ff]+", " ", value.lower()).strip()


def _brand_footer() -> list[str]:
    return ["", f'<a href="{CHANNEL_URL}">بی‌خبر</a>', "رسانه خبر ایران"]


def format_truth(post: TruthPost, persian_text: str) -> str:
    label = "🔁 بازنشر ترامپ در Truth Social | ایران" if post.is_retruth else "🇺🇸 ترامپ در Truth Social | ایران"
    parts = [f"{_safe(label)}", "", _safe(persian_text), "", f'🔗 <a href="{_safe(post.url)}">لینک پست</a>']
    parts += _brand_footer()
    return "\n".join(parts).strip()


def format_news(item: NewsItem, title_fa: str, summary_fa: str) -> str:
    summary_fa = (summary_fa or "").strip()
    if len(summary_fa) > 900:
        summary_fa = summary_fa[:897].rstrip() + "…"

    title_norm = _norm(title_fa)
    summary_norm = _norm(summary_fa)
    show_summary = bool(summary_norm and summary_norm != title_norm and title_norm not in summary_norm and summary_norm not in title_norm)

    parts = [f"📰 {_safe(item.source)} | ایران", "", _safe(title_fa)]
    if show_summary:
        parts += ["", _safe(summary_fa)]
    if item.link:
        parts += ["", f"منبع: {_safe(item.source)} | <a href=\"{_safe(item.link)}\">لینک خبر</a>"]
    parts += _brand_footer()
    return "\n".join(parts).strip()


def format_market(snapshot: MarketSnapshot) -> str:
    return (
        "💰 قیمت بازار ایران\n\n"
        f"🇺🇸 دلار آزاد: {snapshot.usd_toman:,} تومان\n"
        f"🟡 طلای ۱۸ عیار: {snapshot.gold18_toman:,} تومان / گرم\n\n"
        "منبع: TGJU"
    )
