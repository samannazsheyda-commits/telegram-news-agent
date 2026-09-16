from __future__ import annotations

import re


_REPORT_PREFIXES = (
    "report:",
    "report -",
    "special report:",
    "special report -",
    "گزارش:",
    "گزارش -",
    "گزارش ویژه:",
    "گزارش ویژه -",
)


def hard_editorial_rejection(title: str, summary: str = "") -> str:
    """Return a deterministic rejection reason for obvious report-style material."""
    clean_title = re.sub(r"\s+", " ", str(title or "")).strip().lower()
    if clean_title.startswith(_REPORT_PREFIXES):
        return "filtered_question_or_article"
    return ""
