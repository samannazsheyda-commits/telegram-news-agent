from datetime import date, datetime
from zoneinfo import ZoneInfo

import src.runtime as runtime
from src.hormuz import (
    HormuzTrafficReport,
    fetch_hormuz_traffic_report,
    format_hormuz_report,
    hormuz_report_due,
    parse_hormuz_source_text,
)
from src.sources import NewsItem


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


def test_source_text_parser_extracts_counts_types_and_data_provider():
    text = (
        "Only 4 cargo ships transited the Strait of Hormuz on Thursday, down from 9 a day earlier, "
        "according to Kpler data. The 10-day average was 15 vessels per day. "
        "The four ships were two medium-range product tankers, one Kamsarmax bulk carrier and one Handysize vessel."
    )
    parsed = parse_hormuz_source_text(text, publisher="Reuters")
    assert parsed.observed_count == 4
    assert parsed.previous_count == 9
    assert parsed.rolling_average == 15
    assert any("medium-range product tankers" in item for item in parsed.vessel_details)
    assert "Kpler" in parsed.sources
    assert "Reuters" in parsed.sources


def test_daily_fetch_builds_report_from_reliable_source_without_oil_volume():
    item = NewsItem(
        "hormuz-4",
        "Reuters",
        "Gulf shipping traffic via Hormuz stays below average",
        "Only 4 cargo ships transited the Strait of Hormuz, down from 9 a day earlier, according to Kpler data.",
        "https://example.com/hormuz",
        "Fri, 04 Sep 2026 20:00:00 GMT",
    )

    def searcher(label, query):
        return [item]

    def detail_fetcher(news_item):
        return (
            "The 10-day average was 15 vessels per day. The four ships were two medium-range product tankers, "
            "one Kamsarmax bulk carrier and one Handysize vessel."
        )

    report = fetch_hormuz_traffic_report(date(2026, 9, 4), searcher=searcher, detail_fetcher=detail_fetcher)
    assert report.observed_count == 4
    assert report.previous_count == 9
    assert report.rolling_average == 15
    assert "Kpler" in report.sources
    assert "Reuters" in report.sources
    rendered = format_hormuz_report(report)
    assert "میلیون بشکه" not in rendered


def test_runtime_sends_previous_day_report_once_after_noon(tmp_path, monkeypatch):
    state_path = tmp_path / "state.json"
    state_path.write_text('{"truth_last_id":"10","news_seen":["seed"]}', encoding="utf-8")
    monkeypatch.setattr(runtime.agent, "STATE_PATH", str(state_path))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    requested_dates = []
    report = HormuzTrafficReport(
        report_date=date(2026, 9, 4), observed_count=4, previous_count=9, rolling_average=15,
        vessel_details=(), notes=(), sources=("Kpler", "Reuters"),
    )
    monkeypatch.setattr(runtime, "fetch_hormuz_traffic_report", lambda report_date: requested_dates.append(report_date) or report)
    monkeypatch.setattr(runtime, "format_hormuz_report", lambda value: "HORMUZ REPORT\nمنابع: Kpler، Reuters")
    sent = []
    monkeypatch.setattr(runtime.agent, "send_telegram", lambda text, token, chat: sent.append(text))

    now = datetime(2026, 9, 5, 12, 4, tzinfo=TEHRAN)
    runtime._send_hormuz_daily(now)
    runtime._send_hormuz_daily(now)

    assert requested_dates == [date(2026, 9, 4)]
    assert sent == ["HORMUZ REPORT\nمنابع: Kpler، Reuters"]
    assert runtime.agent.load_state(state_path)["hormuz_last_sent_date"] == "2026-09-05"


def test_runtime_does_not_publish_hormuz_message_when_no_observed_count(tmp_path, monkeypatch):
    state_path = tmp_path / "state.json"
    state_path.write_text('{"truth_last_id":"10","news_seen":["seed"]}', encoding="utf-8")
    monkeypatch.setattr(runtime.agent, "STATE_PATH", str(state_path))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    report = HormuzTrafficReport(
        report_date=date(2026, 9, 4), observed_count=None, previous_count=None, rolling_average=None,
        vessel_details=(), notes=("برای این روز آمار دقیق و قابل استناد کشتی‌ها منتشر نشده است.",),
        sources=("Kpler", "Vortexa", "Reuters"),
    )
    monkeypatch.setattr(runtime, "fetch_hormuz_traffic_report", lambda report_date: report)
    sent = []
    monkeypatch.setattr(runtime.agent, "send_telegram", lambda text, token, chat: sent.append(text))

    now = datetime(2026, 9, 5, 12, 4, tzinfo=TEHRAN)
    runtime._send_hormuz_daily(now)

    assert sent == []
    assert runtime.agent.load_state(state_path).get("hormuz_last_sent_date") is None
