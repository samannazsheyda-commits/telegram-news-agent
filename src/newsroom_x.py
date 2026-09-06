from __future__ import annotations

import html
import re

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
    ("Fox News", "@FoxNews"), ("The Guardian", "@guardian"),
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
    ("Scott Bessent", "@SecScottBessent"), ("Pete Hegseth", "@PeteHegseth"),
    ("Department of War", "@DeptofWar"),
    ("Marco Rubio", "@SecRubio"), ("JD Vance", "@VP"),
    ("US State Department", "@StateDept"), ("State Department Spokesperson", "@statedeptspox"),
    ("White House", "@WhiteHouse"),
    # Foreign reporters/analysts with recurring Iran, military, nuclear or sanctions coverage
    ("Mark Levin", "@marklevinshow"), ("Jason Brodsky", "@JasonMBrodsky"),
    ("Mark Dubowitz", "@mdubowitz"), ("Emanuel Fabian", "@manniefabian"),
    ("Seth Frantzman", "@sfrantzman"), ("Jonathan Conricus", "@jconricus"),
    ("Michael Doran", "@Doranimated"), ("Jennifer Hansler", "@jmhansler"),
    ("Joe Truzman", "@JoeTruzman"),
)

_PERSIAN_SOURCE_NAMES = {
    "Reuters": "رویترز", "Associated Press": "آسوشیتدپرس", "AFP": "خبرگزاری فرانسه",
    "BBC World": "بی‌بی‌سی ورلد", "CNN": "سی‌ان‌ان", "France 24": "فرانس ۲۴",
    "Al Jazeera English": "الجزیره انگلیسی", "Al Arabiya English": "العربیه انگلیسی",
    "The New York Times": "نیویورک تایمز", "NYT World": "نیویورک تایمز جهان",
    "Bloomberg": "بلومبرگ", "Financial Times": "فایننشال تایمز", "Sky News": "اسکای نیوز",
    "NBC News": "ان‌بی‌سی نیوز", "CBS News": "سی‌بی‌اس نیوز", "ABC News": "ای‌بی‌سی نیوز",
    "Fox News": "فاکس نیوز", "The Guardian": "گاردین",
    "Washington Post": "واشنگتن پست", "Wall Street Journal": "وال‌استریت ژورنال",
    "The Economist": "اکونومیست", "Times of Israel": "تایمز اسرائیل", "Haaretz": "هاآرتص",
    "Axios": "اکسیوس", "Jerusalem Post": "جروزالم پست", "Israel Hayom": "اسرائیل هیوم",
    "Benjamin Netanyahu": "بنیامین نتانیاهو", "Israel Katz": "اسرائیل کاتز",
    "KAN 11": "کانال ۱۱ اسرائیل", "N12": "کانال ۱۲ اسرائیل", "Channel 13": "کانال ۱۳ اسرائیل",
    "Channel 14": "کانال ۱۴ اسرائیل", "IDF": "ارتش اسرائیل", "CENTCOM": "سنتکام",
    "US Treasury": "وزارت خزانه‌داری آمریکا", "Scott Bessent": "اسکات بسنت",
    "Pete Hegseth": "پیت هگست", "Department of War": "وزارت جنگ آمریکا",
    "Marco Rubio": "مارکو روبیو", "JD Vance": "جی‌دی ونس",
    "US State Department": "وزارت خارجه آمریکا", "State Department Spokesperson": "سخنگوی وزارت خارجه آمریکا",
    "White House": "کاخ سفید", "Mark Levin": "مارک لوین", "Jason Brodsky": "جیسون برادسکی",
    "Mark Dubowitz": "مارک دوبوویتز", "Emanuel Fabian": "امانوئل فابیان", "Seth Frantzman": "ست فرانتزمن",
    "Jonathan Conricus": "جاناتان کانریکوس", "Michael Doran": "مایکل دوران", "Jennifer Hansler": "جنیفر هنسلر",
    "Joe Truzman": "جو تروزمن",
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


def clean_x_post_text(text: str) -> str:
    """Remove trailing secondary-media labels while preserving the actual post text."""
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
    """Resolve an indexed Google News result to the direct X status URL."""
    direct = _direct_x_status_url(link, handle)
    if direct:
        return direct
    if not link:
        return ""
    try:
        response = session.get(
            link,
            headers={"User-Agent": USER_AGENT},
            timeout=12,
            allow_redirects=True,
        )
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
    "netanyahu", "israel katz", "hezbollah", "notam", "tanker", "shipping",
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


def _default_searcher(source: dict[str, str], session=requests) -> list[NewsItem]:
    handle = source["handle"].lstrip("@")
    label = f'{source["name"]} / X'
    query = f'{_X_IRAN_QUERY} site:x.com/{handle}'
    return _fetch_google_news_query(session, label, query, "en", allow_special_source=True)


def fetch_builtin_x_news_items(*, searcher=None, session=requests) -> list[NewsItem]:
    merged: dict[str, NewsItem] = {}
    for source in builtin_x_news_sources():
        try:
            items = searcher(source) if searcher else _default_searcher(source, session=session)
        except Exception:
            continue
        for item in items[:20]:
            display = f'{source["name"]} / X'
            title = clean_x_post_text(item.title)
            summary = clean_x_post_text(item.summary)
            direct_link = resolve_x_post_url(item.link, source["handle"], session=session)
            if not direct_link:
                # Never publish an X item with a Google News or newsroom-site source link.
                continue
            normalized = NewsItem(item.key, display, title, summary, direct_link, item.published)
            if is_monitored_x_topic(f"{normalized.title} {normalized.summary}"):
                merged.setdefault(normalized.key, normalized)
    return list(merged.values())