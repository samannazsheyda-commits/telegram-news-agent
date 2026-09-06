from __future__ import annotations

import re

from .editorial_rules import _specific_facts, _tokens
from .sources import NewsItem

_PROGRESS_TERMS = (
    "redirected", "rerouted", "diverted", "disabled", "boarded", "seized", "intercepted", "destroyed",
    "تغییر مسیر", "از کار انداخته", "از کار انداخت", "غیرفعال", "توقیف", "رهگیری", "منهدم",
)

_DIGIT_MAP = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

_ACTION_ALIASES = {
    "redirected": ("redirected", "rerouted", "diverted", "تغییر مسیر"),
    "disabled": ("disabled", "غیرفعال", "از کار انداخته", "از کار انداخت"),
    "boarded": ("boarded", "seized", "detained", "توقیف", "بازرسی"),
    "intercepted": ("intercepted", "رهگیری"),
    "destroyed": ("destroyed", "منهدم", "نابود"),
}

_CONTEXT_ALIASES = {
    "iran": ("iran", "iranian", "ایران", "ایرانی"),
    "centcom": ("centcom", "central command", "سنتکام"),
    "maritime": ("maritime", "vessel", "ship", "tanker", "navy", "کشتی", "شناور", "دریایی"),
    "blockade": ("blockade", "محاصره"),
}

_NUMBER_RE = re.compile(r"(?<![A-Za-z0-9])\d+(?![A-Za-z0-9])")


def _normalised_progress_text(item: NewsItem) -> str:
    return f"{item.title} {item.summary}".lower().translate(_DIGIT_MAP)


def _nearest_number(text: str, start: int, end: int, radius: int = 80) -> str | None:
    lo = max(0, start - radius)
    hi = min(len(text), end + radius)
    candidates = []
    for match in _NUMBER_RE.finditer(text, lo, hi):
        if match.end() <= start:
            distance = start - match.end()
        elif match.start() >= end:
            distance = match.start() - end
        else:
            distance = 0
        candidates.append((distance, match.start(), match.group(0)))
    if not candidates:
        return None
    candidates.sort()
    return candidates[0][2]


def _progress_action_facts(item: NewsItem) -> set[str]:
    """Extract language-independent action counters from rolling operational updates."""
    text = _normalised_progress_text(item)
    facts: set[str] = set()
    for action, aliases in _ACTION_ALIASES.items():
        best: tuple[int, str] | None = None
        for alias in aliases:
            for match in re.finditer(re.escape(alias), text, flags=re.IGNORECASE):
                number = _nearest_number(text, match.start(), match.end())
                if number is None:
                    continue
                # Keep the closest alias/number pair for this action. This avoids
                # nearby dates such as "Sept. 6" / "15 شهریور" winning over 92.
                number_match = None
                lo = max(0, match.start() - 80)
                hi = min(len(text), match.end() + 80)
                for candidate in _NUMBER_RE.finditer(text, lo, hi):
                    if candidate.group(0) != number:
                        continue
                    if candidate.end() <= match.start():
                        distance = match.start() - candidate.end()
                    elif candidate.start() >= match.end():
                        distance = candidate.start() - match.end()
                    else:
                        distance = 0
                    if number_match is None or distance < number_match:
                        number_match = distance
                distance = number_match if number_match is not None else 999
                if best is None or distance < best[0]:
                    best = (distance, number)
        if best is not None:
            facts.add(f"action:{action}:{best[1]}")
    return facts


def _progress_contexts(item: NewsItem) -> set[str]:
    text = _normalised_progress_text(item)
    return {
        context
        for context, aliases in _CONTEXT_ALIASES.items()
        if any(alias in text for alias in aliases)
    }


def _progress_update_facts(item: NewsItem) -> set[str]:
    """Extract material counters from rolling operational updates."""
    text = _normalised_progress_text(item)
    if not any(term in text for term in _PROGRESS_TERMS):
        return set()
    return _progress_action_facts(item)


def is_strict_duplicate_story(left: NewsItem, right: NewsItem) -> bool:
    """Return True only when two items describe the same underlying report.

    Broad shared context such as Iran/US/war is never enough by itself. A duplicate
    needs substantial lexical overlap after the project's canonical normalization,
    or the same multilingual rolling operational counters in the same context.
    Materially changed operational counters are treated as a new update.
    """
    a, b = _tokens(left), _tokens(right)
    if not a or not b:
        return False

    left_facts, right_facts = _specific_facts(left), _specific_facts(right)
    if (left_facts or right_facts) and left_facts != right_facts:
        return False

    left_progress = _progress_update_facts(left)
    right_progress = _progress_update_facts(right)
    if left_progress and right_progress:
        if left_progress != right_progress:
            return False
        common_context = _progress_contexts(left) & _progress_contexts(right)
        if len(left_progress) >= 2 and len(common_context) >= 2:
            return True
    elif left_progress or right_progress:
        return False

    common = a & b
    overlap = len(common) / max(1, min(len(a), len(b)))
    return len(common) >= 5 and overlap >= 0.50
