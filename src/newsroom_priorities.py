from __future__ import annotations

DEFAULT_PRIORITY_RULES = [
    "موشک از ایران",
    "شلیک موشک از ایران",
    "موشک به ایران",
    "حمله موشکی به ایران",
    "جنگ و تحولات نظامی",
    "حمله مستقیم نظامی",
    "تنگه هرمز",
    "انفجار",
    "پهپاد",
    "ناو جنگی",
    "نفتکش",
    "توقیف کشتی",
    "غرق شدن کشتی",
    "هسته‌ای",
    "تأسیسات نظامی",
    "حریم هوایی",
    "بازار ارز و طلا",
    "تحریم و اقتصاد",
]


def normalize_priority_rules(value) -> list[str]:
    if value is None:
        return list(DEFAULT_PRIORITY_RULES)
    if not isinstance(value, list):
        raise ValueError("priority_rules_must_be_list")
    result: list[str] = []
    seen: set[str] = set()
    for raw in value:
        text = " ".join(str(raw or "").split()).strip()
        if not 2 <= len(text) <= 120:
            raise ValueError("invalid_priority_rule")
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
        if len(result) > 40:
            raise ValueError("too_many_priority_rules")
    if not result:
        raise ValueError("priority_rules_required")
    return result
