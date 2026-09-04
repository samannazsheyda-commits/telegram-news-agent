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
TGJU_OVERVIEW = "https://gem.tgju.org/widget/get/market-overview"
GOOGLE_NEWS_BASE = "https://news.google.com/rss/search"
USER_AGENT = "Mozilla/5.0 (compatible; TelegramNewsAgent/2.0)"

IRAN_NEWS_QUERY = "Iran (war OR Israel OR Trump OR Hormuz OR nuclear OR sanctions OR talks OR attack OR missile OR drone OR tanker OR shipping OR ceasefire)"

NEWS_QUERIES: tuple[tuple[str, str, str], ...] = (
    ("Axios", f'{IRAN_NEWS_QUERY} source:Axios', "en"),
    ("Al Jazeera", f'{IRAN_NEWS_QUERY} source:"Al Jazeera"', "en"),
    ("Channel 14", 'Iran site:now14.co.il', "en"),
    ("Reuters", f'{IRAN_NEWS_QUERY} source:Reuters', "en"),
    ("Associated Press", f'{IRAN_NEWS_QUERY} source:"Associated Press"', "en"),
    ("BBC News", f'{IRAN_NEWS_QUERY} source:"BBC News"', "en"),
    ("CNN", f'{IRAN_NEWS_QUERY} source:CNN', "en"),
    ("Financial Times", f'{IRAN_NEWS_QUERY} source:"Financial Times"', "en"),
    ("The New York Times", f'{IRAN_NEWS_QUERY} source:"The New York Times"', "en"),
    ("France 24", f'{IRAN_NEWS_QUERY} source:"France 24"', "en"),
    ("DW", f'{IRAN_NEWS_QUERY} source:DW', "en"),
    ("Times of Israel", f'{IRAN_NEWS_QUERY} source:"The Times of Israel"', "en"),
    ("Haaretz", f'{IRAN_NEWS_QUERY} source:Haaretz', "en"),
    ("Marco Rubio", '"Marco Rubio" Iran', "en"),
    ("Mohammad Bagher Ghalibaf", '("Mohammad Bagher Ghalibaf" OR قالیباف) (Iran OR ایران)', "en"),
    ("Scott Bessent", '"Scott Bessent" Iran', "en"),
    ("J.D. Vance", '("J.D. Vance" OR "JD Vance") Iran', "en"),
    ("Donald Trump", '("Donald Trump" OR Trump) Iran', "en"),
    ("Hormuz tankers", '(Iran OR Iranian) ("Strait of Hormuz" OR Hormuz) (tanker OR tankers OR ship OR shipping)', "en"),
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

    @property
    def usd_toman(self) -> int:
        return self.usd_rial // 10

    @property
    def gold18_toman(self) -> int:
        return self.gold18_rial // 10


def strip_html(raw: str) -> str:
    soup = BeautifulSoup(raw or "", "html.parser")
    text = soup.get_text(" ", strip=True)
    return html.unescape(re.sub(r"\s+", " ", text)).strip()


def fetch_truth_posts(session=requests, limit: int = 20) -> list[TruthPost]:
    response = session.get(
        TRUTH_URL,
        params={"limit": limit, "exclude_replies": "true", "with_muted": "true"},
        headers={"User-Agent": USER_AGENT},
        timeout=20,
    )
    response.raise_for_status()
    rows: list[dict[str, Any]] = response.json()
    result: list[TruthPost] = []
    for status in rows:
        target = status.get("reblog") or status
        text = strip_html(target.get("content", ""))
        if not text:
            text = "(پست بدون متن؛ ممکن است شامل تصویر یا ویدیو باشد)"
        result.append(
            TruthPost(
                id=str(status.get("id", "")),
                created_at=str(status.get("created_at", "")),
                text=text,
                url=str(status.get("url") or target.get("url") or ""),
                is_retruth=bool(status.get("reblog")),
            )
        )
    return result


IRAN_TERMS = {
    "iran", "iranian", "tehran", "khamenei", "irgc", "revolutionary guard",
    "hormuz", "persian gulf", "isfahan", "natanz", "fordow", "iran's", "iranians",
    "ایران", "ایرانی", "تهران", "خامنه", "سپاه", "هرمز", "خلیج فارس", "نطنز", "فردو",
}


def is_iran_related(text: str) -> bool:
    haystack = (text or "").lower()
    return any(term in haystack for term in IRAN_TERMS)


def _news_key(source: str, title: str) -> str:
    normalized = re.sub(r"\s+", " ", title.strip().lower())
    return hashlib.sha1(f"{source.lower()}|{normalized}".encode("utf-8")).hexdigest()


def parse_google_news_rss(content: bytes, fallback_source: str) -> list[NewsItem]:
    root = ET.fromstring(content)
    items: list[NewsItem] = []
    for node in root.findall(".//item"):
        def value(tag: str) -> str:
            child = node.find(tag)
            return (child.text or "").strip() if child is not None else ""

        title = strip_html(value("title"))
        summary = strip_html(value("description"))
        if not is_iran_related(f"{title} {summary}"):
            continue
        source_node = node.find("source")
        source = strip_html(source_node.text or "") if source_node is not None else fallback_source
        source = source or fallback_source
        link = value("link")
        items.append(
            NewsItem(
                key=_news_key(source, title),
                source=source,
                title=title,
                summary=summary,
                link=link,
                published=value("pubDate"),
            )
        )
    return items


def _google_news_url(query: str, lang: str = "en") -> tuple[str, dict[str, str]]:
    if lang == "fa":
        return GOOGLE_NEWS_BASE, {"q": query, "hl": "fa", "gl": "IR", "ceid": "IR:fa"}
    return GOOGLE_NEWS_BASE, {"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"}


def fetch_news_items(session=requests) -> list[NewsItem]:
    merged: dict[str, NewsItem] = {}
    for fallback_source, query, lang in NEWS_QUERIES:
        url, params = _google_news_url(query, lang)
        response = session.get(url, params=params, headers={"User-Agent": USER_AGENT}, timeout=20)
        response.raise_for_status()
        for item in parse_google_news_rss(response.content, fallback_source=fallback_source):
            merged.setdefault(item.key, item)
    return list(merged.values())


def _extract_price(text: str, labels: list[str]) -> int:
    normalized = text.replace("٬", ",")
    for label in labels:
        pattern = rf"{re.escape(label)}\s+([0-9][0-9,]*)"
        match = re.search(pattern, normalized)
        if match:
            return int(match.group(1).replace(",", ""))
    raise ValueError(f"price not found for labels: {labels}")


def parse_tgju_overview(page_text: str) -> MarketSnapshot:
    usd = _extract_price(page_text, ["دلار"])
    gold = _extract_price(page_text, ["طلا ۱۸", "طلا 18", "طلای ۱۸", "طلای 18"])
    return MarketSnapshot(usd_rial=usd, gold18_rial=gold)


def fetch_market_snapshot(session=requests) -> MarketSnapshot:
    response = session.get(TGJU_OVERVIEW, headers={"User-Agent": USER_AGENT}, timeout=20)
    response.raise_for_status()
    text = BeautifulSoup(response.text, "html.parser").get_text(" ", strip=True)
    return parse_tgju_overview(text)
