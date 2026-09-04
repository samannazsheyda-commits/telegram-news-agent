from __future__ import annotations

from html import escape

from .sources import MarketSnapshot, NewsItem, TruthPost


def _safe(value: str) -> str:
    return escape((value or "").strip(), quote=True)


def format_truth(post: TruthPost, persian_text: str) -> str:
    label = "🔁 بازنشر ترامپ در Truth Social | ایران" if post.is_retruth else "🇺🇸 ترامپ در Truth Social | ایران"
    original = post.text.strip()
    translated = persian_text.strip()
    body = translated
    if translated == original:
        body = f"{translated}\n\nترجمه رایگان موقتاً در دسترس نبود."
    return f"{_safe(label)}\n\n{_safe(body)}\n\n🔗 <a href=\"{_safe(post.url)}\">لینک پست</a>".strip()


def format_news(item: NewsItem, title_fa: str, summary_fa: str) -> str:
    summary_fa = summary_fa.strip()
    if len(summary_fa) > 1200:
        summary_fa = summary_fa[:1197].rstrip() + "…"
    parts = [f"📰 {_safe(item.source)} | ایران", "", _safe(title_fa)]
    if summary_fa and summary_fa != title_fa:
        parts += ["", _safe(summary_fa)]
    if item.link:
        parts += ["", f"منبع: {_safe(item.source)} | <a href=\"{_safe(item.link)}\">لینک خبر</a>"]
    return "\n".join(parts).strip()


def format_market(snapshot: MarketSnapshot) -> str:
    return (
        "💰 قیمت بازار ایران\n\n"
        f"🇺🇸 دلار آزاد: {snapshot.usd_toman:,} تومان\n"
        f"🟡 طلای ۱۸ عیار: {snapshot.gold18_toman:,} تومان / گرم\n\n"
        "منبع: TGJU"
    )
