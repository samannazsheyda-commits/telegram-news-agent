from __future__ import annotations

import hashlib
import html
import re
from dataclasses import dataclass
from typing import Any
import xml.etree.ElementTree as ET

import requests
from bs4 import BeautifulSoup

TRUTH_ACCOUNT_ID = "107780257626128497"
TRUTH_URL = f"https://truthsocial.com/api/v1/accounts/{TRUTH_ACCOUNT_ID}/statuses"
TRUMPSTRUTH_FEED = "https://www.trumpstruth.org/feed"
TGJU_OVERVIEW = "https://gem.tgju.org/widget/get/market-overview"
TGJU_PROFILE_BASE = "https://www.tgju.org/profile"
GOOGLE_NEWS_BASE = "https://news.google.com/rss/search"
USER_AGENT = "Mozilla/5.0 (compatible; TelegramNewsAgent/2.0)"

IRAN_NEWS_QUERY = (
    'Iran (war OR Israel OR Trump OR Hormuz OR nuclear OR IAEA OR "Security Council" OR sanctions '
    'OR talks OR attack OR missile OR drone OR tanker OR shipping OR ceasefire OR airspace OR NOTAM '
    'OR explosion OR bank)'
)

NEWS_QUERIES: tuple[tuple[str, str, str], ...] = (
    ("Axios", f'{IRAN_NEWS_QUERY} source:Axios', "en"),
    ("Al Jazeera", f'{IRAN_NEWS_QUERY} source:"Al Jazeera"', "en"),
    ("Channel 14", 'Iran (attack OR missile OR drone OR nuclear OR war OR Israel) site:now14.co.il', "en"),
    ("KAN 11", f'{IRAN_NEWS_QUERY} site:kan.org.il', "en"),
    ("N12", f'{IRAN_NEWS_QUERY} site:n12.co.il', "en"),
    ("Channel 13", f'{IRAN_NEWS_QUERY} site:13tv.co.il', "en"),
    ("Reuters", f'{IRAN_NEWS_QUERY} source:Reuters', "en"),
    ("Associated Press", f'{IRAN_NEWS_QUERY} source:"Associated Press"', "en"),
    ("BBC News", f'{IRAN_NEWS_QUERY} source:"BBC News"', "en"),
    ("CNN", f'{IRAN_NEWS_QUERY} source:CNN', "en"),
    ("Fox News", f'{IRAN_NEWS_QUERY} source:"Fox News"', "en"),
    ("NBC News", f'{IRAN_NEWS_QUERY} source:"NBC News"', "en"),
    ("CBS News", f'{IRAN_NEWS_QUERY} source:"CBS News"', "en"),
    ("ABC News", f'{IRAN_NEWS_QUERY} source:"ABC News"', "en"),
    ("Sky News", f'{IRAN_NEWS_QUERY} source:"Sky News"', "en"),
    ("Bloomberg", f'{IRAN_NEWS_QUERY} source:Bloomberg', "en"),
    ("CNBC", f'{IRAN_NEWS_QUERY} source:CNBC', "en"),
    ("Financial Times", f'{IRAN_NEWS_QUERY} source:"Financial Times"', "en"),
    ("The New York Times", f'{IRAN_NEWS_QUERY} source:"The New York Times"', "en"),
    ("France 24", f'{IRAN_NEWS_QUERY} source:"France 24"', "en"),
    ("DW", f'{IRAN_NEWS_QUERY} source:DW', "en"),
    ("Times of Israel", f'{IRAN_NEWS_QUERY} source:"The Times of Israel"', "en"),
    ("Haaretz", f'{IRAN_NEWS_QUERY} source:Haaretz', "en"),
    ("Marco Rubio", '"Marco Rubio" Iran', "en"),
    ("Mohammad Bagher Ghalibaf", '("Mohammad Bagher Ghalibaf" OR Ghalibaf OR قالیباف) (Iran OR ایران)', "en"),
    ("Scott Bessent", '"Scott Bessent" Iran', "en"),
    ("J.D. Vance", '("J.D. Vance" OR "JD Vance") Iran', "en"),
    ("Donald Trump", '("Donald Trump" OR Trump) Iran', "en"),
)

SPECIAL_QUERIES: tuple[tuple[str, str, str], ...] = (
    ("Donald Trump / Truth Social", '(Iran OR Iranian OR Tehran OR Hormuz) site:truthsocial.com/@realDonaldTrump', "en"),
    ("Barak Ravid / X", '(Iran OR Iranian OR Tehran OR Hormuz) site:x.com/BarakRavid', "en"),
    ("Abbas Araghchi / X", '(Iran OR Iranian OR Tehran OR Hormuz) site:x.com/araghchi', "en"),
    ("Mohsen Rezaei / X", '(Iran OR Iranian OR Tehran OR Hormuz) (site:x.com/ir_rezaee OR site:x.com/RezaeeMohsen)', "en"),
    ("TankerTrackers", '(Iran OR Hormuz OR "Persian Gulf") (explosion OR attack OR strike OR fire OR collision OR conflict OR seized OR sinking) site:x.com/TankerTrackers', "en"),
    ("NOTAM / Airspace", '(Iran OR Iranian OR "Persian Gulf") (NOTAM OR airspace OR "flight ban" OR "flight cancellation" OR "flights cancelled" OR "airspace closed" OR "airspace reopened")', "en"),
    ("Al Arabiya", '(Jordan OR Qatar OR Bahrain OR Kuwait OR UAE OR Iraq OR "Saudi Arabia") ("air defense" OR "air defence" OR interception OR intercepted OR sirens OR missile OR drone OR explosion) source:"Al Arabiya"', "en"),
)

APPROVED_SOURCE_ALIASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Axios", ("axios",)), ("Al Jazeera", ("al jazeera",)),
    ("Al Arabiya", ("al arabiya", "al arabiya english", "alarabiya")),
    ("Channel 14", ("channel 14", "now 14", "now14", "israel national news 14")),
    ("KAN 11", ("kan", "kan 11", "kan news", "כאן 11", "כאן חדשות")),
    ("N12", ("n12", "channel 12", "חדשות 12")),
    ("Channel 13", ("channel 13", "13tv", "reshet 13", "חדשות 13")),
    ("Fox News", ("fox news", "foxnews")),
    ("NBC News", ("nbc news", "nbcnews")),
    ("CBS News", ("cbs news", "cbsnews")),
    ("ABC News", ("abc news", "abcnews")),
    ("Sky News", ("sky news", "skynews")),
    ("Bloomberg", ("bloomberg",)),
    ("CNBC", ("cnbc",)),
    ("Reuters", ("reuters",)), ("Associated Press", ("associated press", "ap news", "apnews")),
    ("BBC News", ("bbc", "bbc news", "bbc.com")), ("CNN", ("cnn",)),
    ("Financial Times", ("financial times",)),
    ("The New York Times", ("new york times", "the new york times")),
    ("France 24", ("france 24", "france24")), ("DW", ("dw", "deutsche welle")),
    ("Times of Israel", ("times of israel", "the times of israel")), ("Haaretz", ("haaretz",)),
)

@dataclass(frozen=True)
class TruthPost:
    id: str
    created_at: str
    text: str
    url: str
    is_retruth: bool = False

@dataclass(frozen=True)
class NewsItem:
    key: str
    source: str
    title: str
    summary: str
    link: str
    published: str

@dataclass(frozen=True)
class MarketSnapshot:
    usd_rial: int
    gold18_rial: int
    eur_rial: int | None = None
    gbp_rial: int | None = None
    aed_rial: int | None = None
    try_rial: int | None = None
    emami_rial: int | None = None
    half_rial: int | None = None
    quarter_rial: int | None = None
    gram_coin_rial: int | None = None
    bitcoin_usd: float | None = None
    tether_rial: int | None = None

    @staticmethod
    def _toman(value: int | None) -> int | None:
        return None if value is None else value // 10
    @property
    def usd_toman(self) -> int: return self.usd_rial // 10
    @property
    def gold18_toman(self) -> int: return self.gold18_rial // 10
    @property
    def eur_toman(self) -> int | None: return self._toman(self.eur_rial)
    @property
    def gbp_toman(self) -> int | None: return self._toman(self.gbp_rial)
    @property
    def aed_toman(self) -> int | None: return self._toman(self.aed_rial)
    @property
    def try_toman(self) -> int | None: return self._toman(self.try_rial)
    @property
    def emami_toman(self) -> int | None: return self._toman(self.emami_rial)
    @property
    def half_toman(self) -> int | None: return self._toman(self.half_rial)
    @property
    def quarter_toman(self) -> int | None: return self._toman(self.quarter_rial)
    @property
    def gram_coin_toman(self) -> int | None: return self._toman(self.gram_coin_rial)
    @property
    def tether_toman(self) -> int | None: return self._toman(self.tether_rial)


def strip_html(raw: str) -> str:
    soup = BeautifulSoup(raw or "", "html.parser")
    return html.unescape(re.sub(r"\s+", " ", soup.get_text(" ", strip=True))).strip()


def _truth_api_posts(payload: list[dict[str, Any]]) -> list[TruthPost]:
    result: list[TruthPost] = []
    for status in payload:
        target = status.get("reblog") or status
        text = strip_html(target.get("content", "")) or "(پست بدون متن؛ ممکن است شامل تصویر یا ویدیو باشد)"
        result.append(TruthPost(str(status.get("id", "")), str(status.get("created_at", "")), text, str(status.get("url") or target.get("url") or ""), bool(status.get("reblog"))))
    return result


def parse_trumpstruth_rss(content: bytes) -> list[TruthPost]:
    root = ET.fromstring(content)
    result: list[TruthPost] = []
    for node in root.findall(".//item"):
        def value(tag: str) -> str:
            child = node.find(tag)
            return (child.text or "").strip() if child is not None else ""
        link = value("link") or value("guid")
        match = re.search(r"/statuses/(\d+)", link)
        if not match:
            continue
        title = strip_html(value("title"))
        description = strip_html(value("description"))
        text = description or re.sub(r"^Donald J\. Trump:\s*", "", title).strip()
        if text:
            result.append(TruthPost(match.group(1), value("pubDate"), text, link, "retruthed" in title.lower()))
    result.sort(key=lambda p: int(p.id), reverse=True)
    return result


def fetch_truth_posts(session=requests, limit: int = 20) -> list[TruthPost]:
    try:
        response = session.get(TRUTH_URL, params={"limit": limit, "exclude_replies": "true", "with_muted": "true"}, headers={"User-Agent": USER_AGENT}, timeout=20)
        response.raise_for_status()
        return _truth_api_posts(response.json())
    except Exception:
        response = session.get(TRUMPSTRUTH_FEED, headers={"User-Agent": USER_AGENT}, timeout=20)
        response.raise_for_status()
        return parse_trumpstruth_rss(response.content)[:limit]

IRAN_TERMS = {"iran", "iranian", "tehran", "khamenei", "irgc", "revolutionary guard", "hormuz", "persian gulf", "isfahan", "natanz", "fordow", "iran's", "iranians", "ایران", "ایرانی", "تهران", "خامنه", "سپاه", "هرمز", "خلیج فارس", "نطنز", "فردو"}
SECURITY_TERMS = {"explosion", "blast", "attack", "strike", "missile", "drone", "fire", "conflict", "seized", "sinking", "collision", "notam", "airspace closed", "airspace reopened", "flight ban", "flight cancellation", "flights cancelled", "flight restriction", "air defense", "air defence", "interception", "intercepted", "sirens", "انفجار", "حمله", "درگیری", "موشک", "پهپاد", "آتش", "توقیف", "غرق", "نوتام", "بسته شدن حریم", "بازگشایی حریم", "لغو پرواز", "ممنوعیت پرواز", "پدافند", "رهگیری", "آژیر"}
REGIONAL_TERMS = {"jordan", "amman", "qatar", "doha", "bahrain", "kuwait", "uae", "united arab emirates", "abu dhabi", "dubai", "iraq", "baghdad", "saudi arabia", "riyadh", "اردن", "امان", "قطر", "دوحه", "بحرین", "کویت", "امارات", "ابوظبی", "دبی", "عراق", "بغداد", "عربستان", "ریاض"}


def is_iran_related(text: str) -> bool:
    haystack = (text or "").lower(); return any(term in haystack for term in IRAN_TERMS)


def is_security_alert(text: str) -> bool:
    haystack = (text or "").lower(); return any(term in haystack for term in SECURITY_TERMS)


def is_regional_security_alert(text: str) -> bool:
    haystack = (text or "").lower()
    return any(term in haystack for term in REGIONAL_TERMS) and is_security_alert(haystack)


def canonical_source(raw: str) -> str | None:
    value = re.sub(r"\s+", " ", (raw or "").lower()).strip()
    for canonical, aliases in APPROVED_SOURCE_ALIASES:
        if any(alias == value or alias in value for alias in aliases): return canonical
    return None


def _story_title(title: str) -> str:
    text = re.sub(r"\s+-\s+[^-]{2,80}$", "", title.strip())
    return re.sub(r"[^a-z0-9\u0600-\u06ff]+", " ", text.lower()).strip()


def _news_key(source: str, title: str) -> str:
    return hashlib.sha1(_story_title(title).encode("utf-8")).hexdigest()


def parse_google_news_rss(content: bytes, fallback_source: str, allow_special_source: bool = False) -> list[NewsItem]:
    root = ET.fromstring(content); items: list[NewsItem] = []
    for node in root.findall(".//item"):
        def value(tag: str) -> str:
            child = node.find(tag); return (child.text or "").strip() if child is not None else ""
        title, summary = strip_html(value("title")), strip_html(value("description"))
        combined = f"{title} {summary}"
        if not is_iran_related(combined) and not (fallback_source == "Al Arabiya" and is_regional_security_alert(combined)):
            continue
        source_node = node.find("source")
        raw_source = strip_html(source_node.text or "") if source_node is not None else fallback_source
        source = canonical_source(raw_source)
        if not source:
            if not allow_special_source: continue
            source = fallback_source
        items.append(NewsItem(_news_key(source, title), source, title, summary, value("link"), value("pubDate")))
    return items


def _google_news_url(query: str, lang: str = "en") -> tuple[str, dict[str, str]]:
    if lang == "fa": return GOOGLE_NEWS_BASE, {"q": query, "hl": "fa", "gl": "IR", "ceid": "IR:fa"}
    return GOOGLE_NEWS_BASE, {"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"}


def fetch_news_items(session=requests) -> list[NewsItem]:
    merged: dict[str, NewsItem] = {}
    for fallback_source, query, lang in NEWS_QUERIES:
        url, params = _google_news_url(query, lang)
        response = session.get(url, params=params, headers={"User-Agent": USER_AGENT}, timeout=20); response.raise_for_status()
        for item in parse_google_news_rss(response.content, fallback_source=fallback_source): merged.setdefault(item.key, item)
    for fallback_source, query, lang in SPECIAL_QUERIES:
        url, params = _google_news_url(query, lang)
        response = session.get(url, params=params, headers={"User-Agent": USER_AGENT}, timeout=20); response.raise_for_status()
        for item in parse_google_news_rss(response.content, fallback_source=fallback_source, allow_special_source=True):
            combined = f"{item.title} {item.summary}"
            if fallback_source in {"TankerTrackers", "NOTAM / Airspace"} and not is_security_alert(combined): continue
            if fallback_source == "Al Arabiya" and not is_regional_security_alert(combined): continue
            merged.setdefault(item.key, item)
    return list(merged.values())


def _extract_price(text: str, labels: list[str]) -> int:
    normalized = text.replace("٬", ",")
    for label in labels:
        match = re.search(rf"{re.escape(label)}\s+([0-9][0-9,]*(?:\.[0-9]+)?)", normalized)
        if match: return int(float(match.group(1).replace(",", "")))
    raise ValueError(f"price not found for labels: {labels}")


def _extract_float_price(text: str, labels: list[str]) -> float:
    normalized = text.replace("٬", ",")
    for label in labels:
        match = re.search(rf"{re.escape(label)}\s+([0-9][0-9,]*(?:\.[0-9]+)?)", normalized)
        if match: return float(match.group(1).replace(",", ""))
    raise ValueError(f"price not found for labels: {labels}")


def parse_tgju_profile_rate(page_text: str) -> int:
    match = re.search(r"نرخ فعلی::\s*([0-9][0-9,]*)", page_text.replace("٬", ","))
    if not match: raise ValueError("TGJU profile current rate not found")
    return int(match.group(1).replace(",", ""))


def parse_tgju_tether_rial(page_text: str) -> int:
    match = re.search(r"قیمت ریالی\s*[:|]?\s*([0-9][0-9,]*)", page_text.replace("٬", ","))
    if not match: raise ValueError("TGJU tether rial price not found")
    return int(match.group(1).replace(",", ""))


def parse_tgju_overview(page_text: str) -> MarketSnapshot:
    return MarketSnapshot(usd_rial=_extract_price(page_text, ["دلار"]), gold18_rial=_extract_price(page_text, ["طلا ۱۸", "طلا 18", "طلای ۱۸", "طلای 18"]), eur_rial=_extract_price(page_text, ["یورو"]), emami_rial=_extract_price(page_text, ["سکه"]), bitcoin_usd=_extract_float_price(page_text, ["بیت کوین", "بیت‌کوین"]))


def _fetch_profile_text(session, slug: str) -> str:
    response = session.get(f"{TGJU_PROFILE_BASE}/{slug}", headers={"User-Agent": USER_AGENT}, timeout=20); response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser").get_text(" ", strip=True)


def fetch_market_snapshot(session=requests) -> MarketSnapshot:
    response = session.get(TGJU_OVERVIEW, headers={"User-Agent": USER_AGENT}, timeout=20); response.raise_for_status()
    base = parse_tgju_overview(BeautifulSoup(response.text, "html.parser").get_text(" ", strip=True))
    extras: dict[str, int | None] = {}
    for field, slug in (("gbp_rial", "price_gbp"), ("aed_rial", "price_aed"), ("try_rial", "price_try"), ("half_rial", "nim"), ("quarter_rial", "rob"), ("gram_coin_rial", "gerami")):
        try: extras[field] = parse_tgju_profile_rate(_fetch_profile_text(session, slug))
        except Exception: extras[field] = None
    try: tether_rial = parse_tgju_tether_rial(_fetch_profile_text(session, "crypto-tether"))
    except Exception: tether_rial = None
    return MarketSnapshot(base.usd_rial, base.gold18_rial, base.eur_rial, extras["gbp_rial"], extras["aed_rial"], extras["try_rial"], base.emami_rial, extras["half_rial"], extras["quarter_rial"], extras["gram_coin_rial"], base.bitcoin_usd, tether_rial)
