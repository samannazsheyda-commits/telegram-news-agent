from __future__ import annotations

import re
from difflib import SequenceMatcher
from email.utils import parsedate_to_datetime
from html import escape
from zoneinfo import ZoneInfo

from .sources import MarketSnapshot, NewsItem, TruthPost

CHANNEL_URL = "https://t.me/bikhabaar"
TEHRAN = ZoneInfo("Asia/Tehran")
PERSIAN_MONTHS = (
    "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند",
)


def _safe(value: str) -> str:
    return escape((value or "").strip(), quote=True)


def _norm(value: str) -> str:
    value = re.sub(r"\s+-\s+[^-]{2,80}$", "", value or "")
    return re.sub(r"[^a-z0-9\u0600-\u06ff]+", " ", value.lower()).strip()


def _ensure_period(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return text
    if text[-1] in ".!؟?…؛:":
        return text
    return text + "."


def _to_persian_digits(value: str) -> str:
    return value.translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


def _gregorian_to_jalali(gy: int, gm: int, gd: int) -> tuple[int, int, int]:
    gdm = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    gy2 = gy + 1 if gm > 2 else gy
    days = 355666 + (365 * gy) + ((gy2 + 3) // 4) - ((gy2 + 99) // 100) + ((gy2 + 399) // 400) + gd + gdm[gm - 1]
    jy = -1595 + (33 * (days // 12053))
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm = 1 + (days // 31)
        jd = 1 + (days % 31)
    else:
        jm = 7 + ((days - 186) // 30)
        jd = 1 + ((days - 186) % 30)
    return jy, jm, jd


def _published_fa(value: str) -> str:
    if not value:
        return ""
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo("UTC"))
        local = dt.astimezone(TEHRAN)
        jy, jm, jd = _gregorian_to_jalali(local.year, local.month, local.day)
        raw = f"{jd} {PERSIAN_MONTHS[jm - 1]} {jy} — {local:%H:%M}"
        return _to_persian_digits(raw)
    except Exception:
        return ""


def _brand_footer() -> list[str]:
    return ["", f'📡 <a href="{CHANNEL_URL}">بی‌خبر</a> ←', "مانیتور تحولات ایران"]


def _topic_emoji(item: NewsItem, title_fa: str, summary_fa: str) -> str:
    text = " ".join([item.title, item.summary, title_fa, summary_fa]).lower()
    groups: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("🚀", ("missile", "rocket", "drone", "موشک", "پهپاد", "راکت")),
        ("⚓", ("hormuz", "tanker", "shipping", "ship", "هرمز", "نفتکش", "کشتیرانی", "کشتی")),
        ("☢️", ("nuclear", "uranium", "natanz", "fordow", "هسته", "اورانیوم", "نطنز", "فردو")),
        ("🤝", ("talks", "negotiation", "ceasefire", "deal", "مذاکر", "آتش بس", "آتش‌بس", "توافق")),
        ("💰", ("sanction", "economy", "economic", "oil price", "تحریم", "اقتصاد", "قیمت نفت")),
        ("🇮🇱", ("israel", "israeli", "netanyahu", "اسرائیل", "نتانیاهو")),
        ("🇺🇸", ("trump", "vance", "rubio", "bessent", "white house", "ترامپ", "ونس", "روبیو", "بِسنت", "کاخ سفید")),
        ("🚨", ("attack", "strike", "war", "bomb", "killed", "حمله", "جنگ", "بمباران", "کشته")),
    )
    for emoji, terms in groups:
        if any(term in text for term in terms):
            return emoji
    return "📰"


def _is_redundant_summary(title: str, summary: str) -> bool:
    t = _norm(title)
    s = _norm(summary)
    if not s or s == t or t in s or s in t:
        return True
    t_tokens = set(t.split())
    s_tokens = set(s.split())
    if t_tokens and s_tokens:
        overlap = len(t_tokens & s_tokens) / max(1, min(len(t_tokens), len(s_tokens)))
        if overlap >= 0.60:
            return True
    return SequenceMatcher(None, t, s).ratio() >= 0.72


def format_truth(post: TruthPost, persian_text: str) -> str:
    label = "🔁 بازنشر ترامپ در Truth Social | ایران" if post.is_retruth else "🇺🇸 ترامپ در Truth Social | ایران"
    body = _ensure_period(persian_text)
    parts = [f"{_safe(label)}", "", _safe(body), "", f'🔗 <a href="{_safe(post.url)}">لینک پست</a>']
    parts += _brand_footer()
    return "\n".join(parts).strip()


def format_news(item: NewsItem, title_fa: str, summary_fa: str) -> str:
    title_fa = _ensure_period(title_fa)
    summary_fa = _ensure_period((summary_fa or "").strip())
    if len(summary_fa) > 900:
        summary_fa = _ensure_period(summary_fa[:897].rstrip(" .…") + "…")

    emoji = _topic_emoji(item, title_fa, summary_fa)
    parts = [f"{emoji} <b>{_safe(title_fa)}</b>"]

    if summary_fa and not _is_redundant_summary(title_fa, summary_fa):
        parts += ["", f"▪️ {_safe(summary_fa)}"]

    published = _published_fa(item.published)
    if published:
        parts += ["", f"🕒 {_safe(published)}"]

    if item.link:
        parts += [f'🔗 منبع: {_safe(item.source)} | <a href="{_safe(item.link)}">لینک خبر</a>']

    parts += _brand_footer()
    return "\n".join(parts).strip()


def _money_line(emoji: str, label: str, value: int | None, suffix: str = "تومان") -> str | None:
    if value is None:
        return None
    return f"{emoji} {label}: {value:,} {suffix}"


def format_market(snapshot: MarketSnapshot) -> str:
    lines: list[str] = ["📊 <b>بازار ایران</b>", ""]
    values = (
        _money_line("🇺🇸", "دلار آزاد", snapshot.usd_toman),
        _money_line("🇪🇺", "یورو", snapshot.eur_toman),
        _money_line("🇬🇧", "پوند", snapshot.gbp_toman),
        _money_line("🇦🇪", "درهم", snapshot.aed_toman),
        _money_line("🇹🇷", "لیر", snapshot.try_toman),
        _money_line("🟡", "طلای ۱۸ عیار", snapshot.gold18_toman, "تومان / گرم"),
        _money_line("🪙", "سکه امامی", snapshot.emami_toman),
        _money_line("🪙", "نیم‌سکه", snapshot.half_toman),
        _money_line("🪙", "ربع‌سکه", snapshot.quarter_toman),
        _money_line("🪙", "سکه گرمی", snapshot.gram_coin_toman),
        None if snapshot.bitcoin_usd is None else f"₿ بیت‌کوین: ${snapshot.bitcoin_usd:,.2f}",
        _money_line("💵", "تتر", snapshot.tether_toman),
    )
    lines.extend(line for line in values if line)
    lines += ["", "🔗 منبع: TGJU"]
    return "\n".join(lines).strip()
