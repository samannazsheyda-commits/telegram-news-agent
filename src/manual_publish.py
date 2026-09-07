from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from .editorial_store import LocalEditorialStore, ReviewItem
from .formatters import CHANNEL_URL, _published_fa, _safe, _story_marker
from .services import load_state, save_state, send_telegram
from .sources import NewsItem


_SOURCE_OVERRIDES = {
    "Tabz Live": "تبز لایو",
    "Reuters": "رویترز",
    "Bloomberg": "بلومبرگ",
    "Times of Israel": "تایمز اسرائیل",
    "The Times of Israel": "تایمز اسرائیل",
    "Associated Press": "آسوشیتدپرس",
    "AP": "آسوشیتدپرس",
    "AFP": "خبرگزاری فرانسه",
    "BBC": "بی‌بی‌سی",
    "BBC World": "بی‌بی‌سی ورلد",
    "CNN": "سی‌ان‌ان",
    "France 24": "فرانس ۲۴",
    "Al Jazeera English": "الجزیره انگلیسی",
    "Al Arabiya English": "العربیه انگلیسی",
    "The New York Times": "نیویورک تایمز",
    "New York Times": "نیویورک تایمز",
    "Financial Times": "فایننشال تایمز",
    "Sky News": "اسکای نیوز",
    "NBC News": "ان‌بی‌سی نیوز",
    "CBS News": "سی‌بی‌اس نیوز",
    "ABC News": "ای‌بی‌سی نیوز",
    "Fox News": "فاکس نیوز",
    "DW News": "دویچه‌وله",
    "The Guardian": "گاردین",
    "Washington Post": "واشنگتن پست",
    "Wall Street Journal": "وال‌استریت ژورنال",
    "Haaretz": "هاآرتص",
    "Axios": "اکسیوس",
    "Jerusalem Post": "جروزالم پست",
    "Israel Hayom": "اسرائیل هیوم",
    "CENTCOM": "سنتکام",
    "White House": "کاخ سفید",
    "US Treasury": "وزارت خزانه‌داری آمریکا",
    "US State Department": "وزارت خارجه آمریکا",
    "State Department": "وزارت خارجه آمریکا",
    "TankerTrackers": "تنکر ترکرز",
    "NOTAM": "نوتام",
}

_COUNTRY_FLAGS = (
    (("ایران", "iran", "iranian"), "🇮🇷"),
    (("امارات", "uae", "united arab emirates", "emirati"), "🇦🇪"),
    (("آمریکا", "ایالات متحده", "united states", "u.s.", " us ", "american"), "🇺🇸"),
    (("اسرائیل", "israel", "israeli"), "🇮🇱"),
    (("عربستان", "saudi", "saudi arabia"), "🇸🇦"),
    (("قطر", "qatar"), "🇶🇦"),
    (("عمان", "oman"), "🇴🇲"),
    (("بحرین", "bahrain"), "🇧🇭"),
    (("عراق", "iraq", "iraqi"), "🇮🇶"),
    (("سوریه", "syria", "syrian"), "🇸🇾"),
    (("لبنان", "lebanon", "lebanese"), "🇱🇧"),
    (("یمن", "yemen", "yemeni"), "🇾🇪"),
    (("ترکیه", "turkey", "türkiye", "turkish"), "🇹🇷"),
    (("پاکستان", "pakistan", "pakistani"), "🇵🇰"),
    (("افغانستان", "afghanistan", "afghan"), "🇦🇫"),
    (("روسیه", "russia", "russian"), "🇷🇺"),
    (("چین", "china", "chinese"), "🇨🇳"),
    (("کره جنوبی", "south korea", "korean"), "🇰🇷"),
)

_IMPACT_WORDS = (
    "حمله", "حملات", "موشک", "پهپاد", "انفجار", "بمباران", "درگیری", "شلیک",
    "attack", "attacks", "strike", "missile", "drone", "explosion", "blast", "bombing", "fired",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _has_persian(value: str) -> bool:
    return bool(re.search(r"[\u0600-\u06ff]", value or ""))


def _has_latin(value: str) -> bool:
    return bool(re.search(r"[A-Za-z]", value or ""))


def _clean_source(source: str) -> str:
    value = (source or "").strip()
    value = re.sub(r"\s*/\s*Telegram\s*$", "", value, flags=re.IGNORECASE).strip()
    is_x = bool(re.search(r"\s*/\s*X\s*$", value, flags=re.IGNORECASE))
    if is_x:
        value = re.sub(r"\s*/\s*X\s*$", "", value, flags=re.IGNORECASE).strip()
    value = _SOURCE_OVERRIDES.get(value, value)
    if _has_latin(value):
        value = "منبع خبری"
    return f"{value} / ایکس" if is_x else value


def _clean_manual_body(body_fa: str) -> str:
    text = (body_fa or "").strip()
    if not text or not _has_persian(text):
        return ""
    return text


def _ensure_period(text: str) -> str:
    value = (text or "").strip()
    if not value or value[-1] in ".!؟?…؛:":
        return value
    return value + "."


def _country_flags(text: str) -> list[str]:
    lowered = f" {(text or '').lower()} "
    flags: list[str] = []
    for keywords, flag in _COUNTRY_FLAGS:
        if any(keyword.lower() in lowered for keyword in keywords):
            flags.append(flag)
    return flags


def _status_line(news: NewsItem, title_fa: str) -> str:
    context = f"{title_fa} {news.title} {news.summary}"
    marker = _story_marker(news)
    flags = _country_flags(context)
    impact = "💥" if any(word in context.lower() for word in _IMPACT_WORDS) else ""
    return " ".join(part for part in (marker, *flags, impact) if part)


def _message_for(item: ReviewItem, title_fa: str, body_fa: str) -> str:
    news = NewsItem(
        key=item.news_key,
        source=_clean_source(item.source),
        title=item.original_title,
        summary=item.original_summary,
        link=item.source_url,
        published=item.published_at_source,
    )
    title = _ensure_period(title_fa)
    parts = [f"<b>{_safe(news.source)}: {_safe(title)}</b>"]
    published = _published_fa(news.published)
    if published:
        parts += ["", f"⏰ {_safe(published)}"]
    if news.link:
        parts += [f'📌 <a href="{_safe(news.link)}">لینک منبع خبر</a>']
    parts += ["", f'📡 <a href="{CHANNEL_URL}">بی‌خبر</a> ←', "مانیتور تحولات ایران", "", _status_line(news, title)]
    return "\n".join(parts).strip()


def _mark_seen(news_key: str, state_path: str | Path | None) -> None:
    if state_path is None:
        return
    state = load_state(state_path)
    seen = list(state.get("news_seen") or [])
    seen = [key for key in seen if key != news_key]
    seen.insert(0, news_key)
    state["news_seen"] = seen[:500]
    save_state(state, state_path)


def publish_review_item(
    store: LocalEditorialStore,
    item_id: str,
    title_fa: str,
    body_fa: str,
    token: str,
    chat_id: str,
    *,
    state_path: str | Path | None = None,
    sender=send_telegram,
) -> ReviewItem:
    item = store.get_pending(item_id)
    if item is None:
        raise ValueError("not_pending")
    title_fa = (title_fa or "").strip()
    body_fa = (body_fa or "").strip()
    if not title_fa:
        raise ValueError("headline_required")
    if not _has_persian(title_fa):
        raise ValueError("persian_headline_required")
    if not item.source or not item.source_url:
        raise ValueError("source_required")
    message = _message_for(item, title_fa, body_fa)
    if not message:
        raise ValueError("invalid_message")

    sender(message, token, chat_id)
    _mark_seen(item.news_key, state_path)
    return store.move_to_history(
        item.id,
        status="published_manual",
        final_persian_title=title_fa,
        final_persian_body=_clean_manual_body(body_fa),
        decision_at=_now(),
    )


def reject_review_item(store: LocalEditorialStore, item_id: str) -> ReviewItem:
    item = store.get_pending(item_id)
    if item is None:
        raise ValueError("not_pending")
    return store.move_to_history(item.id, status="rejected_manual", decision_at=_now())
