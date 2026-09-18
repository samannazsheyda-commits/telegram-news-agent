from __future__ import annotations

import re


_BUILDER_PATTERNS = (
    r"\bماژول\b",
    r"\bپنل\b",
    r"\bداشبورد\b",
    r"\bصفحه\b",
    r"\bبخش\b.*\b(اضافه|حذف|بساز|تغییر|عوض)\b",
    r"\b(اضافه|بساز|تغییر|عوض|حذف)\b.*\b(بخش|صفحه|داشبورد|پنل|ماژول)\b",
    r"\b(ui|UI|رابط کاربری)\b",
)

_OPERATOR_GUARDS = (
    "این خبر",
    "خبر رو",
    "خبر را",
    "این منبع",
    "منبع رو",
    "منبع را",
    "فارسی کن",
    "ترجمه کن",
    "خاموش کن",
    "روشن کن",
    "فعال کن",
    "غیرفعال کن",
)


def is_builder_request(message: str) -> bool:
    text = re.sub(r"\s+", " ", str(message or "")).strip()
    if not text:
        return False
    if any(guard in text for guard in _OPERATOR_GUARDS):
        return False
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in _BUILDER_PATTERNS)


def builder_policy() -> dict:
    return {
        "requires_confirmation_before_merge": True,
        "requires_green_ci": True,
        "direct_production_edits": False,
        "arbitrary_shell": False,
        "branch_required": True,
        "pull_request_required": True,
        "rollback_reference_required": True,
    }
