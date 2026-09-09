from __future__ import annotations

import re

from .newsroom_models import NormalizedNewsItem, RawNewsItem


ACTOR_ALIASES = {
    "Donald Trump": ("donald trump", "trump"),
    "CENTCOM": ("centcom", "u.s. central command", "us central command"),
    "White House": ("white house",),
    "Mohsen Rezaei": ("mohsen rezaei", "محسن رضایی"),
    "Abbas Araghchi": ("abbas araghchi", "abbas araqchi", "عباس عراقچی"),
}

LOCATION_ALIASES = {
    "Strait of Hormuz": ("strait of hormuz", "هرمز", "تنگه هرمز"),
    "Iran": ("iran", "iranian", "ایران", "ایرانی"),
    "Spain": ("spain", "spanish", "اسپانیا"),
    "Jordan": ("jordan", "jordanian", "اردن"),
    "Qeshm": ("qeshm", "قشم"),
    "Sirik": ("sirik", "سیریک"),
    "Bandar Abbas": ("bandar abbas", "bandarabbas", "بندرعباس", "بندر عباس"),
    "Bushehr": ("bushehr", "بوشهر"),
    "Jask": ("jask", "جاسک"),
    "Assaluyeh": ("assaluyeh", "asalouyeh", "عسلویه"),
    "Bandar Deyr": ("bandar deyr", "deyr", "بندر دیر", "دیر"),
    "Tehran": ("tehran", "تهران"),
    "Isfahan": ("isfahan", "esfahan", "اصفهان"),
    "Shiraz": ("shiraz", "شیراز"),
    "Natanz": ("natanz", "نطنز"),
    "Fordow": ("fordow", "fordo", "فردو"),
}

ACTION_PATTERNS = (
    ("announce_restricted_zone", r"\b(?:announce|announces|announced|establish|establishes|create|creates)\b[^.]{0,80}\b(?:restricted|exclusion) zone\b|منطقه (?:محدود|ممنوع)"),
    ("close_airspace", r"\b(?:close|closes|closed|shut|shuts)\b[^.]{0,40}\bairspace\b|بستن حریم هوایی|حریم هوایی بسته"),
    ("reopen_airspace", r"\b(?:reopen|reopens|reopened)\b[^.]{0,40}\bairspace\b|بازگشایی حریم هوایی|حریم هوایی باز"),
    ("intercept", r"\bintercept(?:s|ed|ing)?\b|رهگیر|رهگیری"),
    ("redirect_vessels", r"\bredirect(?:s|ed|ing)?\b[^.]{0,60}\b(?:vessels?|ships?)\b|تغییر مسیر"),
    ("strike", r"\b(?:strike|strikes|struck|attack|attacks|attacked)\b|حمله"),
    ("explosion", r"\b(?:explosion|explosions|blast|blasts|detonation|detonations)\b|انفجار|انفجارها|انفجارهایی"),
)


def _normalize_text(value: str) -> str:
    text = re.sub(r"\s+", " ", (value or "").strip().lower())
    return text.replace("ي", "ی").replace("ك", "ک")


def _extract_aliases(text: str, aliases: dict[str, tuple[str, ...]]) -> list[str]:
    found: list[str] = []
    for canonical, values in aliases.items():
        if any(alias in text for alias in values):
            found.append(canonical)
    return found


def _extract_actions(text: str) -> list[str]:
    actions: list[str] = []
    for name, pattern in ACTION_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            actions.append(name)
    return actions


def _extract_numbers(text: str) -> list[str]:
    return re.findall(r"(?<![\w.])\d+(?:\.\d+)?(?![\w.])", text)


def _extract_objects(text: str) -> list[str]:
    objects: list[str] = []
    if "commercial vessel" in text or "commercial vessels" in text or "کشتی تجاری" in text:
        objects.append("commercial vessels")
    if "airspace" in text or "حریم هوایی" in text:
        objects.append("airspace")
    if "missile" in text or "موشک" in text:
        objects.append("missiles")
    if "tanker" in text or "نفتکش" in text:
        objects.append("tankers")
    if "restricted zone" in text or "exclusion zone" in text or "منطقه محدود" in text or "منطقه ممنوع" in text:
        objects.append("restricted zone")
    if any(term in text for term in ("explosion", "explosions", "blast", "blasts", "detonation", "انفجار")):
        objects.append("explosions")
    return objects


def _extract_topics(text: str) -> list[str]:
    topics: list[str] = []
    if "hormuz" in text or "هرمز" in text:
        topics.append("hormuz")
    if any(term in text for term in ("missile", "strike", "attack", "centcom", "warship", "explosion", "blast", "موشک", "حمله", "انفجار")):
        topics.append("security")
    if "airspace" in text or "حریم هوایی" in text:
        topics.append("airspace")
    return topics


def normalize_item(item: RawNewsItem) -> NormalizedNewsItem:
    normalized_text = _normalize_text(f"{item.title} {item.summary}")
    return NormalizedNewsItem(
        raw=item,
        actors=_extract_aliases(normalized_text, ACTOR_ALIASES),
        locations=_extract_aliases(normalized_text, LOCATION_ALIASES),
        actions=_extract_actions(normalized_text),
        objects=_extract_objects(normalized_text),
        numeric_facts=_extract_numbers(normalized_text),
        topic_tags=_extract_topics(normalized_text),
        quoted_speaker="",
        normalized_text=normalized_text,
    )
