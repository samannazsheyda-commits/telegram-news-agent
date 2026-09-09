from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from .newsroom_models import NormalizedNewsItem


TEHRAN = ZoneInfo("Asia/Tehran")
MIDNIGHT_GRACE = timedelta(hours=3)

IRAN_TERMS = (
    "iran", "iranian", "tehran", "irgc", "revolutionary guard", "persian gulf", "rial", "toman",
    "ایران", "ایرانی", "تهران", "سپاه", "خلیج فارس", "ریال", "تومان",
)
REGIONAL_TERMS = (
    "israel", "iraq", "jordan", "qatar", "kuwait", "bahrain", "uae", "united arab emirates",
    "saudi arabia", "oman", "yemen", "lebanon", "syria", "gulf",
    "اسرائیل", "عراق", "اردن", "قطر", "کویت", "بحرین", "امارات", "عربستان", "عمان", "یمن", "لبنان", "سوریه", "خلیج",
)
WAR_TERMS = (
    "war", "attack", "strike", "strikes", "struck", "bombing", "military attack", "military strike",
    "missile", "ballistic", "cruise missile", "rocket", "launch", "launched", "intercept", "intercepted",
    "explosion", "blast", "detonation", "drone attack", "airstrike", "air strike",
    "جنگ", "حمله", "حملات", "بمباران", "موشک", "بالستیک", "کروز", "راکت", "شلیک", "رهگیری", "انفجار", "پهپاد",
)
HORMUZ_TERMS = ("strait of hormuz", "hormuz", "تنگه هرمز", "هرمز")
SHIP_TERMS = (
    "ship", "ships", "vessel", "vessels", "tanker", "tankers", "warship", "warships", "shipping",
    "cargo ship", "merchant vessel", "naval vessel", "navy ship", "seized", "seizure", "sunk", "sinking",
    "کشتی", "شناور", "نفتکش", "ناو", "ناو جنگی", "کشتیرانی", "توقیف", "غرق",
)
SANCTION_TERMS = ("sanction", "sanctions", "sanctioned", "تحریم", "تحریم‌ها", "تحریم شد")
FX_TERMS = (
    "dollar", "usd", "exchange rate", "currency", "forex", "rial", "toman", "free market dollar",
    "دلار", "ارز", "نرخ ارز", "ریال", "تومان", "بازار ارز",
)
GOLD_TERMS = ("gold", "gold price", "18k gold", "طلا", "قیمت طلا", "طلای ۱۸")
MARKET_IRAN_TERMS = ("iran", "iranian", "rial", "toman", "tehran market", "ایران", "ایرانی", "ریال", "تومان", "بازار ایران")

ARTICLE_PREFIXES = (
    "analysis:", "analysis -", "opinion:", "opinion -", "explainer:", "explainer -",
    "commentary:", "commentary -", "factbox:", "factbox -", "viewpoint:", "viewpoint -",
    "تحلیل:", "تحلیل -", "یادداشت:", "یادداشت -", "نظر:", "نظر -", "گزارش تحلیلی:",
)
QUESTION_PREFIXES = (
    "why ", "how ", "what ", "when ", "where ", "who ", "could ", "would ", "should ",
    "can ", "will ", "is ", "are ", "does ", "do ", "did ", "what we know", "what to know",
    "چرا ", "چگونه ", "چطور ", "آیا ", "چه چیزی ", "چه می‌دانیم", "آنچه می‌دانیم",
)
TEASER_PATTERNS = (
    "read more", "continue reading", "full story", "click here", "more at ", "more on ",
    "ادامه مطلب", "ادامه خبر", "برای ادامه", "متن کامل", "بیشتر بخوانید",
)
AGGREGATOR_HOSTS = {
    "news.google.com", "www.news.google.com", "feedproxy.google.com", "google.com", "www.google.com",
}


@dataclass(frozen=True)
class EligibilityResult:
    eligible: bool
    reason: str
    review: bool = False


def _parse_published(value: str) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        pass
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _fresh_enough(published: datetime, now: datetime) -> bool:
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now_utc = now.astimezone(timezone.utc)
    if published > now_utc + timedelta(minutes=10):
        return False
    local_now = now_utc.astimezone(TEHRAN)
    local_published = published.astimezone(TEHRAN)
    if local_published.date() == local_now.date():
        return True
    if local_now.hour < 3 and local_published.date() == (local_now.date() - timedelta(days=1)):
        return timedelta(0) <= now_utc - published <= MIDNIGHT_GRACE
    return False


def _contains_any(text: str, terms) -> bool:
    return any(term in text for term in terms)


def _question_or_article(title: str) -> bool:
    clean = re.sub(r"\s+", " ", str(title or "")).strip().lower()
    if not clean:
        return False
    if clean.endswith("?") or clean.endswith("؟"):
        return True
    if clean.startswith(ARTICLE_PREFIXES):
        return True
    if clean.startswith(QUESTION_PREFIXES):
        return True
    return False


def _incomplete_or_teaser(title: str, summary: str) -> bool:
    title_clean = re.sub(r"\s+", " ", str(title or "")).strip()
    summary_clean = re.sub(r"\s+", " ", str(summary or "")).strip()
    combined = f"{title_clean} {summary_clean}".lower()
    if any(pattern in combined for pattern in TEASER_PATTERNS):
        return True
    if title_clean.endswith(("...", "…")) or summary_clean.endswith(("...", "…")):
        return True
    if summary_clean and re.search(r"\b(?:in|on|at)\s+[a-z0-9-]+(?:\.[a-z0-9-]+)+[.!]?\s*$", summary_clean, re.I):
        return True
    return False


def _direct_source_link(url: str) -> bool:
    raw = str(url or "").strip()
    if not raw:
        return False
    try:
        parsed = urlparse(raw)
    except Exception:
        return False
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    host = parsed.netloc.lower().split(":", 1)[0]
    return host not in AGGREGATOR_HOSTS


def _inside_locked_scope(text: str) -> bool:
    iran = _contains_any(text, IRAN_TERMS)
    regional = _contains_any(text, REGIONAL_TERMS)
    hormuz = _contains_any(text, HORMUZ_TERMS)

    # War/missiles/explosions are relevant when Iran is an actor/target, or when
    # the event is explicitly in Hormuz. Generic regional conflict is intentionally
    # not enough: the channel is an Iran developments monitor.
    if _contains_any(text, WAR_TERMS) and (iran or hormuz):
        return True

    # Hormuz and Iran-linked maritime incidents are core channel topics.
    if hormuz and (_contains_any(text, SHIP_TERMS) or _contains_any(text, WAR_TERMS) or "strait" in text or "تنگه" in text):
        return True
    if _contains_any(text, SHIP_TERMS) and (iran or hormuz):
        return True

    # Sanctions must be Iran-related.
    if _contains_any(text, SANCTION_TERMS) and iran:
        return True

    # Dollar/currency/gold are allowed only for the Iranian market.
    if (_contains_any(text, FX_TERMS) or _contains_any(text, GOLD_TERMS)) and _contains_any(text, MARKET_IRAN_TERMS):
        return True

    return False


def evaluate_eligibility(item: NormalizedNewsItem, now: datetime) -> EligibilityResult:
    published = _parse_published(item.raw.published_at)
    if published is None:
        return EligibilityResult(False, "invalid_publish_time")
    if not _fresh_enough(published, now):
        return EligibilityResult(False, "stale")
    if _question_or_article(item.raw.title):
        return EligibilityResult(False, "filtered_question_or_article")
    if _incomplete_or_teaser(item.raw.title, item.raw.summary):
        return EligibilityResult(False, "filtered_incomplete_or_teaser")
    if not _direct_source_link(item.raw.source_url):
        return EligibilityResult(False, "filtered_non_direct_source")

    text = re.sub(r"\s+", " ", f"{item.raw.title} {item.raw.summary}".lower()).strip()
    if not _inside_locked_scope(text):
        return EligibilityResult(False, "filtered_outside_channel_scope")

    return EligibilityResult(True, "eligible")
