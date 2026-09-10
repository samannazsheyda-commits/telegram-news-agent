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
    "iran", "iranian", "tehran", "irgc", "revolutionary guard", "hormuz", "persian gulf",
    "ایران", "ایرانی", "تهران", "سپاه", "هرمز", "خلیج فارس",
)
SECURITY_TERMS = (
    "attack", "strike", "missile", "drone", "explosion", "intercept", "airspace", "notam",
    "flight ban", "flight cancellation", "sanction", "tanker", "war", "military", "shipping",
    "حمله", "موشک", "پهپاد", "انفجار", "رهگیری", "حریم هوایی", "نوتام", "لغو پرواز", "تحریم", "نفتکش",
)
# Automatic publication is deliberately narrow. Iran relevance alone is not
# enough; the story must also belong to one of the newsroom's selected beats.
SELECTED_TOPIC_TERMS = (
    # kinetic / military
    "missile", "ballistic", "cruise missile", "rocket", "drone", "uav", "attack", "strike",
    "explosion", "blast", "bombing", "intercept", "air defense", "air defence", "air raid",
    "warship", "destroyer", "carrier", "military exercise", "military drill", "naval exercise",
    "weapon", "weapons", "munition", "موشک", "بالستیک", "کروز", "راکت", "پهپاد", "حمله",
    "انفجار", "بمباران", "رهگیری", "پدافند", "آژیر", "ناو", "ناوشکن", "رزمایش", "تسلیحات",
    # Hormuz / maritime
    "strait of hormuz", "hormuz", "persian gulf", "tanker", "shipping", "commercial vessel",
    "merchant vessel", "ship seized", "vessel seized", "seizure", "sinking", "خلیج فارس", "تنگه هرمز",
    "هرمز", "نفتکش", "کشتی تجاری", "شناور", "توقیف", "غرق",
    # airspace
    "airspace", "notam", "flight ban", "flight cancellation", "flights cancelled", "حریم هوایی",
    "نوتام", "لغو پرواز", "ممنوعیت پرواز",
    # nuclear / sanctions / high-value Iran policy
    "nuclear", "uranium", "enrichment", "iaea", "atomic", "sanction", "sanctions", "هسته‌ای",
    "هسته ای", "اورانیوم", "غنی‌سازی", "آژانس بین‌المللی انرژی اتمی", "تحریم",
    # explicitly selected public figures / security institutions
    "trump", "white house", "pentagon", "centcom", "ترامپ", "کاخ سفید", "پنتاگون", "سنتکام",
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
    "inside ", "live updates:", "live updates -", "timeline:", "timeline -", "profile:", "profile -",
    "background:", "background -", "everything you need to know", "what we know", "what to know",
    "تحلیل:", "تحلیل -", "یادداشت:", "یادداشت -", "نظر:", "نظر -", "گزارش تحلیلی:",
    "آنچه باید بدانید", "آنچه می‌دانیم", "خط زمانی:", "پروفایل:",
)
QUESTION_PREFIXES = (
    "why ", "how ", "what ", "when ", "where ", "who ", "could ", "would ", "should ",
    "can ", "will ", "is ", "are ", "does ", "do ", "did ",
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
    if "?" in clean or "؟" in clean:
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
    if host in AGGREGATOR_HOSTS:
        return False
    return True


def evaluate_eligibility(item: NormalizedNewsItem, now: datetime) -> EligibilityResult:
    published = _parse_published(item.raw.published_at)
    if published is None:
        return EligibilityResult(False, "invalid_publish_time", review=item.raw.source_priority == "protected")
    if not _fresh_enough(published, now):
        return EligibilityResult(False, "stale")

    if _question_or_article(item.raw.title):
        return EligibilityResult(False, "filtered_question_or_article")
    if _incomplete_or_teaser(item.raw.title, item.raw.summary):
        return EligibilityResult(False, "filtered_incomplete_or_teaser")
    if not _direct_source_link(item.raw.source_url):
        return EligibilityResult(False, "filtered_non_direct_source")

    text = re.sub(r"\s+", " ", f"{item.raw.title} {item.raw.summary}".lower()).strip()
    protected = item.raw.source_priority == "protected"
    iran_relevant = _contains_any(text, IRAN_TERMS)

    if not iran_relevant:
        if protected:
            return EligibilityResult(False, "needs_editorial_review", review=True)
        return EligibilityResult(False, "not_iran_relevant")

    # Routine Iran mentions, meetings and general politics are not enough for
    # automatic publication. Protected sources remain visible for human review;
    # lower-priority sources are rejected outright.
    if not _contains_any(text, SELECTED_TOPIC_TERMS):
        return EligibilityResult(False, "outside_selected_topics", review=protected)

    company_like = _contains_any(text, COMPANY_TERMS)
    operational = _contains_any(text, OPERATIONAL_OVERRIDE_TERMS)
    if company_like and not operational:
        if protected:
            return EligibilityResult(False, "needs_editorial_review", review=True)
        return EligibilityResult(False, "filtered_low_value")

    return EligibilityResult(True, "eligible")
