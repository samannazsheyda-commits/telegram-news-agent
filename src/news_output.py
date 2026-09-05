from __future__ import annotations

import re

from .newsroom_x import clean_x_post_text

_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
_LEADING_ALERT_RE = re.compile(r"^(?:(?:🔴|🚨|⚠️?|‼️?|❗️?|⭕️?|🛑|🔺|🔻)\s*)+")
_TRAILING_LINK_PROMO_RE = re.compile(
    r"\s*(?:(?:🔴|🚨)\s*)?(?:live\s+updates?|read\s+more|more|details)\s*:?\s*$",
    re.IGNORECASE,
)


def clean_visible_x_text(text: str) -> str:
    """Return the X post copy for Telegram without decorative alert badges or URLs.

    The canonical X status remains available through the dedicated source-link line,
    so article/short links embedded in the post are intentionally omitted here.
    """
    value = clean_x_post_text(text)
    value = _LEADING_ALERT_RE.sub("", value).strip()
    value = _URL_RE.sub("", value)
    value = re.sub(r"\s+", " ", value).strip()
    value = _TRAILING_LINK_PROMO_RE.sub("", value).strip()
    value = re.sub(r"\s+([,.;:!?؟])", r"\1", value).strip()
    return value
