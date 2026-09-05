from __future__ import annotations

import requests

from . import formatters as _formatters
from .sources import NewsItem, _fetch_google_news_query


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
    ("Joe Truzman", "@JoeTruzman"),
    # Iranian newsrooms only — no Iranian commentators
    ("Tasnim Persian", "@Tasnimnews_Fa"), ("Tasnim English", "@Tasnimnews_EN"),
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
    "Joe Truzman": "جو تروزمن", "Tasnim Persian": "تسنیم", "Tasnim English": "تسنیم انگلیسی",
}
for _name, _fa in _PERSIAN_SOURCE_NAMES.items():
    _formatters.SOURCE_FA[f"{_name} / X"] = f"{_fa} / ایکس"

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
            normalized = item if item.source.endswith(" / X") else NewsItem(
                item.key, display, item.title, item.summary, item.link, item.published
            )
            if is_monitored_x_topic(f"{normalized.title} {normalized.summary}"):
                merged.setdefault(normalized.key, normalized)
    return list(merged.values())
