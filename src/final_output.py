from __future__ import annotations

import re
from html import unescape

from .formatters import SOURCE_FA


_FLAG_RE = re.compile(r"(?:[\U0001F1E6-\U0001F1FF]{2})")
_HANDLE_RE = re.compile(r"(?<![\w/@])@[A-Za-z0-9_]{2,64}\b")
_HTML_SPLIT_RE = re.compile(r"(<[^>]+>)")
_LEGACY_BREAKING_RE = re.compile(
    r"^\s*💥\s*🔴\s*<b>خبر فوری</b>\s*\n\s*"
    r"(?:(?:🛑|🟥💥|🚨🚀|🟥|🔺|⚪️)\s*)?<b>([^<]+)</b>",
    re.MULTILINE,
)
COUNTRY_FLAG_RULES = (
    ("🇮🇷", ("iran", "iranian", "ایران", "ایرانی", "سپاه", "هرمز")),
    ("🇺🇸", ("united states", "u.s.", "american", "america", "آمریکا", "آمریکایی", "سنتکام")),
    ("🇮🇱", ("israel", "israeli", "اسرائیل", "اسرائیلی")),
    ("🇸🇦", ("saudi arabia", "saudi", "عربستان سعودی", "سعودی")),
    ("🇦🇪", ("united arab emirates", "uae", "امارات", "امارات متحده")),
    ("🇯🇴", ("jordan", "jordanian", "اردن", "اردنی")),
    ("🇾🇪", ("yemen", "yemeni", "houthi", "یمن", "یمنی", "حوثی")),
    ("🇮🇶", ("iraq", "iraqi", "عراق", "عراقی")),
    ("🇶🇦", ("qatar", "qatari", "قطر", "قطری")),
    ("🇧🇭", ("bahrain", "بحرین")),
    ("🇰🇼", ("kuwait", "کویت")),
    ("🇴🇲", ("oman", "عمان")),
    ("🇬🇧", ("united kingdom", "britain", "british", "بریتانیا", "انگلیس")),
    ("🇷🇺", ("russia", "russian", "روسیه", "روسی")),
    ("🇨🇳", ("china", "chinese", "چین", "چینی")),
    ("🇹🇷", ("turkey", "turkish", "ترکیه", "ترکی")),
    ("🇸🇾", ("syria", "syrian", "سوریه", "سوری")),
    ("🇱🇧", ("lebanon", "lebanese", "لبنان", "لبنانی")),
)


def _country_term_present(text: str, term: str) -> bool:
    if re.search(r"[a-z]", term):
        return bool(re.search(rf"(?<![a-z]){re.escape(term)}(?![a-z])", text, flags=re.IGNORECASE))
    return term in text


def _footer_flags(value: str) -> list[str]:
    visible = re.sub(r"<[^>]+>", " ", unescape(str(value or ""))).lower()
    flags = list(dict.fromkeys(_FLAG_RE.findall(visible)))
    for flag, terms in COUNTRY_FLAG_RULES:
        if flag in flags:
            continue
        if any(_country_term_present(visible, term) for term in terms):
            flags.append(flag)
        if len(flags) >= 4:
            break
    return flags[:4]


def _normalize_visible_fragment(value: str) -> str:
    text = unescape(str(value or ""))
    for source, fa_label in sorted(SOURCE_FA.items(), key=lambda pair: len(pair[0]), reverse=True):
        text = text.replace(source, fa_label)

    text = re.sub(r"(?i)\bBREAKING\b", "فوری", text)
    text = re.sub(r"(?i)\bURGENT\b", "فوری", text)
    text = re.sub(r"(?i)\bALERT\b", "هشدار", text)
    text = re.sub(r"(?i)(?<![A-Za-z])Telegram(?![A-Za-z])", "تلگرام", text)
    text = re.sub(r"(?i)(?<![A-Za-z])/\s*X(?![A-Za-z])", "/ ایکس", text)

    # Never leak an unknown ASCII aggregator label into the Persian final post.
    # The platform is metadata, not the public source name.
    text = re.sub(
        r"\b[A-Za-z][A-Za-z0-9 .&'_-]{1,80}\s*/\s*تلگرام(?=\s*:)",
        "منبع",
        text,
    )
    text = re.sub(
        r"\b[A-Za-z][A-Za-z0-9 .&'_-]{1,80}\s*/\s*ایکس(?=\s*:)",
        "منبع",
        text,
    )

    text = _HANDLE_RE.sub("", text)
    # Flags are removed from headline/body here and reattached once at the end.
    text = _FLAG_RE.sub("", text)
    text = text.replace("⚡️", "").replace("⚡", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\s+([،,:؛.!؟])", r"\1", text)
    text = re.sub(r":\s*[-–—]+\s*", ": ", text)
    return text


def _normalize_visible_html(value: str) -> str:
    chunks = _HTML_SPLIT_RE.split(str(value or ""))
    output: list[str] = []
    for chunk in chunks:
        if not chunk:
            continue
        if chunk.startswith("<") and chunk.endswith(">"):
            output.append(chunk)
        else:
            output.append(_normalize_visible_fragment(chunk))
    return "".join(output)


def _collapse_legacy_breaking_header(value: str) -> str:
    def repl(match: re.Match[str]) -> str:
        headline = re.sub(r"\s+", " ", match.group(1)).strip()
        return f"💥 🔴 <b>خبر فوری | {headline}</b>"

    return _LEGACY_BREAKING_RE.sub(repl, value, count=1)


def _normalize_layout(value: str) -> str:
    lines: list[str] = []
    previous_blank = False
    for raw_line in str(value or "").split("\n"):
        line = re.sub(r"[ \t]+", " ", raw_line).strip()
        if not line:
            if lines and not previous_blank:
                lines.append("")
            previous_blank = True
            continue
        previous_blank = False
        lines.append(line)

    output: list[str] = []
    for line in lines:
        if line.startswith("⏰ ") and output and output[-1] != "":
            output.append("")
        if line.startswith("📡 ") and output and output[-1] != "":
            output.append("")
        output.append(line)

    compact: list[str] = []
    for line in output:
        if line == "" and (not compact or compact[-1] == ""):
            continue
        compact.append(line)
    return "\n".join(compact).strip()


def finalize_telegram_message(value: str) -> str:
    """Single last-mile formatter guard for every Telegram-bound news message.

    The guard is idempotent: source labels are Persianized, handles/noisy flags
    are removed from the body, article layout is normalized, and relevant
    country flags are placed exactly once at the very bottom.
    """
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("&#10;", "\n").replace("&#xA;", "\n")
    flags = _footer_flags(text)
    text = _normalize_visible_html(text)
    text = _collapse_legacy_breaking_header(text)
    text = _normalize_layout(text)
    if flags:
        text = f"{text.rstrip()}\n\n{' '.join(flags)}"
    return text
