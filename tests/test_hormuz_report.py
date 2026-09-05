from datetime import date, datetime
from zoneinfo import ZoneInfo

from src.hormuz import HormuzTrafficReport, format_hormuz_report, hormuz_report_due


TEHRAN = ZoneInfo("Asia/Tehran")


def test_report_is_due_at_noon_tehran_once_per_day():
    now = datetime(2026, 9, 5, 12, 4, tzinfo=TEHRAN)
    assert hormuz_report_due({}, now)
    assert not hormuz_report_due({"hormuz_last_sent_date": "2026-09-05"}, now)
    assert not hormuz_report_due({}, datetime(2026, 9, 5, 11, 59, tzinfo=TEHRAN))


def test_report_uses_jalali_date_and_only_ship_statistics():
    report = HormuzTrafficReport(
        report_date=date(2026, 9, 4),
        observed_count=4,
        previous_count=9,
        rolling_average=15,
        vessel_details=(
            "۲ نفتکش فرآورده کلاس MR",
            "۱ کشتی فله‌بر Kamsarmax",
            "۱ کشتی Handysize",
        ),
        notes=("آمار بر پایه تردد قابل مشاهده با AIS است.",),
        sources=("Kpler", "Reuters"),
    )
    text = format_hormuz_report(report)
    assert "۱۳ شهریور ۱۴۰۵" in text
    assert "کشتی‌های عبوری مشاهده‌شده: ۴ فروند" in text
    assert "روز قبل: ۹ فروند" in text
    assert "میانگین ۱۰روزه: ۱۵ فروند در روز" in text
    assert "۲ نفتکش فرآورده کلاس MR" in text
    assert "منابع: Kpler، Reuters" in text
    assert "مقدار نفت" not in text
    assert "میلیون بشکه" not in text


def test_report_does_not_invent_missing_count():
    report = HormuzTrafficReport(
        report_date=date(2026, 9, 4),
        observed_count=None,
        previous_count=None,
        rolling_average=None,
        vessel_details=(),
        notes=("برای این روز آمار دقیق و قابل استناد کشتی‌ها منتشر نشده است.",),
        sources=("Kpler",),
    )
    text = format_hormuz_report(report)
    assert "آمار دقیق و قابل استناد کشتی‌ها منتشر نشده" in text
    assert "کشتی‌های عبوری مشاهده‌شده:" not in text
    assert "منابع: Kpler" in text
