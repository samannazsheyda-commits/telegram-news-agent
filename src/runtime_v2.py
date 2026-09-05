from __future__ import annotations

import re
import sys
from datetime import datetime

from . import runtime as base
from . import services
from . import sources
from .news_context import fetch_news_detail_enriched
from .newsroom_x import fetch_builtin_x_news_items, is_monitored_x_topic
from .oil import OilSnapshot, fetch_oil_snapshot, format_oil_lines


_original_generic_fetch = base._original_fetch_news_items
_original_custom_fetch = base.fetch_custom_news_items
_original_priority_score = base._priority_event_priority
_original_market_fetch = base.agent.fetch_market_snapshot
_original_market_format = base.agent.format_market
_original_market_daily_format = base.agent.format_market_daily_summary
_original_record_market = base.agent._record_market_snapshot
_original_news_format = base._original_format_news
_x_news_keys: set[str] = set()
_market_hooks_installed = False

_X_SOURCE_FA = {
    "Reuters / X": "رویترز / ایکس", "Associated Press / X": "آسوشیتدپرس / ایکس",
    "AFP / X": "خبرگزاری فرانسه / ایکس", "BBC World / X": "بی‌بی‌سی ورلد / ایکس",
    "CNN / X": "سی‌ان‌ان / ایکس", "France 24 / X": "فرانس ۲۴ / ایکس",
    "Al Jazeera English / X": "الجزیره انگلیسی / ایکس", "Al Arabiya English / X": "العربیه انگلیسی / ایکس",
    "The New York Times / X": "نیویورک تایمز / ایکس", "NYT World / X": "نیویورک تایمز جهان / ایکس",
    "Bloomberg / X": "بلومبرگ / ایکس", "Financial Times / X": "فایننشال تایمز / ایکس",
    "Sky News / X": "اسکای نیوز / ایکس", "NBC News / X": "ان‌بی‌سی نیوز / ایکس",
    "CBS News / X": "سی‌بی‌اس نیوز / ایکس", "ABC News / X": "ای‌بی‌سی نیوز / ایکس",
    "Fox News / X": "فاکس نیوز / ایکس", "DW News / X": "دویچه‌وله / ایکس",
    "The Guardian / X": "گاردین / ایکس", "Washington Post / X": "واشنگتن پست / ایکس",
    "Wall Street Journal / X": "وال‌استریت ژورنال / ایکس", "Times of Israel / X": "تایمز اسرائیل / ایکس",
    "Haaretz / X": "هاآرتص / ایکس", "Axios / X": "اکسیوس / ایکس",
    "Jerusalem Post / X": "جروزالم پست / ایکس", "Israel Hayom / X": "اسرائیل هیوم / ایکس",
    "Benjamin Netanyahu / X": "بنیامین نتانیاهو / ایکس", "Israel Katz / X": "اسرائیل کاتز / ایکس",
    "KAN 11 / X": "کانال ۱۱ اسرائیل / ایکس", "N12 / X": "کانال ۱۲ اسرائیل / ایکس",
    "Channel 13 / X": "کانال ۱۳ اسرائیل / ایکس", "Channel 14 / X": "کانال ۱۴ اسرائیل / ایکس",
    "IDF / X": "ارتش اسرائیل / ایکس", "CENTCOM / X": "سنتکام / ایکس",
    "US Treasury / X": "وزارت خزانه‌داری آمریکا / ایکس", "Scott Bessent / X": "اسکات بسنت / ایکس",
    "US Secretary of Defense / X": "وزیر دفاع آمریکا / ایکس", "US State Department / X": "وزارت خارجه آمریکا / ایکس",
    "State Department Spokesperson / X": "سخنگوی وزارت خارجه آمریکا / ایکس", "White House / X": "کاخ سفید / ایکس",
    "Mark Levin / X": "مارک لوین / ایکس", "Jason Brodsky / X": "جیسون برادسکی / ایکس",
    "Tasnim Persian / X": "تسنیم / ایکس", "Tasnim English / X": "تسنیم انگلیسی / ایکس",
}
base.news_formatters.SOURCE_FA.update(_X_SOURCE_FA)

_PRESERVED_SPECIAL_SOURCES = {
    "Barak Ravid / X", "Abbas Araghchi / X", "Mohsen Rezaei / X", "Sepah News / X",
    "TankerTrackers", "NOTAM / Airspace",
}

_COUNTRY_FLAGS = (
    ("🇮🇷", ("iran", "iranian", "tehran", "irgc", "ایران", "ایرانی", "تهران", "سپاه")),
    ("🇮🇱", ("israel", "israeli", "netanyahu", "israel katz", "idf", "اسرائیل", "نتانیاهو", "کاتز")),
    ("🇺🇸", ("united states", "u.s.", " us ", "american", "washington", "centcom", "pentagon", "white house", "آمریکا", "واشنگتن", "سنتکام", "پنتاگون", "کاخ سفید")),
    ("🇱🇧", ("lebanon", "hezbollah", "لبنان", "حزب‌الله")),
    ("🇯🇴", ("jordan", "amman", "اردن", "امان")),
    ("🇰🇼", ("kuwait", "کویت")),
    ("🇧🇭", ("bahrain", "بحرین")),
    ("🇶🇦", ("qatar", "doha", "قطر", "دوحه")),
    ("🇦🇪", ("uae", "united arab emirates", "abu dhabi", "dubai", "امارات", "ابوظبی", "دبی")),
    ("🇸🇦", ("saudi", "riyadh", "عربستان", "ریاض")),
    ("🇮🇶", ("iraq", "baghdad", "عراق", "بغداد")),
    ("🇴🇲", ("oman", "muscat", "عمان", "مسقط")),
    ("🇬🇧", ("united kingdom", "britain", "british", "بریتانیا", "انگلیس")),
    ("🇫🇷", ("france", "french", "فرانسه")),
    ("🇩🇪", ("germany", "german", "آلمان")),
    ("🇷🇺", ("russia", "russian", "روسیه")),
    ("🇨🇳", ("china", "chinese", "چین")),
)


def translate_news_to_fa(text: str, session=None) -> str:
    value = (text or "").strip()
    if not value:
        return ""
    latin_words = re.findall(r"\b[A-Za-z]{3,}\b", value)
    words = re.findall(r"[A-Za-z\u0600-\u06FF]+", value)
    mostly_latin = bool(latin_words) and (not words or len(latin_words) / len(words) > 0.30)
    if not mostly_latin:
        return services.translate_to_fa(value, session=session or services.requests)
    translation_session = session or services.requests
    for translator in (services._google_translate, services._mymemory_translate):
        try:
            translated = services._polish_fa(translator(value, session=translation_session))
            translated = services._repair_news_idioms(value, translated)
            if services._translation_quality_ok(value, translated):
                return translated
        except Exception:
            continue
    return ""


def _x_first_fetch_news_items():
    global _x_news_keys
    try: x_items = fetch_builtin_x_news_items()
    except Exception as exc:
        print(f"Newsroom X source error: {exc}", file=sys.stderr); x_items = []
    _x_news_keys = {item.key for item in x_items}
    return list(x_items)


def _fetch_preserved_special_items() -> list:
    merged = {}
    for source_name, query, lang in sources.SPECIAL_QUERIES:
        if source_name not in _PRESERVED_SPECIAL_SOURCES: continue
        try: items = sources._fetch_google_news_query(sources.requests, source_name, query, lang, allow_special_source=True)
        except Exception as exc:
            print(f"Special source error ({source_name}): {exc}", file=sys.stderr); continue
        for item in items: merged.setdefault(item.key, item)
    return list(merged.values())


def _custom_x_and_alert_items() -> list:
    merged = {item.key: item for item in _fetch_preserved_special_items()}
    try: custom_items = _original_custom_fetch()
    except Exception as exc:
        print(f"Custom X source error: {exc}", file=sys.stderr); custom_items = []
    for item in custom_items:
        if item.source.endswith(" / X"): merged.setdefault(item.key, item)
    return list(merged.values())


def _no_priority_web_news() -> list: return []


def _is_newsroom_x(item) -> bool:
    return item.source.endswith(" / X") and item.source not in {
        "Barak Ravid / X", "Abbas Araghchi / X", "Mohsen Rezaei / X", "Sepah News / X",
    }


def _strict_rejection_reason(item, now: datetime):
    if _is_newsroom_x(item):
        if base.agent._published_dt(item.published) is None: return "invalid_publish_time"
        if not base.agent._published_today(item.published, now): return "not_today_tehran"
        if not is_monitored_x_topic(f"{item.title} {item.summary}"): return "low_signal_or_unapproved_source"
        return None
    return base._original_news_rejection_reason(item, now)


def _priority_event_priority(item) -> int:
    score = _original_priority_score(item)
    if item.key in _x_news_keys or item.source.endswith(" / X"): score = max(score, 85)
    return score


def fetch_news_detail_x_only(item, session=None) -> str:
    if item.source.endswith(" / X"): return ""
    if session is None: return fetch_news_detail_enriched(item)
    return fetch_news_detail_enriched(item, session=session)


def _country_flags(item, title_fa: str, summary_fa: str) -> str:
    text = f" {item.title} {item.summary} {title_fa} {summary_fa} ".lower()
    flags = [flag for flag, terms in _COUNTRY_FLAGS if any(term in text for term in terms)]
    return " ".join(dict.fromkeys(flags))


def _format_news_with_flags(item, title_fa: str, summary_fa: str, marker_override=None) -> str:
    text = _original_news_format(item, title_fa, summary_fa, marker_override=marker_override)
    if not text:
        return text
    flags = _country_flags(item, title_fa, summary_fa)
    if flags:
        marker = "\n⏰ "
        if marker in text:
            text = text.replace(marker, f"\n\n{flags}\n\n⏰ ", 1)
        else:
            text += f"\n\n{flags}"
    return text


def _brand_footer_with_arrow() -> list[str]:
    return ["", f'👉🏻 📡 <a href="{base.news_formatters.CHANNEL_URL}">بی‌خبر</a> ←', "مانیتور تحولات ایران"]


def _fetch_market_with_oil():
    snapshot = _original_market_fetch()
    oil = fetch_oil_snapshot()
    object.__setattr__(snapshot, "brent_usd", oil.brent_usd)
    object.__setattr__(snapshot, "wti_usd", oil.wti_usd)
    return snapshot


def _insert_before_timestamp(text: str, extra_lines: list[str]) -> str:
    if not extra_lines: return text
    marker = "\n⏰ "
    block = "\n" + "\n".join(extra_lines) + "\n"
    if marker in text: return text.replace(marker, block + "⏰ ", 1)
    return text + block.rstrip()


def _format_market_with_oil(snapshot, now=None) -> str:
    text = _original_market_format(snapshot, now)
    oil = OilSnapshot(getattr(snapshot, "brent_usd", None), getattr(snapshot, "wti_usd", None))
    lines = format_oil_lines(oil)
    if lines: lines.append("📌 منبع نفت: Yahoo Finance")
    return _insert_before_timestamp(text, lines)


def _record_market_with_oil(state: dict, snapshot, now: datetime) -> None:
    _original_record_market(state, snapshot, now)
    data = state.get("market_day_prices") or {}
    for key in ("brent", "wti"):
        value = getattr(snapshot, f"{key}_usd", None)
        if value is None: continue
        if data.get(f"first_{key}") is None: data[f"first_{key}"] = float(value)
        data[f"last_{key}"] = float(value)
    state["market_day_prices"] = data


def _oil_daily_lines(label: str, first: float | None, last: float | None) -> list[str]:
    if first is None or last is None: return []
    diff = last - first
    pct = 0.0 if first == 0 else abs(diff) / first * 100
    if diff > 0: change = f"▲ ${abs(diff):,.2f} | {pct:.2f}٪ افزایش"
    elif diff < 0: change = f"▼ ${abs(diff):,.2f} | {pct:.2f}٪ کاهش"
    else: change = "— بدون تغییر"
    return [f"🛢 <b>{label}</b>", f"${first:,.2f} ← ${last:,.2f} / بشکه", change]


def _format_market_daily_with_oil(first_usd, last_usd, first_gold, last_gold, now=None) -> str:
    text = _original_market_daily_format(first_usd, last_usd, first_gold, last_gold, now)
    try:
        state = base.agent.load_state(base.agent.STATE_PATH); data = state.get("market_day_prices") or {}
    except Exception: data = {}
    extra: list[str] = []
    for label, key in (("نفت برنت", "brent"), ("نفت WTI", "wti")):
        lines = _oil_daily_lines(label, data.get(f"first_{key}"), data.get(f"last_{key}"))
        if lines:
            if extra: extra.append("")
            extra.extend(lines)
    if extra: extra.extend(["", "📌 منبع نفت: Yahoo Finance"])
    return _insert_before_timestamp(text, extra)


def _install_market_hooks() -> None:
    global _market_hooks_installed
    if _market_hooks_installed: return
    base.agent.fetch_market_snapshot = _fetch_market_with_oil
    base.agent.format_market = _format_market_with_oil
    base.agent._record_market_snapshot = _record_market_with_oil
    base.agent.format_market_daily_summary = _format_market_daily_with_oil
    _market_hooks_installed = True


def install_integrations() -> None:
    base._original_fetch_news_items = _x_first_fetch_news_items
    base.fetch_custom_news_items = _custom_x_and_alert_items
    base.fetch_priority_news_items = _no_priority_web_news
    base._priority_rejection_reason = _strict_rejection_reason
    base._priority_event_priority = _priority_event_priority
    base._original_format_news = _format_news_with_flags
    base.news_formatters._brand_footer = _brand_footer_with_arrow
    base.agent.fetch_news_detail = fetch_news_detail_x_only
    base.agent.translate_to_fa = translate_news_to_fa
    _install_market_hooks()
    base.install_integrations()


def run(now: datetime | None = None) -> int:
    install_integrations()
    rc = base.agent.run(now)
    if rc == 0:
        try: base._send_hormuz_daily(now)
        except Exception as exc: print(f"Hormuz daily report error: {exc}", file=sys.stderr)
    base._flush_recent_published(now)
    return rc


def monitor_loop(poll_seconds: int = 60, session_seconds: int = 240) -> int:
    import time
    poll_seconds = max(1, int(poll_seconds)); session_seconds = max(poll_seconds, int(session_seconds))
    started = time.monotonic()
    while True:
        cycle_started = time.monotonic()
        if cycle_started - started >= session_seconds: return 0
        rc = run()
        if rc != 0: return rc
        cycle_finished = time.monotonic()
        if cycle_finished - started + poll_seconds > session_seconds: return 0
        time.sleep(max(0.0, poll_seconds - (cycle_finished - cycle_started)))


def _cli() -> int:
    import os
    if "--monitor" in sys.argv[1:]:
        return monitor_loop(poll_seconds=int(os.environ.get("POLL_SECONDS", "60")), session_seconds=int(os.environ.get("SESSION_SECONDS", "240")))
    return run()


if __name__ == "__main__":
    raise SystemExit(_cli())
