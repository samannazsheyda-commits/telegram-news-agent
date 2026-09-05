from __future__ import annotations

from .editorial_rules import _specific_facts, _tokens
from .sources import NewsItem


def is_strict_duplicate_story(left: NewsItem, right: NewsItem) -> bool:
    """Return True only when two items describe the same underlying report.

    Broad shared context such as Iran/US/war is never enough by itself. A duplicate
    needs substantial lexical overlap after the project's canonical normalization.
    """
    a, b = _tokens(left), _tokens(right)
    if not a or not b:
        return False

    left_facts, right_facts = _specific_facts(left), _specific_facts(right)
    if (left_facts or right_facts) and left_facts != right_facts:
        return False

    common = a & b
    overlap = len(common) / max(1, min(len(a), len(b)))
    return len(common) >= 5 and overlap >= 0.50
