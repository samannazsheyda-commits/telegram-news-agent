from __future__ import annotations

import re


_CLASH_REPORT_ALIASES = {
    "clash report",
    "clashreport",
    "@clashreport",
}


def canonical_news_source(raw: str) -> str:
    value = re.sub(r"\s+", " ", str(raw or "")).strip()
    normalized = value.lower()
    if normalized in _CLASH_REPORT_ALIASES:
        return "Clash Report"
    return value
