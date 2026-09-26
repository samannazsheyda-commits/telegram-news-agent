from __future__ import annotations

import re
from dataclasses import dataclass

# Deep editorial reasoning or multi-story synthesis. Everything else stays on the fast model.
_COMPLEX_PATTERNS = (
    r"تحلیل",
    r"مقایسه",
    r"جمع[‌\s]?بندی",
    r"ارزیابی",
    r"بررسی\s*(عمیق|دقیق|کامل)",
    r"ارزش\s*انتشار",
    r"چرا\s",
    r"روند",
    r"(همه|تمام|چند)\s*(خبر|خبرها|منابع)",
    r"اعتبار\s*(منبع|خبر)",
    r"\banaly[sz]",
    r"\bcompare\b",
    r"\bdeep\b",
)
_COMPLEX_RE = re.compile("|".join(_COMPLEX_PATTERNS), re.IGNORECASE)
_LONG_MESSAGE_CHARS = 400


@dataclass(frozen=True)
class ModelRoute:
    tier: str
    reason: str


def route_turn(message: str, *, has_image: bool = False) -> ModelRoute:
    text = str(message or "").strip()
    if has_image:
        return ModelRoute("complex", "image_analysis")
    if len(text) >= _LONG_MESSAGE_CHARS:
        return ModelRoute("complex", "long_request")
    if _COMPLEX_RE.search(text):
        return ModelRoute("complex", "editorial_reasoning")
    return ModelRoute("fast", "routine")


def model_for(client, route: ModelRoute) -> str:
    fast = str(getattr(client, "fast_model", "") or "")
    if route.tier == "complex":
        return str(getattr(client, "complex_model", "") or fast)
    return fast
