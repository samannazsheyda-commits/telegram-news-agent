from __future__ import annotations

import html
import json
import re
import time
from datetime import datetime, timezone
from email.utils import format_datetime, parsedate_to_datetime

import requests

from . import formatters as _formatters
from .sources import NewsItem, USER_AGENT, _fetch_google_news_query


_BUILTIN_X_NEWSROOMS = (
    # Global newsrooms
    ("Reuters", "@Reuters"), ("Associated Press", "@AP"), ("AFP", "@AFP"),
    ("BBC World", "@BBCWorld"), ("CNN", "@CNN"), ("France 24", "@FRANCE24"),
    ("Al Jazeera English", "@AJEnglish"), ("Al Arabiya English", "@AlArabiya_Eng"),
    ("The New York Times", "@nytimes"), ("NYT World", "@nytimesworld"),
    ("Bloomberg", "@business"), ("Financial Times", "@FT"), ("Sky News", "@SkyNews"),
    ("NBC News", "@NBCNews"), ("CBS News", "@CBSNews"), ("ABC News", "@ABC"),
    ("Fox News", "@FoxNews"), ("DW News", "@dwnews"), ("The Guardian", "@guardian"),
    ("Washington Post", "@washingtonpost"), ("Wall Street Journal", "@WSJ"),
    ("The Economist", "@TheEconomist"),
    # Israeli newsrooms and official sources
    ("Times of Israel", "@TimesofIsrael"), ("Haaretz", "@haaretzcom"), ("Axios", "@axios"),
    ("Jerusalem Post", "@Jerusalem_Post"), ("Israel Hayom", "@IsraelHayomEng"),
    ("Benjamin Netanyahu", "@netanyahu"), ("Israel Katz", "@Israel_katz"),
    ("KAN 11", "@kann_news"), ("N12", "@N12News"), ("Channel 13", "@newsisrael13"),
    ("Channel 14", "@C14_news"), ("IDF", "@IDF"),
    # US officials and institutions relevant to Iran/security/sanctions
    ("CENTCOM", "@CENTCOM"), ("US Treasury", "@USTreasury"),
    ("Scott Bessent", "@SecScottBessent"), ("Pete Hegseth", "@SecDef"),
    ("Marco Rubio", "@SecRubio"), ("JD Vance", "@VP"),
    ("US State Department", "@StateDept"), ("State Department Spokesperson", "@statedeptspox"),
    ("White House", "@WhiteHouse"),
    # Foreign reporters/analysts with recurring Iran, military, nuclear or sanctions coverage
    ("Mark Levin", "@marklevinshow"), ("Jason Brodsky", "@JasonMBrodsky"),
    ("Mark Dubowitz", "@mdubowitz"), ("Emanuel Fabian", "@manniefabian"),
    ("Seth Frantzman", "@sfrantzman"), ("Jonathan Conricus", "@jconricus"),
    ("Michael Doran", "@Doranimated"), ("Jennifer Hansler", "@jmhansler"),
    ("Joe Truzman", "@JoeTruzman"), ("Barak Ravid", "@BarakRavid"),
    # Iranian official/newsroom sources retained from the existing special-source list
    ("Abbas Araghchi", "@araghchi"), ("Mohsen Rezaei", "@ir_rezaee"),
    ("Sepah News", "@Sepah_News"), ("Tasnim Persian", "@Tasnimnews_Fa"),
    ("Tasnim English", "@Tasnimnews_EN"),
    # Maritime source explicitly retained by the user
    ("TankerTrackers", "@TankerTrackers"),
)

_PERSIAN_SOURCE_NAMES = {
    "Reuters": "رویترز", "Associated Press": "آسوشیتدپرس", "AFP": "خبرگزاری فرانسه",
    "BBC World": "بی‌بی‌سی ورلد", "CNN": "سی‌ان‌ان", "France 24": "فرانس ۲۴",
    "Al Jazeera English": "الجزیره انگلیسی", "Al Arabiya English": "العربیه انگلیسی",
    "The New York Times": "نیویورک تایمز", "NYT World": "نیویورک تایمز جهان",
    "Bloomberg": "بلومبرگ", "Financial Times": "فایننشال تایمز", "Sky News": "اسکای نیوز",
    "NBC News": "ان‌بی‌سی نیوز", "CBS News": "سی‌بی‌اس نیوز", "ABC News": "ای‌بی‌سی نیوز",
    "Fox News": "فاکس نیوز", "DW News": "دویچه‌وله", "The Guardian": "گاردین",
    "Washington Post": "واشنگتن پست", "Wall Street Journal": "وال‌استریت ژورنال",
    "The Economist": "اکونومیست", "Times of Israel": "تایمز اسرائیل", "Haaretz": "هاآرتص",
    "Axios": "اکسیوس", "Jerusalem Post": "جروزالم پست", "Israel Hayom": "اسرائیل هیوم",
    "Benjamin Netanyahu": "بنیامین نتانیاهو", "Israel Katz": "اسرائیل کاتز",
    "KAN 11": "کانال ۱۱ اسرائیل", "N12": "کانال ۱۲ اسرائیل", "Channel 13": "کانال ۱۳ اسرائیل",
    "Channel 14": "کانال ۱۴ اسرائیل", "IDF": "ارتش اسرائیل", "CENTCOM": "سنتکام",
    "US Treasury": "وزارت خزانه‌داری آمریکا", "Scott Bessent": "اسکات بسنت",
    "Pete Hegseth": "پیت هگست", "Marco Rubio": "مارکو روبیو", "JD Vance": "جی‌دی ونس",
    "US State Department": "وزارت خارجه آمریکا", "State Department Spokesperson": "سخنگوی وزارت خارجه آمریکا",
    "White House": "کاخ سفید", "Mark Levin": "مارک لوین", "Jason Brodsky": "جیسون برادسکی",
    "Mark Dubowitz": "مارک دوبوویتز", "Emanuel Fabian": "امانوئل فابیان", "Seth Frantzman": "ست فرانتزمن",
    "Jonathan Conricus": "جاناتان کانریکوس", "Michael Doran": "مایکل دوران", "Jennifer Hansler": "جنیفر هنسلر",
    "Joe Truzman": "جو تروزمن", "Barak Ravid": "باراک راوید", "Abbas Araghchi": "عباس عراقچی",
    "Mohsen Rezaei": "محسن رضایی", "Sepah News": "سپاه نیوز", "TankerTrackers": "تانکرترکرز",
    "Tasnim Persian": "تسنیم", "Tasnim English": "تسنیم انگلیسی",
}
for _name, _fa in _PERSIAN_SOURCE_NAMES.items():
    _formatters.SOURCE_FA[f"{_name} / X"] = f"{_fa} / ایکس"

_SECONDARY_MEDIA = (
    "Wall Street Journal", "WSJ", "i24NEWS", "i24 News", "Reuters", "Associated Press", "AP", "AFP",
    "BBC", "CNN", "France 24", "Al Jazeera", "Al Arabiya", "Axios", "Haaretz", "Times of Israel",
    "Jerusalem Post", "New York Times", "NYT", "Bloomberg", "Financial Times", "Sky News", "NBC News",
    "CBS News", "ABC News", "Fox News", "DW News", "The Guardian", "Guardian", "Washington Post",
    "The Economist", "Economist", "N12", "KAN 11", "Channel 13", "Channel 14",
)
_MEDIA_PATTERN = "|".join(sorted((re.escape(name) for name in _SECONDARY_MEDIA), key=len, reverse=True))
_TRAILING_MEDIA_RE = re.compile(rf"\s+(?:[-–—|:]\s*)(?:{_MEDIA_PATTERN})\s*$", re.IGNORECASE)
_PAREN_MEDIA_RE = re.compile(rf"\s*\((?:{_MEDIA_PATTERN})(?:\s*,\s*\d{{4}})?\)\s*([.!?؟]?)$", re.IGNORECASE)
_X_STATUS_RE = re.compile(r"https?://(?:www\.)?(?:x\.com|twitter\.com)/([A-Za-z0-9_]+)/status/(\d+)", re.IGNORECASE)
_NEXT_DATA_RE = re.compile(r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>', re.IGNORECASE | re.DOTALL)
_X_SYNDICATION_BASE = "https://syndication.twitter.com/srv/timeline-profile/screen-name"


def clean_x_post_text(text: str) -> str:
    value = re.sub(r"\s+", " ", html.unescape(text or "")).strip()
    value = _TRAILING_MEDIA_RE.sub("", value).strip()
    match = _PAREN_MEDIA_RE.search(value)
    if match:
        punctuation = match.group(1) or "."
        value = _PAREN_MEDIA_RE.sub(punctuation, value).strip()
    return value


def _direct_x_status_url(value: str, expected_handle: str = "") -> str:
    text = html.unescape(value or "")
    matches = list(_X_STATUS_RE.finditer(text))
    if not matches:
        return ""
    expected = expected_handle.lstrip("@").lower()
    chosen = next((m for m in matches if not expected or m.group(1).lower() == expected), matches[0])
    return f"https://x.com/{chosen.group(1)}/status/{chosen.group(2)}"


def resolve_x_post_url(link: str, handle: str, session=requests) -> str:
    direct = _direct_x_status_url(link, handle)
    if direct:
        return direct
    if not link:
        return ""
    try:
        response = session.get(link, headers={"User-Agent": USER_AGENT}, timeout=12, allow_redirects=True)
        response.raise_for_status()
    except Exception:
        return ""
    direct = _direct_x_status_url(getattr(response, "url", ""), handle)
    if direct:
        return direct
    return _direct_x_status_url(getattr(response, "text", ""), handle)


_X_IRAN_QUERY = (
    '(Iran OR Iranian OR Tehran OR IRGC OR "Quds Force" OR Hormuz OR "Persian Gulf" OR "Gulf of Oman" '
    'OR "Arabian Sea" OR "Abraham Lincoln" OR "USS Boxer" OR "carrier strike group" OR carrier OR destroyer '
    'OR submarine OR "Fifth Fleet" OR NAVCENT OR minelaying OR "mine laying" OR "naval mine" '
    'OR "mine countermeasures" OR "Al Udeid" OR "Al Dhafra" OR Bahrain OR Qatar OR Kuwait OR "Diego Garcia" '
    'OR missile OR "ballistic missile" OR "cruise missile" OR drone OR nuclear OR enrichment OR uranium '
    'OR centrifuge OR IAEA OR Grossi OR inspector OR Fordow OR Natanz OR Isfahan OR Arak OR sanctions OR OFAC '
    'OR "frozen funds" OR "blocked funds" OR "blocked Iranian funds" OR oil OR tanker OR shipping '
    'OR Israel OR Netanyahu OR "Israel Katz" OR Lebanon OR Hezbollah OR airspace OR NOTAM)'
)

_MONITORED_TERMS = (
    "iran", "iranian", "tehran", "irgc", "quds force", "hormuz", "persian gulf", "gulf of oman",
    "arabian sea", "abraham lincoln", "uss boxer", "carrier strike group", "carrier", "destroyer", "submarine",
    "fifth fleet", "navcent", "minelaying", "mine laying", "naval mine", "mine countermeasures",
    "al udeid", "al dhafra", "diego garcia", "bahrain", "qatar", "kuwait", "fordow", "natanz",
    "isfahan", "arak", "iaea", "grossi", "inspector", "centrifuge", "enrichment", "uranium", "ofac",
    "sanctions", "frozen funds", "blocked funds", "ballistic missile", "cruise missile", "drone",
    "netanyahu", "israel katz", "hezbollah", "notam", "tanker", "shipping", "nuclear", "missile",
    "ایران", "تهران", "سپاه", "نیروی قدس", "هرمز", "خلیج فارس", "ناو هواپیمابر", "ناو آب‌خاکی",
    "ناوشکن", "زیردریایی", "ناوگان پنجم", "مین‌گذاری", "مین دریایی", "مین‌روبی", "فردو", "نطنز",
    "اصفهان", "اراک", "آژانس", "گروسی", "بازرس", "غنی‌سازی", "اورانیوم", "تحریم", "پول بلوکه",
    "موشک بالستیک", "موشک کروز", "پهپاد", "نتانیاهو", "اسرائیل کاتز", "حزب‌الله", "نوتام", "نفتکش",
)


def x_monitor_query() -> str:
    return _X_IRAN_QUERY


def is_monitored_x_topic(text: str) -> bool:
    value = (text or "").lower()
    return any(term in value for term in _MONITORED_TERMS)


def builtin_x_news_sources() -> tuple[dict[str, str], ...]:
    return tuple({"name": name, "handle": handle} for name, handle in _BUILTIN_X_NEWSROOMS)


def _normalise_x_created_at(value: object) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        dt = parsedate_to_datetime(raw)
    except Exception:
        try:
            dt = datetime.strptime(raw, "%a %b %d %H:%M:%S %z %Y")
        except ValueError:
            return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return format_datetime(dt.astimezone(timezone.utc))


def parse_x_syndication_html(page_html: str, source_name: str, handle: str) -> list[NewsItem]:
    """Parse the public X embed timeline and return only Iran-related posts from that profile."""
    match = _NEXT_DATA_RE.search(page_html or "")
    if not match:
        raise ValueError("X syndication __NEXT_DATA__ missing")
    payload = json.loads(html.unescape(match.group(1)))
    page_props = payload.get("props", {}).get("pageProps", {})
    entries = page_props.get("timeline", {}).get("entries")
    if not isinstance(entries, list):
        raise ValueError("X syndication timeline entries missing")

    display = f"{source_name} / X"
    screen_name = handle.lstrip("@")
    result: list[NewsItem] = []
    seen_ids: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        content = entry.get("content") if isinstance(entry.get("content"), dict) else {}
        tweet = content.get("tweet") if isinstance(content.get("tweet"), dict) else entry.get("tweet")
        if not isinstance(tweet, dict):
            continue
        post_id = str(tweet.get("id_str") or tweet.get("id") or "").strip()
        text = clean_x_post_text(str(tweet.get("full_text") or tweet.get("text") or ""))
        published = _normalise_x_created_at(tweet.get("created_at"))
        if not post_id or not text or not published or post_id in seen_ids:
            continue
        if not is_monitored_x_topic(text):
            continue
        seen_ids.add(post_id)
        result.append(NewsItem(
            f"x:{screen_name}:{post_id}",
            display,
            text,
            "",
            f"https://x.com/{screen_name}/status/{post_id}",
            published,
        ))
    return result


def _default_syndication_fetcher(source: dict[str, str], session=requests) -> str:
    handle = source["handle"].lstrip("@")
    response = session.get(
        f"{_X_SYNDICATION_BASE}/{handle}",
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
        timeout=15,
    )
    response.raise_for_status()
    return response.text


def _default_searcher(source: dict[str, str], session=requests) -> list[NewsItem]:
    handle = source["handle"].lstrip("@")
    label = f'{source["name"]} / X'
    query = f'{_X_IRAN_QUERY} site:x.com/{handle}'
    return _fetch_google_news_query(session, label, query, "en", allow_special_source=True)


def _google_fallback_items(source: dict[str, str], *, searcher, session=requests) -> list[NewsItem]:
    try:
        items = searcher(source) if searcher else _default_searcher(source, session=session)
    except Exception:
        return []
    normalized_items: list[NewsItem] = []
    for item in items[:20]:
        display = f'{source["name"]} / X'
        title = clean_x_post_text(item.title)
        summary = clean_x_post_text(item.summary)
        direct_link = resolve_x_post_url(item.link, source["handle"], session=session)
        if not direct_link:
            continue
        normalized = NewsItem(item.key, display, title, summary, direct_link, item.published)
        if is_monitored_x_topic(f"{normalized.title} {normalized.summary}"):
            normalized_items.append(normalized)
    return normalized_items


def fetch_builtin_x_news_items(*, searcher=None, syndication_fetcher=None, session=requests) -> list[NewsItem]:
    """Read monitored X profiles directly through X's public embed timeline; Google is fallback only."""
    merged: dict[str, NewsItem] = {}
    use_default_syndication = syndication_fetcher is None
    for index, source in enumerate(builtin_x_news_sources()):
        try:
            page_html = (
                syndication_fetcher(source)
                if syndication_fetcher
                else _default_syndication_fetcher(source, session=session)
            )
            items = parse_x_syndication_html(page_html, source["name"], source["handle"])
        except Exception as exc:
            print(f"X syndication fallback source={source['handle']!r} error={exc}")
            items = _google_fallback_items(source, searcher=searcher, session=session)

        for item in items:
            merged.setdefault(item.key, item)

        # Avoid hammering the public embed endpoint across the full monitored registry.
        if use_default_syndication and index + 1 < len(_BUILTIN_X_NEWSROOMS):
            time.sleep(0.20)
    return list(merged.values())
