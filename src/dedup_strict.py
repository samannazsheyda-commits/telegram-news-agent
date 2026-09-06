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
_PERSIAN_RE = re.compile(r"[\u0600-\u06ff]")


def _normalised_progress_text(item: NewsItem) -> str:
    return f"{item.title} {item.summary}".lower().translate(_DIGIT_MAP)


def _directional_number(text: str, start: int, end: int, *, prefer_before: bool, radius: int = 80) -> tuple[int, str] | None:
    lo = max(0, start - radius)
    hi = min(len(text), end + radius)
    before: list[tuple[int, str]] = []
    after: list[tuple[int, str]] = []
    for match in _NUMBER_RE.finditer(text, lo, hi):
        if match.end() <= start:
            before.append((start - match.end(), match.group(0)))
        elif match.start() >= end:
            after.append((match.start() - end, match.group(0)))

    preferred = before if prefer_before else after
    fallback = after if prefer_before else before
    if preferred:
        return min(preferred, key=lambda row: row[0])
    if fallback:
        return min(fallback, key=lambda row: row[0])
    return None


def _progress_action_facts(item: NewsItem) -> set[str]:
    """Extract language-independent action counters from rolling operational updates."""
    text = _normalised_progress_text(item)
    facts: set[str] = set()
    for action, aliases in _ACTION_ALIASES.items():
        best: tuple[int, str] | None = None
        for alias in aliases:
            prefer_before = bool(_PERSIAN_RE.search(alias))
            for match in re.finditer(re.escape(alias), text, flags=re.IGNORECASE):
                candidate = _directional_number(
                    text,
                    match.start(),
                    match.end(),
                    prefer_before=prefer_before,
                )
                if candidate is None:
                    continue
                if best is None or candidate[0] < best[0]:
                    best = candidate
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
