from __future__ import annotations

import re

from .formatters import SOURCE_FA

_FLAG_RE = re.compile(r"(?:[\U0001F1E6-\U0001F1FF]{2})")
_HANDLE_RE = re.compile(r"(?<![\w/@])@[A-Za-z0-9_]{2,64}\b")


def normalize_urgent_message(value: str) -> str:
    """Normalize the final emergency Telegram HTML without destroying links/markup.

    Emergency broadcasts used to bypass the normal news formatter entirely.
    This last-mile guard keeps the visible output Persian and removes raw
    aggregator noise while preserving intentional Telegram HTML links.
    """
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("&#10;", "\n").replace("&#xA;", "\n")

    for source, fa_label in sorted(SOURCE_FA.items(), key=lambda pair: len(pair[0]), reverse=True):
        text = text.replace(source, fa_label)

    text = re.sub(r"(?i)\bBREAKING\b", "فوری", text)
    text = re.sub(r"(?i)\bURGENT\b", "فوری", text)
    text = re.sub(r"(?i)\bALERT\b", "هشدار", text)
    text = re.sub(r"(?i)(?<![A-Za-z])Telegram(?![A-Za-z])", "تلگرام", text)
    text = re.sub(r"(?i)(?<![A-Za-z])/\s*X(?![A-Za-z])", "/ ایکس", text)
    text = _HANDLE_RE.sub("", text)
    text = _FLAG_RE.sub("", text)

    lines: list[str] = []
    previous_blank = False
    for raw_line in text.split("\n"):
        line = re.sub(r"[ \t]+", " ", raw_line).strip()
        line = re.sub(r"\s+([،,:؛.!؟])", r"\1", line)
        if not line:
            if not previous_blank and lines:
                lines.append("")
            previous_blank = True
            continue
        previous_blank = False
        lines.append(line)

    return "\n".join(lines).strip()
