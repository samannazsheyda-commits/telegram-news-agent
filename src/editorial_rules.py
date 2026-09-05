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
    "reuters", "bbc", "cnn", "haaretz", "axios", "bloomberg", "cnbc", "nyt", "times", "jazeera",
    "arabiya", "associated", "press", "news", "sky", "financial", "france", "dw", "ap", "afp",
    "رویترز", "بی‌بی‌سی", "سی‌ان‌ان", "هاآرتص", "اکسیوس", "بلومبرگ", "الجزیره", "العربیه",
}

CANONICAL_REPLACEMENTS = (
    (r"\b(united states|u\.?s\.?|america|american|washington)\b", "usa"),
    (r"\b(israeli defense chief|israeli defence chief|israeli defense minister|israeli defence minister)\b", "israel_katz"),
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
    (r"\b(atomic facilities|nuclear facilities|nuclear sites?)\b", "nuclear_site"),
    (r"\b(rebuild|rebuilds|rebuilding|restore|restores|restoring|reconstruct|reconstructing)\b", "rebuild"),
    (r"\b(warn|warns|warned|threaten|threatens|threatened)\b", "warn"),
    (r"\b(strike|strikes|struck|attack|attacks|attacked)\b", "strike"),
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
    "avoid airspace", "avoid iranian airspace", "avoid iran airspace", "aviation warning", "security risk", "security risks",
    "notam", "evacuation", "attack", "attacked", "strike", "struck", "missile", "drone", "explosion",
    "sanction", "sanctions", "seized", "shutdown", "shut down", "facility hit", "infrastructure hit",
    "تعلیق پرواز", "لغو پرواز", "بسته شدن حریم", "حریم هوایی بسته", "اجتناب از حریم هوایی", "هشدار هوانوردی",
    "نوتام", "تخلیه", "حمله", "موشک", "پهپاد", "انفجار", "تحریم", "توقیف",
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
    return text.replace("ي", "ی").replace("ك", "ک")


def _tokens(item: NewsItem) -> set[str]:
    text = _normalize(f"{item.title} {item.summary}")
    tokens = re.findall(r"[a-z0-9_\u0600-\u06ff]+", text)
    return {token for token in tokens if len(token) > 2 and token not in STOPWORDS and token not in SOURCE_WORDS}


def _concepts(item: NewsItem) -> set[str]:
    text = _normalize(f"{item.title} {item.summary}")
    concepts: set[str] = set()
    groups = {
        "iran": ("iran", "iranian", "tehran", "ایران", "ایرانی", "تهران"),
        "usa": ("usa",),
        "israel": ("israel", "israeli", "اسرائیل"),
        "israel_katz": ("israel katz", "israel_katz", "یسرائیل کاتز", "اسرائیل کاتز"),
        "netanyahu": ("netanyahu", "نتانیاهو"),
        "postwar": ("postwar",), "coalition": ("coalition",),
        "abraham": ("abraham accords", "توافق ابراهیم", "پیمان ابراهیم"),
        "intel": ("intel",), "midterms": ("midterms",), "escalate": ("escalate",),
        "sanctions": ("sanction", "sanctions", "تحریم"),
        "talks": ("talks", "negotiation", "negotiations", "مذاکره", "مذاکرات"),
        "irgc": ("irgc", "سپاه", "سپاه پاسداران"), "quds": ("quds", "نیروی قدس"),
        "hezbollah": ("hezbollah", "حزب‌الله"), "lebanon": ("lebanon", "لبنان"),
        "ballistic": ("ballistic_missile", "موشک بالستیک", "موشک‌های بالستیک"),
        "cruise": ("cruise_missile", "موشک کروز", "موشک‌های کروز"),
        "drone": ("drone", "پهپاد"),
        "nuclear": ("nuclear", "atomic", "هسته‌ای", "اتمی"),
        "nuclear_site": ("nuclear_site", "تأسیسات هسته‌ای", "تاسیسات هسته‌ای"),
        "rebuild": ("rebuild", "بازسازی", "بازسازی کند"),
        "warn": ("warn", "هشدار", "تهدید"),
        "strike": ("strike", "حمله", "حملات"),
        "energy": ("energy infrastructure", "oil infrastructure", "gas infrastructure", "زیرساخت انرژی", "زیرساخت‌های انرژی"),
    }
    for name, aliases in groups.items():
        if any(alias in text for alias in aliases):
            concepts.add(name)
    return concepts


def _specific_facts(item: NewsItem) -> set[str]:
    """Facts whose appearance usually means a materially newer development."""
    text = _normalize(f"{item.title} {item.summary}")
    facts = set(re.findall(r"\b(?:[01]?\d|2[0-3]):[0-5]\d\b", text))
    facts.update(re.findall(r"\b(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", text))
    for location in ("fordow", "natanz", "isfahan", "arak", "فردو", "نطنز", "اصفهان", "اراک"):
        if location in text:
            facts.add(location)
    return facts


def is_duplicate_story(left: NewsItem, right: NewsItem) -> bool:
    """Treat the same underlying event/claim as duplicate regardless of outlet wording."""
    a, b = _tokens(left), _tokens(right)
    if not a or not b:
        return False

    left_facts, right_facts = _specific_facts(left), _specific_facts(right)
    if (left_facts or right_facts) and left_facts != right_facts:
        if left_facts - right_facts or right_facts - left_facts:
            return False

    common = a & b
    overlap = len(common) / max(1, min(len(a), len(b)))
    if len(common) >= 5 and overlap >= 0.42:
        return True

    ca, cb = _concepts(left), _concepts(right)
    concept_common = ca & cb
    if len(concept_common) >= 4:
        return True
    if len(concept_common) >= 3:
        return len(common) >= 2 or overlap >= 0.24
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
    text = re.sub(r"\s+", " ", (value or "").strip())
    if any(term in text.lower() for term in BOILERPLATE_TERMS):
        return ""
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rsplit(" ", 1)[0].strip() + "…"


def priority_search_queries() -> tuple[tuple[str, str], ...]:
    return (
        ("Netanyahu", '("Benjamin Netanyahu" OR Netanyahu) (Iran OR Iranian OR Tehran OR IRGC OR Hezbollah OR Lebanon OR nuclear OR missile OR drone)'),
        ("Israel Katz", '("Israel Katz") (Iran OR Iranian OR Tehran OR IRGC OR Hezbollah OR Lebanon OR nuclear OR missile OR drone OR "energy infrastructure")'),
        ("Iran security leadership", '("Mohsen Rezaei" OR IRGC OR "Quds Force" OR "Khatam al-Anbiya" OR "Iranian Army") (Iran OR Israel OR Lebanon OR Hezbollah OR war OR attack)'),
        ("Iran missiles and drones", 'Iran ("ballistic missile" OR "cruise missile" OR drone OR UAV) (Israel OR attack OR launch OR deploy OR base OR war)'),
        ("Iran energy infrastructure", 'Iran ("energy infrastructure" OR refinery OR "oil infrastructure" OR "gas infrastructure" OR "power grid") (Israel OR attack OR strike OR threat OR war)'),
    )


def fetch_priority_news_items(session=requests) -> list[NewsItem]:
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
