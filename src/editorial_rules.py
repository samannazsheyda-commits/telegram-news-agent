from __future__ import annotations

import re
from typing import Iterable

import requests

from .sources import NewsItem, _fetch_google_news_query


STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "to", "of", "for", "in", "on", "at", "by", "with",
    "from", "as", "is", "are", "was", "were", "be", "been", "being", "has", "have", "had", "says",
    "said", "saying", "report", "reports", "reported", "cites", "citing", "according", "new", "latest",
    "this", "that", "after", "before", "about", "over", "under", "its", "their", "his", "her", "into",
    "و", "در", "به", "از", "با", "برای", "که", "این", "آن", "یک", "را", "است", "شد", "می", "گفت",
    "اعلام", "کرد", "گزارش", "به‌گفته", "به گفته",
}

SOURCE_WORDS = {
    "reuters", "bbc", "cnn", "haaretz", "axios", "bloomberg", "cnbc", "nyt", "times", "israel",
    "jazeera", "arabiya", "associated", "press", "news", "sky", "financial", "france", "dw",
    "رویترز", "بی‌بی‌سی", "سی‌ان‌ان", "هاآرتص", "اکسیوس", "بلومبرگ", "الجزیره", "العربیه",
}

CANONICAL_REPLACEMENTS = (
    (r"\b(united states|u\.?s\.?|washington)\b", "usa"),
    (r"\b(post[- ]?war|after the war)\b", "postwar"),
    (r"\b(alliance|coalition|bloc)\b", "coalition"),
    (r"\b(expand|expansion|broaden|broader|wider|widen)\b", "expand"),
    (r"\b(midterms?|midterm elections?)\b", "midterms"),
    (r"\b(intelligence assessment|u\.?s\.? intelligence|american intelligence)\b", "intel"),
    (r"\b(escalate|escalation|intensify|intensifies|intensified)\b", "escalate"),
    (r"\b(irgc|islamic revolutionary guard corps|revolutionary guards?)\b", "irgc"),
    (r"\b(quds force|qods force)\b", "quds"),
    (r"\b(ballistic missiles?)\b", "ballistic_missile"),
    (r"\b(cruise missiles?)\b", "cruise_missile"),
    (r"\b(drones?|uavs?|unmanned aerial vehicles?)\b", "drone"),
)

PRIORITY_TERMS = (
    "irgc", "islamic revolutionary guard corps", "revolutionary guard", "quds force", "qods force",
    "سپاه", "سپاه پاسداران", "نیروی قدس", "محسن رضایی", "mohsen rezaei",
    "khatam al-anbiya", "khatam-al anbiya", "khatam al anbiya", "قرارگاه خاتم", "خاتم الانبیا", "خاتم‌الانبیا",
    "iranian army", "iran army", "ارتش ایران", "ارتش جمهوری اسلامی",
    "ballistic missile", "ballistic missiles", "موشک بالستیک", "موشک‌های بالستیک",
    "cruise missile", "cruise missiles", "موشک کروز", "موشک‌های کروز",
    "iranian drone", "iran drones", "iranian drones", "پهپاد ایران", "پهپادهای ایران", "پهپاد ایرانی",
    "energy infrastructure", "oil infrastructure", "gas infrastructure", "refinery", "power grid",
    "زیرساخت انرژی", "زیرساخت‌های انرژی", "تأسیسات نفتی", "تاسیسات نفتی", "پالایشگاه", "شبکه برق",
    "benjamin netanyahu", "netanyahu", "بنیامین نتانیاهو", "نتانیاهو",
    "israel katz", "یسرائیل کاتز", "اسرائیل کاتز",
)

IRAN_CONTEXT = (
    "iran", "iranian", "tehran", "irgc", "quds", "سپاه", "ایران", "تهران", "حزب‌الله", "hezbollah",
    "lebanon", "لبنان",
)

COMPANY_TERMS = (
    "company", "corporate", "ceo", "chief executive", "airline", "carrier", "earnings", "profit", "profits",
    "revenue", "sales", "shares", "stock", "growth", "expansion", "fleet", "routes", "aircraft", "acquisition",
    "merger", "quarterly", "business", "شرکت", "مدیرعامل", "سود", "درآمد", "سهام", "ناوگان", "مسیر پروازی",
)

OPERATIONAL_SECURITY_TERMS = (
    "suspend flights", "suspends flights", "suspended flights", "cancelled flights", "canceled flights",
    "flight cancellation", "airspace closure", "airspace closed", "closes airspace", "closed airspace",
    "notam", "evacuation", "attack", "attacked", "strike", "struck", "missile", "drone", "explosion",
    "sanction", "sanctions", "seized", "shutdown", "shut down", "facility hit", "infrastructure hit",
    "تعلیق پرواز", "لغو پرواز", "بسته شدن حریم", "حریم هوایی بسته", "نوتام", "تخلیه", "حمله", "موشک",
    "پهپاد", "انفجار", "تحریم", "توقیف",
)

BOILERPLATE_TERMS = (
    "comprehensive up-to-date news coverage",
    "aggregated from sources all over the world by google news",
    "پوشش جامع و به‌روز اخبار",
    "جمع‌آوری‌شده از منابع مختلف در سراسر جهان توسط گوگل نیوز",
)


def _normalize(value: str) -> str:
    text = re.sub(r"\s+", " ", (value or "").lower()).strip()
    for pattern, replacement in CANONICAL_REPLACEMENTS:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    text = text.replace("ي", "ی").replace("ك", "ک")
    return text


def _tokens(item: NewsItem) -> set[str]:
    text = _normalize(f"{item.title} {item.summary}")
    tokens = re.findall(r"[a-z0-9_\u0600-\u06ff]+", text)
    return {
        token for token in tokens
        if len(token) > 2 and token not in STOPWORDS and token not in SOURCE_WORDS
    }


def _concepts(item: NewsItem) -> set[str]:
    text = _normalize(f"{item.title} {item.summary}")
    concepts: set[str] = set()
    groups = {
        "iran": ("iran", "iranian", "tehran", "ایران", "ایرانی", "تهران"),
        "usa": ("usa",),
        "postwar": ("postwar",),
        "coalition": ("coalition",),
        "abraham": ("abraham accords", "توافق ابراهیم", "پیمان ابراهیم"),
        "intel": ("intel",),
        "midterms": ("midterms",),
        "escalate": ("escalate",),
        "sanctions": ("sanction", "sanctions", "تحریم"),
        "talks": ("talks", "negotiation", "negotiations", "مذاکره", "مذاکرات"),
        "irgc": ("irgc", "سپاه", "سپاه پاسداران"),
        "quds": ("quds", "نیروی قدس"),
        "hezbollah": ("hezbollah", "حزب‌الله"),
        "lebanon": ("lebanon", "لبنان"),
        "ballistic": ("ballistic_missile", "موشک بالستیک", "موشک‌های بالستیک"),
        "cruise": ("cruise_missile", "موشک کروز", "موشک‌های کروز"),
        "drone": ("drone", "پهپاد"),
        "energy": ("energy infrastructure", "oil infrastructure", "gas infrastructure", "زیرساخت انرژی", "زیرساخت‌های انرژی"),
    }
    for name, aliases in groups.items():
        if any(alias in text for alias in aliases):
            concepts.add(name)
    return concepts


def is_duplicate_story(left: NewsItem, right: NewsItem) -> bool:
    """Treat the same underlying event/claim as duplicate regardless of outlet wording."""
    a = _tokens(left)
    b = _tokens(right)
    if not a or not b:
        return False
    common = a & b
    overlap = len(common) / max(1, min(len(a), len(b)))
    if len(common) >= 5 and overlap >= 0.42:
        return True

    ca = _concepts(left)
    cb = _concepts(right)
    concept_common = ca & cb
    if len(concept_common) >= 3:
        return len(common) >= 2 or overlap >= 0.28
    return False


def is_priority_security_news(item: NewsItem) -> bool:
    text = _normalize(f"{item.title} {item.summary}")
    capability_hit = (
        ("ballistic" in text and ("missile" in text or "موشک" in text))
        or ("cruise" in text and ("missile" in text or "موشک" in text))
        or ("موشک" in text and any(term in text for term in ("بالستیک", "کروز")))
        or ("drone" in text and any(ctx in text for ctx in IRAN_CONTEXT))
        or ("پهپاد" in text and any(ctx in text for ctx in IRAN_CONTEXT))
    )
    if not capability_hit and not any(term in text for term in PRIORITY_TERMS):
        return False
    if any(name in text for name in ("netanyahu", "نتانیاهو", "israel katz", "یسرائیل کاتز", "اسرائیل کاتز", "energy infrastructure", "زیرساخت انرژی", "زیرساخت‌های انرژی")):
        return any(ctx in text for ctx in IRAN_CONTEXT) or any(
            term in text for term in ("war", "attack", "missile", "hezbollah", "lebanon", "جنگ", "حمله", "موشک", "حزب‌الله", "لبنان")
        )
    return True


def is_low_value_company_news(item: NewsItem) -> bool:
    text = _normalize(f"{item.title} {item.summary}")
    if not any(term in text for term in COMPANY_TERMS):
        return False
    if any(term in text for term in OPERATIONAL_SECURITY_TERMS):
        return False
    if is_priority_security_news(item):
        return False
    return True


def editorial_detail(value: str, max_chars: int = 1100) -> str:
    """Keep useful source detail without forcing a fixed sentence count."""
    text = re.sub(r"\s+", " ", (value or "").strip())
    if any(term in text.lower() for term in BOILERPLATE_TERMS):
        return ""
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars].rsplit(" ", 1)[0].strip()
    return cut + "…"


def priority_search_queries() -> tuple[tuple[str, str], ...]:
    return (
        ("Netanyahu", '("Benjamin Netanyahu" OR Netanyahu) (Iran OR Iranian OR Tehran OR IRGC OR Hezbollah OR Lebanon OR nuclear OR missile OR drone)'),
        ("Israel Katz", '("Israel Katz") (Iran OR Iranian OR Tehran OR IRGC OR Hezbollah OR Lebanon OR nuclear OR missile OR drone OR "energy infrastructure")'),
        ("Iran security leadership", '("Mohsen Rezaei" OR IRGC OR "Quds Force" OR "Khatam al-Anbiya" OR "Iranian Army") (Iran OR Israel OR Lebanon OR Hezbollah OR war OR attack)'),
        ("Iran missiles and drones", 'Iran ("ballistic missile" OR "cruise missile" OR drone OR UAV) (Israel OR attack OR launch OR deploy OR base OR war)'),
        ("Iran energy infrastructure", 'Iran ("energy infrastructure" OR refinery OR "oil infrastructure" OR "gas infrastructure" OR "power grid") (Israel OR attack OR strike OR threat OR war)'),
    )


def fetch_priority_news_items(session=requests) -> list[NewsItem]:
    """Targeted searches so critical Iran-security subjects are not dependent on generic headlines."""
    merged: dict[str, NewsItem] = {}
    for label, query in priority_search_queries():
        try:
            items = _fetch_google_news_query(session, label, query, "en", allow_special_source=False)
        except Exception:
            continue
        for item in items[:20]:
            merged.setdefault(item.key, item)
    return list(merged.values())


def dedupe_items(items: Iterable[NewsItem], references: Iterable[NewsItem] = ()) -> list[NewsItem]:
    kept: list[NewsItem] = []
    refs = list(references)
    for item in items:
        if any(is_duplicate_story(item, previous) for previous in refs + kept):
            continue
        kept.append(item)
    return kept
