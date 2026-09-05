from __future__ import annotations

import requests

from .sources import NewsItem, _fetch_google_news_query


_BUILTIN_X_NEWSROOMS = (
    ("Reuters", "@Reuters"), ("Associated Press", "@AP"), ("AFP", "@AFP"),
    ("BBC World", "@BBCWorld"), ("CNN", "@CNN"), ("France 24", "@FRANCE24"),
    ("Al Jazeera English", "@AJEnglish"), ("Al Arabiya English", "@AlArabiya_Eng"),
    ("The New York Times", "@nytimes"), ("NYT World", "@nytimesworld"),
    ("Bloomberg", "@business"), ("Financial Times", "@FT"), ("Sky News", "@SkyNews"),
    ("NBC News", "@NBCNews"), ("CBS News", "@CBSNews"), ("ABC News", "@ABC"),
    ("Fox News", "@FoxNews"), ("DW News", "@dwnews"), ("The Guardian", "@guardian"),
    ("Washington Post", "@washingtonpost"), ("Wall Street Journal", "@WSJ"),
    ("Times of Israel", "@TimesofIsrael"), ("Haaretz", "@haaretzcom"), ("Axios", "@axios"),
    ("Jerusalem Post", "@Jerusalem_Post"), ("Israel Hayom", "@IsraelHayomEng"),
    ("Benjamin Netanyahu", "@netanyahu"), ("Israel Katz", "@Israel_katz"),
    ("KAN 11", "@kann_news"), ("N12", "@N12News"), ("Channel 13", "@newsisrael13"),
    ("Channel 14", "@C14_news"), ("IDF", "@IDF"),
    ("CENTCOM", "@CENTCOM"), ("US Treasury", "@USTreasury"),
    ("Scott Bessent", "@SecScottBessent"), ("US Secretary of Defense", "@SecDef"),
    ("US State Department", "@StateDept"), ("State Department Spokesperson", "@statedeptspox"),
    ("White House", "@WhiteHouse"),
    ("Mark Levin", "@marklevinshow"), ("Jason Brodsky", "@JasonMBrodsky"),
    ("Tasnim Persian", "@Tasnimnews_Fa"), ("Tasnim English", "@Tasnimnews_EN"),
)

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
    "arabian sea", "abraham lincoln", "uss boxer", "carrier strike group", "fifth fleet", "navcent",
    "minelaying", "mine laying", "naval mine", "mine countermeasures", "al udeid", "al dhafra",
    "diego garcia", "fordow", "natanz", "isfahan", "arak", "iaea", "grossi", "centrifuge",
    "enrichment", "uranium", "ofac", "frozen funds", "blocked funds", "ballistic missile",
    "cruise missile", "netanyahu", "israel katz", "hezbollah", "notam",
    "ایران", "تهران", "سپاه", "نیروی قدس", "هرمز", "خلیج فارس", "ناوگان پنجم", "مین دریایی",
    "فردو", "نطنز", "اصفهان", "اراک", "آژانس", "گروسی", "غنی‌سازی", "اورانیوم", "تحریم",
    "پول بلوکه", "موشک بالستیک", "موشک کروز", "نتانیاهو", "اسرائیل کاتز", "حزب‌الله", "نوتام",
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
