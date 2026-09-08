from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

from .newsroom_models import NormalizedNewsItem


TEHRAN = ZoneInfo("Asia/Tehran")
MIDNIGHT_GRACE = timedelta(hours=3)

IRAN_TERMS = (
    "iran", "iranian", "tehran", "irgc", "revolutionary guard", "hormuz", "persian gulf",
    "ایران", "ایرانی", "تهران", "سپاه", "هرمز", "خلیج فارس",
)
REGIONAL_SECURITY_TERMS = (
    "jordan", "qatar", "kuwait", "bahrain", "uae", "united arab emirates", "iraq", "saudi arabia",
    "اردن", "قطر", "کویت", "بحرین", "امارات", "عراق", "عربستان",
)
SECURITY_TERMS = (
    "attack", "strike", "missile", "drone", "explosion", "intercept", "airspace", "notam",
    "flight ban", "flight cancellation", "sanction", "tanker", "war", "military", "shipping",
    "حمله", "موشک", "پهپاد", "انفجار", "رهگیری", "حریم هوایی", "نوتام", "لغو پرواز", "تحریم", "نفتکش",
)
COMPANY_TERMS = (
    "company", "corporate", "ceo", "earnings", "profit", "profits", "revenue", "sales", "shares",
    "quarterly", "business", "market outlook", "شرکت", "مدیرعامل", "سود", "درآمد", "سهام",
)
OPERATIONAL_OVERRIDE_TERMS = (
    "resume overflight", "resumes overflight", "resume overflights", "resumes overflights",
    "iranian airspace", "iran airspace", "airspace", "notam", "flight ban", "flight cancellation",
    "attack", "strike", "missile", "drone", "sanction", "tanker", "shipping", "war",
    "ازسرگیری پرواز", "از سرگیری پرواز", "حریم هوایی", "نوتام", "لغو پرواز", "تحریم", "حمله", "موشک", "پهپاد",
)
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


def evaluate_eligibility(item: NormalizedNewsItem, now: datetime) -> EligibilityResult:
    published = _parse_published(item.raw.published_at)
    if published is None:
        return EligibilityResult(False, "invalid_publish_time", review=item.raw.source_priority == "protected")
    if not _fresh_enough(published, now):
        return EligibilityResult(False, "stale")

    if _question_or_article(item.raw.title):
        return EligibilityResult(False, "filtered_question_or_article")

    text = re.sub(r"\s+", " ", f"{item.raw.title} {item.raw.summary}".lower()).strip()
    protected = item.raw.source_priority == "protected"
    iran_relevant = _contains_any(text, IRAN_TERMS)
    regional_security = _contains_any(text, REGIONAL_SECURITY_TERMS) and _contains_any(text, SECURITY_TERMS)
    if not iran_relevant and not regional_security:
        if protected:
            return EligibilityResult(False, "needs_editorial_review", review=True)
        return EligibilityResult(False, "not_iran_relevant")

    company_like = _contains_any(text, COMPANY_TERMS)
    operational = _contains_any(text, OPERATIONAL_OVERRIDE_TERMS)
    if company_like and not operational:
        if protected:
            return EligibilityResult(False, "needs_editorial_review", review=True)
        return EligibilityResult(False, "filtered_low_value")

    return EligibilityResult(True, "eligible")
