from __future__ import annotations

import re

from .newsroom_x import clean_x_post_text

_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
_LEADING_ALERT_RE = re.compile(r"^(?:(?:🔴|🚨|⚠️?|‼️?|❗️?|⭕️?|🛑|🔺|🔻)\s*)+")
_LEADING_EDITORIAL_LABEL_RE = re.compile(
    r"^(?:(?:scoop|exclusive|exclusive scoop|breaking exclusive)\s*:\s*)+",
    re.IGNORECASE,
)
_TRAILING_LINK_PROMO_RE = re.compile(
    r"\s*(?:(?:🔴|🚨)\s*)?(?:"
    r"live\s+updates?|read\s+more|more|details|"
    r"my\s+(?:full\s+)?story\s+at|(?:full\s+)?story\s+at|more\s+in\s+my\s+story"
    r")\s*:?\s*$",
    re.IGNORECASE,
)


def clean_visible_x_text(text: str) -> str:
    """Return clean X copy for Telegram without labels, promos or embedded URLs."""
    value = clean_x_post_text(text)
    value = _LEADING_ALERT_RE.sub("", value).strip()
    value = _LEADING_EDITORIAL_LABEL_RE.sub("", value).strip()
    value = _URL_RE.sub("", value)
    value = re.sub(r"\s+", " ", value).strip()
    value = _TRAILING_LINK_PROMO_RE.sub("", value).strip()
    value = re.sub(r"\s+([,.;:!?؟])", r"\1", value).strip()
    return value
