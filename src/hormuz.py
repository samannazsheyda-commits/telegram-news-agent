from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo


TEHRAN = ZoneInfo("Asia/Tehran")
PERSIAN_MONTHS = (
    "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند",
)
PERSIAN_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
VESSEL_TERMS = (
    "tanker", "tankers", "bulk carrier", "kamsarmax", "handysize", "vlcc",
    "lng carrier", "lpg carrier", "container ship", "cargo ship", "vessel",
)


@dataclass(frozen=True)
class HormuzTrafficReport:
    report_date: date
    observed_count: int | None
    previous_count: int | None
    rolling_average: int | float | None
    vessel_details: tuple[str, ...]
    notes: tuple[str, ...]
    sources: tuple[str, ...]


@dataclass(frozen=True)
class ParsedHormuzStats:
    observed_count: int | None
    previous_count: int | None
    rolling_average: int | float | None
    vessel_details: tuple[str, ...]
    sources: tuple[str, ...]


def _to_persian_digits(value: object) -> str:
    return str(value).translate(PERSIAN_DIGITS)


def _gregorian_to_jalali(g_y: int, g_m: int, g_d: int) -> tuple[int, int, int]:
    g_days_in_month = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
    j_days_in_month = (31, 31, 31, 31, 31, 31, 30, 30, 30, 30, 30, 29)

    gy = g_y - 1600
    gm = g_m - 1
    gd = g_d - 1

    g_day_no = 365 * gy + (gy + 3) // 4 - (gy + 99) // 100 + (gy + 399) // 400
    for i in range(gm):
        g_day_no += g_days_in_month[i]
    if gm > 1 and ((gy + 1600) % 4 == 0 and ((gy + 1600) % 100 != 0 or (gy + 1600) % 400 == 0)):
        g_day_no += 1
    g_day_no += gd

    j_day_no = g_day_no - 79
    j_np = j_day_no // 12053
    j_day_no %= 12053

    jy = 979 + 33 * j_np + 4 * (j_day_no // 1461)
    j_day_no %= 1461
    if j_day_no >= 366:
        jy += (j_day_no - 1) // 365
        j_day_no = (j_day_no - 1) % 365

    jm = 0
    while jm < 11 and j_day_no >= j_days_in_month[jm]:
        j_day_no -= j_days_in_month[jm]
        jm += 1
    jd = j_day_no + 1
    return jy, jm + 1, jd


def format_jalali_date(value: date) -> str:
    jy, jm, jd = _gregorian_to_jalali(value.year, value.month, value.day)
    return f"{_to_persian_digits(jd)} {PERSIAN_MONTHS[jm - 1]} {_to_persian_digits(jy)}"


def hormuz_report_due(state: dict, now: datetime) -> bool:
    local = now.astimezone(TEHRAN)
    if local.hour < 12:
        return False
    return state.get("hormuz_last_sent_date") != local.date().isoformat()


def _format_number(value: int | float) -> str:
    if isinstance(value, float) and not value.is_integer():
        rendered = f"{value:.1f}".rstrip("0").rstrip(".")
    else:
        rendered = str(int(value))
    return _to_persian_digits(rendered)


def _first_number(text: str, patterns: tuple[str, ...]) -> int | float | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        raw = match.group(1).replace(",", "")
        try:
            value = float(raw)
        except ValueError:
            continue
        return int(value) if value.is_integer() else value
    return None


def parse_hormuz_source_text(text: str, publisher: str = "") -> ParsedHormuzStats:
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    observed = _first_number(cleaned, (
        r"(?:only\s+)?(\d+(?:\.\d+)?)\s+(?:cargo|commercial)?\s*(?:ships?|vessels?)\s+(?:transited|crossed|passed through|passed)",
        r"(?:transits?|traffic)\s+(?:fell|dropped|rose|increased)?\s*(?:to|at)?\s*(\d+(?:\.\d+)?)\s+(?:ships?|vessels?)",
    ))
    previous = _first_number(cleaned, (
        r"(?:down|up)\s+from\s+(\d+(?:\.\d+)?)\s+(?:a|the)?\s*(?:day|one day)\s+earlier",
        r"previous\s+day[^\d]{0,20}(\d+(?:\.\d+)?)\s+(?:ships?|vessels?)",
    ))
    average = _first_number(cleaned, (
        r"10[- ]day\s+average(?:\s+(?:was|of))?\s+(\d+(?:\.\d+)?)",
        r"average\s+of\s+(\d+(?:\.\d+)?)\s+(?:ships?|vessels?)\s+(?:a|per)\s+day",
    ))

    details: list[str] = []
    for sentence in re.split(r"(?<=[.!?])\s+", cleaned):
        low = sentence.lower()
        if any(term in low for term in VESSEL_TERMS) and any(
            token in low for token in ("two ", "one ", "three ", "four ", "medium-range", "kamsarmax", "handysize", "vlcc", "lng", "lpg")
        ):
            details.append(sentence.strip())
    details = details[:4]

    sources: list[str] = []
    if "kpler" in cleaned.lower():
        sources.append("Kpler")
    if "vortexa" in cleaned.lower():
        sources.append("Vortexa")
    if publisher:
        normalized = publisher.strip()
        if normalized and normalized not in sources:
            sources.append(normalized)

    return ParsedHormuzStats(
        observed_count=observed if isinstance(observed, int) else None,
        previous_count=previous if isinstance(previous, int) else None,
        rolling_average=average,
        vessel_details=tuple(details),
        sources=tuple(sources),
    )


def format_hormuz_report(report: HormuzTrafficReport) -> str:
    lines = [f"🚢 آمار تردد تنگه هرمز | {format_jalali_date(report.report_date)}"]

    if report.observed_count is not None:
        lines.append(f"کشتی‌های عبوری مشاهده‌شده: {_format_number(report.observed_count)} فروند")
    if report.previous_count is not None:
        lines.append(f"روز قبل: {_format_number(report.previous_count)} فروند")
    if report.rolling_average is not None:
        lines.append(f"میانگین ۱۰روزه: {_format_number(report.rolling_average)} فروند در روز")

    if report.vessel_details:
        lines.append("")
        lines.extend(report.vessel_details)

    if report.notes:
        lines.append("")
        lines.extend(report.notes)

    if report.sources:
        lines.append("")
        lines.append("منابع: " + "، ".join(report.sources))

    return "\n".join(lines).strip()
