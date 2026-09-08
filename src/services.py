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
    ("موفق سالتی", "موفق السلطی"),
    ("موفق سالتی", "موفق السلطی"),
    ("موفق سلتی", "موفق السلطی"),
    ("موفق صلتی", "موفق السلطی"),
    ("Muwaffaq Salti", "موفق السلطی"),
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
        "پافشاری کرد",
    ),
    (
        "walked back",
        ("راه رفت", "به عقب راه رفت", "عقب رفت"),
        "عقب‌نشینی کرد",
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

    if (
        "may not be a nuclear deal with iran" in source_lower
        and "ability to build bomb may be destroyed" in source_lower
    ):
        return (
            "یک مقام ارشد آمریکایی: ممکن است توافق هسته‌ای با ایران به‌زودی حاصل نشود، "
            "اما آمریکا می‌تواند توان ایران برای ساخت سلاح هسته‌ای را از بین ببرد"
        )

    for idiom, bad_phrases, replacement in IDIOM_REPAIRS:
        if idiom not in source_lower:
            continue
        for bad in bad_phrases:
            value = value.replace(bad, replacement)
    return value


def translate_to_fa(text: str, session=requests) -> str:
    value = (text or "").strip()
    if not value:
        return ""
    if has_persian(value):
        return _polish_fa(value)
    translated = ""
    for translator in (_google_translate, _mymemory_translate):
        try:
            translated = translator(value, session=session)
        except Exception:
            continue
        if translated and has_persian(translated):
            break
    if not translated:
        return ""
    translated = _repair_news_idioms(value, translated)
    return _polish_fa(translated)


def _telegram_api_url(token: str, method: str) -> str:
    return f"https://api.telegram.org/bot{token}/{method}"


def send_telegram(text: str, token: str, chat_id: str, session=requests, *, video_url: str = "", photo_url: str = "") -> dict[str, Any]:
    token = (token or "").strip()
    chat_id = (chat_id or "").strip()
    if not token or not chat_id:
        raise RuntimeError("telegram_not_configured")
    media_url = (video_url or "").strip()
    if media_url:
        response = session.post(
            _telegram_api_url(token, "sendVideo"),
            data={"chat_id": chat_id, "video": media_url, "caption": text, "parse_mode": "HTML", "supports_streaming": True},
            timeout=30,
        )
    elif (photo_url or "").strip():
        response = session.post(
            _telegram_api_url(token, "sendPhoto"),
            data={"chat_id": chat_id, "photo": (photo_url or "").strip(), "caption": text, "parse_mode": "HTML"},
            timeout=30,
        )
    else:
        response = session.post(
            _telegram_api_url(token, "sendMessage"),
            data={"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True},
            timeout=30,
        )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("ok"):
        raise RuntimeError(str(payload))
    return payload


def load_json(path: str | Path, default: Any) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default


def save_json(path: str | Path, value: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sleep_seconds(seconds: int | float) -> None:
    time.sleep(max(0.0, float(seconds)))
