from __future__ import annotations

import re
from datetime import datetime, timezone
from difflib import SequenceMatcher
from email.utils import parsedate_to_datetime
from html import escape
from zoneinfo import ZoneInfo

from .sources import MarketSnapshot, NewsItem, TruthPost

CHANNEL_URL = "https://t.me/bikhabaar"
TEHRAN = ZoneInfo("Asia/Tehran")
PERSIAN_MONTHS = ("فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند")
SOURCE_FA = {
    "Axios": "اکسیوس",
    "Al Jazeera": "الجزیره",
    "Channel 14": "کانال ۱۴ اسرائیل",
    "Reuters": "رویترز",
    "Associated Press": "آسوشیتدپرس",
    "BBC News": "بی‌بی‌سی",
    "CNN": "سی‌ان‌ان",
    "Financial Times": "فایننشال تایمز",
    "The New York Times": "نیویورک تایمز",
    "France 24": "فرانس ۲۴",
    "DW": "دویچه‌وله",
    "Times of Israel": "تایمز آو اسرائیل",
    "Haaretz": "هاآرتص",
    "Donald Trump / Truth Social": "ترامپ / تروث سوشال",
    "Barak Ravid / X": "باراک راوید",
    "Abbas Araghchi / X": "عباس عراقچی",
    "Mohsen Rezaei / X": "محسن رضایی",
    "TankerTrackers": "تانکرترکرز",
    "NOTAM / Airspace": "نوتام / حریم هوایی",
}


def _safe(value: str) -> str:
    return escape((value or "").strip(), quote=True)


def _norm(value: str) -> str:
    value = re.sub(r"\s+-\s+[^-]{2,80}$", "", value or "")
    return re.sub(r"[^a-z0-9\u0600-\u06ff]+", " ", value.lower()).strip()


def _ensure_period(value: str) -> str:
    text = (value or "").strip()
    if not text or text[-1] in ".!؟?…؛:":
        return text
    return text + "."


def _to_persian_digits(value: str) -> str:
    return value.translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


def _gregorian_to_jalali(gy: int, gm: int, gd: int) -> tuple[int, int, int]:
    gdm = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    gy2 = gy + 1 if gm > 2 else gy
    days = 355666 + 365 * gy + ((gy2 + 3) // 4) - ((gy2 + 99) // 100) + ((gy2 + 399) // 400) + gd + gdm[gm - 1]
    jy = -1595 + 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm, jd = 1 + days // 31, 1 + days % 31
    else:
        jm, jd = 7 + (days - 186) // 30, 1 + (days - 186) % 30
    return jy, jm, jd


def _datetime_fa(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    local = dt.astimezone(TEHRAN)
    jy, jm, jd = _gregorian_to_jalali(local.year, local.month, local.day)
    return _to_persian_digits(f"{jd} {PERSIAN_MONTHS[jm - 1]} {jy} — {local:%H:%M}")


def _published_fa(value: str) -> str:
    if not value:
        return ""
    try:
        return _datetime_fa(parsedate_to_datetime(value))
    except Exception:
        return ""


def _brand_footer() -> list[str]:
    return ["", f'📡 <a href="{CHANNEL_URL}">بی‌خبر</a> ←', "مانیتور تحولات ایران"]


def _is_redundant_summary(title: str, summary: str) -> bool:
    t, s = _norm(title), _norm(summary)
    if not s or s == t or t in s or s in t:
        return True
    a, b = set(t.split()), set(s.split())
    if a and b and len(a & b) / max(1, min(len(a), len(b))) >= 0.60:
        return True
    return SequenceMatcher(None, t, s).ratio() >= 0.72


def _red_story_marker(item: NewsItem) -> str:
    text = f"{item.title} {item.summary}".lower()
    if any(x in text for x in ("missile", "drone", "attack", "strike", "explosion", "blast", "bombing", "killed", "seized", "sinking", "موشک", "پهپاد", "حمله", "انفجار", "بمباران", "توقیف", "غرق")):
        return "🛑"
    if any(x in text for x in ("notam", "airspace closed", "flight ban", "flights cancelled", "نوتام", "حریم هوایی بسته", "لغو پرواز")):
        return "🔺"
    return "🟥"


def _story_marker(item: NewsItem) -> str:
    text = f"{item.title} {item.summary}".lower()
    if any(x in text for x in ("missile", "drone", "attack", "strike", "explosion", "blast", "bombing", "killed", "seized", "sinking", "موشک", "پهپاد", "حمله", "انفجار", "بمباران", "توقیف", "غرق")):
        return "🛑"
    if any(x in text for x in ("notam", "airspace closed", "flight ban", "flights cancelled", "نوتام", "حریم هوایی بسته", "لغو پرواز")):
        return "🔺"
    if any(x in text for x in ("breaking", "urgent", "alert", "فوری", "هشدار")):
        return "🟥"
    return "⚪️"


def _detail_marker(marker: str) -> str:
    return "▫️" if marker == "⚪️" else "🟥"


def _source_label(source: str) -> str:
    return SOURCE_FA.get(source, source)


def format_truth(post: TruthPost, persian_text: str) -> str:
    label = "▫️ بازنشر ترامپ در Truth Social | ایران" if post.is_retruth else "⚪️ ترامپ در Truth Social | ایران"
    parts = [_safe(label), "", f"<b>{_safe(_ensure_period(persian_text))}</b>", "", f'📌 <a href="{_safe(post.url)}">لینک پست</a>']
    parts += _brand_footer()
    return "\n".join(parts).strip()


def format_news(item: NewsItem, title_fa: str, summary_fa: str, marker_override: str | None = None) -> str:
    title_fa = _ensure_period(title_fa)
    summary_fa = _ensure_period((summary_fa or "").strip())
    if len(summary_fa) > 900:
        summary_fa = _ensure_period(summary_fa[:897].rstrip(" .…") + "…")
    marker = marker_override or _story_marker(item)
    source = _source_label(item.source)
    parts = [f"{marker} <b>{_safe(source)}: {_safe(title_fa)}</b>"]
    if summary_fa and not _is_redundant_summary(title_fa, summary_fa):
        parts += ["", f"{_detail_marker(marker)} <b>{_safe(summary_fa)}</b>"]
    published = _published_fa(item.published)
    if published:
        parts += ["", f"⏰ {_safe(published)}"]
    if item.link:
        parts += [f'📌 <a href="{_safe(item.link)}">لینک منبع خبر</a>']
    parts += _brand_footer()
    return "\n".join(parts).strip()


def _money_line(emoji: str, label: str, value: int | None, suffix: str = "تومان") -> str | None:
    return None if value is None else f"{emoji} {label}: {value:,} {suffix}"


def format_market(snapshot: MarketSnapshot, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    lines = ["📊 <b>بازار ایران</b>", ""]
    values = (
        _money_line("🇺🇸", "دلار آزاد", snapshot.usd_toman), _money_line("🇪🇺", "یورو", snapshot.eur_toman),
        _money_line("🇬🇧", "پوند", snapshot.gbp_toman), _money_line("🇦🇪", "درهم", snapshot.aed_toman),
        _money_line("🇹🇷", "لیر", snapshot.try_toman), _money_line("🟡", "طلای ۱۸ عیار", snapshot.gold18_toman, "تومان / گرم"),
        _money_line("🪙", "سکه امامی", snapshot.emami_toman), _money_line("🪙", "نیم‌سکه", snapshot.half_toman),
        _money_line("🪙", "ربع‌سکه", snapshot.quarter_toman), _money_line("🪙", "سکه گرمی", snapshot.gram_coin_toman),
        None if snapshot.bitcoin_usd is None else f"₿ بیت‌کوین: ${snapshot.bitcoin_usd:,.2f}", _money_line("💵", "تتر", snapshot.tether_toman),
    )
    lines.extend(x for x in values if x)
    lines += ["", f"⏰ {_datetime_fa(now)}", "🔗 منبع: TGJU"]
    return "\n".join(lines).strip()
