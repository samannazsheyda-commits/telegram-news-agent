from __future__ import annotations

import re

from .editorial_rules import _specific_facts, _tokens
from .sources import NewsItem

_PROGRESS_TERMS = (
    "redirected", "disabled", "boarded", "seized", "intercepted", "destroyed",
    "تغییر مسیر", "از کار انداخته", "غیرفعال", "توقیف", "رهگیری", "منهدم",
)


def _progress_update_facts(item: NewsItem) -> set[str]:
    """Extract material counters/dates from rolling operational updates."""
    text = f"{item.title} {item.summary}".lower()
    if not any(term in text for term in _PROGRESS_TERMS):
        return set()

    facts: set[str] = set()
    for match in re.finditer(
        r"\b(\d+)\s+(commercial\s+)?(vessels?|ships?|tankers?)\b",
        text,
    ):
        facts.add(f"count:{match.group(1)}:{match.group(3)}")

    for match in re.finditer(
        r"\b(?:as of\s+)?(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sept?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?\s+(\d{1,2})\b",
        text,
    ):
        facts.add(f"date:{match.group(1)}:{match.group(2)}")
    return facts


def is_strict_duplicate_story(left: NewsItem, right: NewsItem) -> bool:
    """Return True only when two items describe the same underlying report.

    Broad shared context such as Iran/US/war is never enough by itself. A duplicate
    needs substantial lexical overlap after the project's canonical normalization.
    Materially changed operational counters/dates are treated as a new update.
    """
    a, b = _tokens(left), _tokens(right)
    if not a or not b:
        return False

    left_facts, right_facts = _specific_facts(left), _specific_facts(right)
    if (left_facts or right_facts) and left_facts != right_facts:
        return False

    left_progress = _progress_update_facts(left)
    right_progress = _progress_update_facts(right)
    if (left_progress or right_progress) and left_progress != right_progress:
        return False

    common = a & b
    overlap = len(common) / max(1, min(len(a), len(b)))
    return len(common) >= 5 and overlap >= 0.50
