from __future__ import annotations

import re

_CONTEXT_DEPENDENT_RE = re.compile(
    r"\b(?:these|those|the above|the below|this|that)\s+"
    r"(?:figures?|numbers?|data|rates?|totals?|exports?|shipments?|countries|cases|points?)\b|"
    r"\b(?:most|some|all|none)\s+of\s+them\b|"
    r"\b(?:as noted|as mentioned|as shown|as stated)\s+(?:above|below|earlier|previously)\b",
    re.IGNORECASE,
)

_REPORT_HEADLINE_RE = re.compile(
    r"^(?:the\s+)?(?:risky|dangerous|high[- ]risk|fraught|difficult)?\s*"
    r"(?:mission|challenge|race|battle|quest)\s+to\b|"
    r"^(?:inside|how|why|what it takes to)\b",
    re.IGNORECASE,
)

_NEWS_ACTION_RE = re.compile(
    r"\b(?:says?|said|announces?|announced|confirms?|confirmed|warns?|warned|"
    r"attacks?|attacked|strikes?|struck|kills?|killed|seizes?|seized|closes?|closed|"
    r"opens?|opened|enters?|entered|deploys?|deployed|launches?|launched|"
    r"approves?|approved|rejects?|rejected|agrees?|agreed|halts?|halted)\b",
    re.IGNORECASE,
)


def rejection_reason(text: str, source_name: str = "") -> str | None:
    value = re.sub(r"\s+", " ", (text or "").strip())
    if not value:
        return "empty"
    if _CONTEXT_DEPENDENT_RE.search(value):
        return "context_dependent_fragment"
    if len(value) <= 180 and _REPORT_HEADLINE_RE.search(value) and not _NEWS_ACTION_RE.search(value):
        return "report_or_feature_headline"
    return None


def is_publishable_x_text(text: str, source_name: str = "") -> bool:
    return rejection_reason(text, source_name) is None
