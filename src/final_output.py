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
    text = re.sub(
        r"\b[A-Za-z][A-Za-z0-9 .&'_-]{1,80}\s*/\s*تلگرام(?=\s*:)",
        "منبع تلگرامی",
        text,
    )
    text = re.sub(
        r"\b[A-Za-z][A-Za-z0-9 .&'_-]{1,80}\s*/\s*ایکس(?=\s*:)",
        "منبع در ایکس",
        text,
    )

    text = _HANDLE_RE.sub("", text)
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

    # Remove duplicate blank lines introduced by legacy paths.
    compact: list[str] = []
    for line in output:
        if line == "" and (not compact or compact[-1] == ""):
            continue
        compact.append(line)
    return "\n".join(compact).strip()


def finalize_telegram_message(value: str) -> str:
    """Single last-mile formatter guard for every Telegram-bound news message.

    The guard is intentionally idempotent so both the normal publisher and
    emergency broadcast path can run it without changing already-correct
    output. It preserves Telegram HTML while Persianizing visible source labels,
    removing noisy handles/flags, collapsing the legacy two-line breaking
    header, and enforcing the standard readable layout.
    """
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("&#10;", "\n").replace("&#xA;", "\n")
    text = _normalize_visible_html(text)
    text = _collapse_legacy_breaking_header(text)
    return _normalize_layout(text)
