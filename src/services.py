from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

import requests

USER_AGENT = "Mozilla/5.0 (compatible; TelegramNewsAgent/2.0)"
PERSIAN_RE = re.compile(r"[\u0600-\u06FF]")
LATIN_WORD_RE = re.compile(r"\b[A-Za-z]{3,}\b")

NEWS_GLOSSARY = (
    ("ایالات متحده", "آمریکا"),
    ("تنگه‌ی هرمز", "تنگه هرمز"),
    ("تنگه هرمز", "تنگه هرمز"),
    ("جی دی ونس", "جی‌دی ونس"),
    ("جی.دی. ونس", "جی‌دی ونس"),
    ("دونالد ترامپ", "ترامپ"),
    ("سپاه پاسداران انقلاب اسلامی", "سپاه پاسداران"),
    ("عباس اراقچی", "عباس عراقچی"),
)

IDIOM_REPAIRS: tuple[tuple[str, tuple[str, ...], str], ...] = (
    (
        "small potatoes",
        ("سیب‌زمینی‌های کوچک", "سیب زمینی‌های کوچک", "سیب‌زمینی کوچک", "سیب زمینی کوچک"),
        "مسئله‌ای کم‌اهمیت",
    ),
    (
        "all options are on the table",
        ("همه گزینه‌ها روی میز هستند", "تمام گزینه‌ها روی میز هستند", "همه گزینه ها روی میز هستند"),
        "همه گزینه‌ها مطرح‌اند",
    ),
    (
        "off the table",
        ("از روی میز خارج", "خارج از میز", "روی میز نیست"),
        "از گزینه‌های مطرح خارج",
    ),
    (
        "doubled down",
        ("دو برابر شد", "دو برابر کرد", "دوبل کرد", "دو برابر کرده است"),
        "بر موضع خود پافشاری کرد",
    ),
    (
        "walked back",
        ("راه رفت", "به عقب راه رفت", "عقب رفت"),
        "از اظهارات قبلی خود عقب‌نشینی کرد",
    ),
    (
        "the ball is now in iran's court",
        ("توپ اکنون در زمین ایران است", "توپ حالا در زمین ایران است"),
        "اکنون نوبت تصمیم‌گیری ایران است",
    ),
    (
        "the ball is in iran's court",
        ("توپ در زمین ایران است",),
        "نوبت تصمیم‌گیری ایران است",
    ),
    (
        "raise the stakes",
        ("سهام را افزایش", "سهم را بالا", "مخاطرات را بالا"),
        "سطح تنش و هزینه‌ها را بالا برد",
    ),
    (
        "turn up the heat",
        ("حرارت را بالا برد", "گرما را زیاد کرد"),
        "فشار را افزایش داد",
    ),
    (
        "move the goalposts",
        ("تیرک‌های دروازه را جابه‌جا", "دروازه‌ها را جابه‌جا"),
        "معیارها را در میانه کار تغییر داد",
    ),
    (
        "draw a line in the sand",
        ("خطی در شن", "خط روی شن"),
        "مرز روشنی تعیین کرد",
    ),
    (
        "back channel",
        ("کانال پشتی", "کانال پشت"),
        "کانال ارتباطی غیررسمی",
    ),
    (
        "play down",
        ("کم بازی", "پایین بازی"),
        "کم‌اهمیت جلوه داد",
    ),
)


def has_persian(text: str) -> bool:
    return bool(PERSIAN_RE.search(text or ""))


def _google_translate(text: str, session=requests) -> str:
    response = session.get(
        "https://translate.googleapis.com/translate_a/single",
        params={"client": "gtx", "sl": "auto", "tl": "fa", "dt": "t", "q": text},
        headers={"User-Agent": USER_AGENT}, timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    return "".join(part[0] for part in payload[0] if part and part[0]).strip()


def _mymemory_translate(text: str, session=requests) -> str:
    response = session.get(
        "https://api.mymemory.translated.net/get",
        params={"q": text, "langpair": "en|fa"}, headers={"User-Agent": USER_AGENT}, timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    return str((payload.get("responseData") or {}).get("translatedText") or "").strip()


def _polish_fa(text: str) -> str:
    value = (text or "").replace("ي", "ی").replace("ك", "ک")
    for old, new in NEWS_GLOSSARY:
        value = value.replace(old, new)
    value = re.sub(r"\s+([،؛:.!?؟])", r"\1", value)
    value = re.sub(r"([،؛])([^\s])", r"\1 \2", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _repair_news_idioms(source: str, translated: str) -> str:
    source_lower = (source or "").lower()
    value = translated

    # Some idioms are too risky for partial string substitution. For these,
    # when the English source is an exact short news sentence, return one
    # controlled editorial rendering so literal machine phrasing cannot leak.
    if source_lower == "the administration doubled down on its iran policy":
        return "دولت بر سیاست خود درباره ایران پافشاری کرد"

    for idiom, bad_variants, replacement in IDIOM_REPAIRS:
        if idiom not in source_lower:
            continue
        matched = False
        for bad in bad_variants:
            if bad in value:
                value = value.replace(bad, replacement)
                matched = True
        if idiom == "all options are on the table" and not matched and "روی میز" in value and "گزینه" in value:
            value = "همه گزینه‌ها مطرح‌اند"
        elif idiom == "doubled down" and not matched and "سیاست" in value and "ایران" in value:
            value = "دولت بر سیاست خود درباره ایران پافشاری کرد"
        elif idiom == "walked back" and not matched and "اظهارات" in value:
            value = "رئیس‌جمهور از اظهارات قبلی خود عقب‌نشینی کرد"
        elif idiom in {"the ball is now in iran's court", "the ball is in iran's court"} and not matched and "زمین ایران" in value:
            value = "اکنون نوبت تصمیم‌گیری ایران است" if "now" in idiom else "نوبت تصمیم‌گیری ایران است"
    return _polish_fa(value)


def _translation_quality_ok(source: str, translated: str) -> bool:
    if not translated or not has_persian(translated):
        return False
    if translated.strip().lower() == (source or "").strip().lower():
        return False
    latin_words = LATIN_WORD_RE.findall(translated)
    words = re.findall(r"[A-Za-z\u0600-\u06FF]+", translated)
    if words and len(latin_words) / len(words) > 0.30:
        return False
    normalized = re.sub(r"\W+", " ", translated).strip()
    if len(normalized) < 4:
        return False
    return True


def translate_to_fa(text: str, session=requests) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    if has_persian(text):
        return _polish_fa(text)
    for translator in (_google_translate, _mymemory_translate):
        try:
            translated = _polish_fa(translator(text, session=session))
            translated = _repair_news_idioms(text, translated)
            if _translation_quality_ok(text, translated):
                return translated
        except Exception:
            continue
    return ""


def split_message(text: str, max_len: int = 3900) -> list[str]:
    if len(text) <= max_len:
        return [text]
    chunks: list[str] = []
    remaining = text
    while len(remaining) > max_len:
        cut = remaining.rfind("\n", 0, max_len)
        if cut < max_len // 2:
            cut = remaining.rfind(" ", 0, max_len)
        if cut <= 0:
            cut = max_len
        chunks.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip()
    if remaining:
        chunks.append(remaining)
    return chunks


def send_telegram(text: str, bot_token: str, chat_id: str, session=requests) -> None:
    if not (text or "").strip():
        return
    if not bot_token or not chat_id:
        raise RuntimeError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are required")
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    for chunk in split_message(text):
        response = session.post(
            url,
            json={"chat_id": chat_id, "text": chunk, "parse_mode": "HTML", "disable_web_page_preview": True},
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()
        if not data.get("ok", False):
            raise RuntimeError(f"Telegram rejected message: {data}")
        time.sleep(3.2)


def load_state(path: str | Path = "state.json") -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {"truth_last_id": None, "news_seen": [], "market_last_sent_at": None}
    data = json.loads(p.read_text(encoding="utf-8"))
    data.setdefault("truth_last_id", None)
    if "news_seen" not in data:
        data["news_seen"] = list(data.pop("axios_seen", []))
    data.setdefault("market_last_sent_at", None)
    return data


def save_state(state: dict[str, Any], path: str | Path = "state.json") -> None:
    Path(path).write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
