from __future__ import annotations

import re

_LATIN_WORD_RE = re.compile(r"\b[A-Za-z]{2,}\b")
_LEADING_DECOR_RE = re.compile(
    r"^[\s\u200e\u200f]*(?:[\U0001F1E6-\U0001F1FF]{2}|[\U0001F300-\U0001FAFF]|"
    r"[❌❗‼️⚠️✅☑️✳️✴️⭐️•▪️▫️◾️◽️]+|[-–—|:])+[\s\u200e\u200f]*"
)
_PROMO_PATTERNS = (
    r"\bwatch\b.*\bsession\b",
    r"\bcatch\b.*\bsession\b",
    r"\bweekend festival\b",
    r"\bjoin us\b",
    r"\bregister now\b",
    r"\bsign up\b",
    r"\bsubscribe\b",
    r"\blisten to (?:our|the) podcast\b",
    r"\bwatch (?:the|our|their) (?:full )?(?:video|interview|conversation)\b",
    r"تماشا کنید",
    r"ثبت.?نام کنید",
    r"مشترک شوید",
    r"پادکست را بشنوید",
    r"جشنواره",
)

_PERSIAN_REPAIRS = (
    ("در بالای تنگه هرمز", "در محدوده تنگه هرمز"),
    ("بالای تنگه هرمز", "در محدوده تنگه هرمز"),
    ("ایالات متحده", "آمریکا"),
    ("اسرائيل", "اسرائیل"),
    ("ي", "ی"),
    ("ك", "ک"),
)

_KNOWN_LATIN = {
    "US": "آمریکا",
    "USA": "آمریکا",
    "CENTCOM": "سنتکام",
    "IRGC": "سپاه پاسداران",
    "IAEA": "آژانس بین‌المللی انرژی اتمی",
    "BBC": "بی‌بی‌سی",
    "CNN": "سی‌ان‌ان",
    "NBC": "ان‌بی‌سی",
    "ABC": "ای‌بی‌سی",
    "CBS": "سی‌بی‌اس",
    "FT": "فایننشال تایمز",
    "IDF": "ارتش اسرائیل",
    "UAV": "پهپاد",
    "NOTAM": "نوتام",
}


def strip_leading_decorative_emoji(text: str) -> str:
    value = (text or "").strip()
    previous = None
    while previous != value:
        previous = value
        value = _LEADING_DECOR_RE.sub("", value).strip()
    return value


def is_promotional_news_text(text: str) -> bool:
    value = (text or "").lower()
    return any(re.search(pattern, value, flags=re.I) for pattern in _PROMO_PATTERNS)


def _replace_known_latin(text: str) -> str:
    value = text or ""
    for latin, persian in sorted(_KNOWN_LATIN.items(), key=lambda item: len(item[0]), reverse=True):
        value = re.sub(rf"\b{re.escape(latin)}\b", persian, value, flags=re.I)
    return value


def _normalize_persian(text: str) -> str:
    value = _replace_known_latin((text or "").strip())
    for old, new in _PERSIAN_REPAIRS:
        value = value.replace(old, new)
    value = re.sub(r"\s+([،؛:.!?؟])", r"\1", value)
    value = re.sub(r"([،؛])([^\s])", r"\1 \2", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def trim_to_complete_sentences(text: str, max_chars: int | None = None) -> str:
    value = re.sub(r"\s+", " ", (text or "").strip())
    if not value:
        return ""
    if max_chars is None or len(value) <= max_chars:
        return value
    cut = value[:max_chars].rstrip()
    matches = list(re.finditer(r"[.!؟!?…](?=\s|$)", cut))
    if not matches:
        return ""
    return cut[: matches[-1].end()].strip()


def has_forbidden_latin_body(text: str) -> bool:
    return bool(_LATIN_WORD_RE.search(text or ""))


def _protected_numbers(text: str) -> list[str]:
    return re.findall(r"\d+(?:[.,]\d+)?", text or "")


def _preserves_numbers(source: str, edited: str) -> bool:
    source_numbers = _protected_numbers(source)
    if not source_numbers:
        return True
    trans = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
    return all(number in edited or number.translate(trans) in edited for number in source_numbers)


def edit_news_text(source_text: str, translated_text: str, *, max_chars: int = 700) -> str:
    source = strip_leading_decorative_emoji(source_text)
    translated = strip_leading_decorative_emoji(translated_text)
    if not source or not translated:
        return ""
    if is_promotional_news_text(source) or is_promotional_news_text(translated):
        return ""

    value = _normalize_persian(translated)
    if len(value) > max_chars:
        value = trim_to_complete_sentences(value, max_chars=max_chars)
    if value.endswith(("...", "…")):
        value = trim_to_complete_sentences(value[:-1].rstrip(), max_chars=len(value))
    if not value:
        return ""
    if not _preserves_numbers(source, value):
        return ""
    if has_forbidden_latin_body(value):
        return ""
    return value
