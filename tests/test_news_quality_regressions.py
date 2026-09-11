from datetime import datetime

from src.event_ledger import EventLedger
from src.final_output import finalize_telegram_message
from src.formatters import format_news
from src.newsroom_decision import decide_item
from src.newsroom_eligibility import evaluate_eligibility
from src.newsroom_fingerprint import build_fingerprint
from src.newsroom_models import EventRecord, RawNewsItem
from src.newsroom_normalize import normalize_item
from src.newsroom_publisher import TelegramNewsroomPublisher
from src.sources import NewsItem


class _OfflineTranslationSession:
    def get(self, *args, **kwargs):
        raise RuntimeError("offline regression test")


def _raw(
    title: str,
    *,
    url: str,
    item_id: str,
    summary: str = "",
    source: str = "CENTCOM / X",
    published_at: str = "2026-09-10T16:15:00+00:00",
    fetched_at: str = "2026-09-10T16:16:00+00:00",
) -> RawNewsItem:
    return RawNewsItem(
        source=source,
        source_url=url,
        source_item_id=item_id,
        published_at=published_at,
        fetched_at=fetched_at,
        title=title,
        summary=summary,
        source_priority="protected",
    )


def _published_event(raw: RawNewsItem) -> EventRecord:
    item = normalize_item(raw)
    fp = build_fingerprint(item)
    return EventRecord(
        event_id="shipping-event",
        fingerprint=fp.key,
        canonical_title=raw.title,
        first_seen=raw.fetched_at,
        last_updated=raw.fetched_at,
        primary_source=raw.source,
        source_variants=[raw.source_url],
        key_facts=list(fp.key_facts),
        published_message_ids=[8001],
        status="published",
        fingerprint_data={
            "actors": list(fp.actors),
            "actions": list(fp.actions),
            "objects": list(fp.objects),
            "locations": list(fp.locations),
            "key_facts": list(fp.key_facts),
            "time_bucket": fp.time_bucket,
            "source_item_id": raw.source_item_id,
        },
    )


def test_minor_vessel_count_drift_is_duplicate_not_material_update():
    prior = _raw(
        "CENTCOM says US forces redirected 96 commercial vessels near Iran and allowed 50 humanitarian ships to pass",
        url="https://example.com/prior",
        item_id="prior",
    )
    current = _raw(
        "CENTCOM says US forces redirected 97 commercial vessels near Iran and allowed 50 humanitarian ships to pass",
        url="https://example.com/current",
        item_id="current",
        source="Clash Report / Telegram",
    )
    item = normalize_item(current)
    result = decide_item(item, build_fingerprint(item), [_published_event(prior)])
    assert result.decision == "duplicate_same_claim"


def test_same_shipping_claim_from_new_source_is_candidate_across_time_bucket(tmp_path):
    ledger = EventLedger(tmp_path / "ledger.json")
    prior = _raw(
        "CENTCOM says US forces redirected 96 commercial vessels near Iran and allowed 50 humanitarian ships to pass",
        url="https://example.com/prior-window",
        item_id="prior-window",
        published_at="2026-09-10T15:35:00+00:00",
        fetched_at="2026-09-10T15:36:00+00:00",
    )
    prior_item = normalize_item(prior)
    prior_fp = build_fingerprint(prior_item)
    ledger.create_event(
        fingerprint=prior_fp,
        canonical_title=prior.title,
        primary_source=prior.source,
        source_url=prior.source_url,
        first_seen=prior.fetched_at,
        key_facts=prior_fp.key_facts,
        source_item_id=prior.source_item_id,
    )

    current = _raw(
        "US forces redirected 96 commercial vessels near Iran while 50 humanitarian ships were allowed through",
        url="https://example.com/new-window",
        item_id="new-window",
        source="Clash Report / Telegram",
        published_at="2026-09-10T16:15:00+00:00",
        fetched_at="2026-09-10T16:16:00+00:00",
    )
    current_fp = build_fingerprint(normalize_item(current))
    assert ledger.find_candidates(current_fp)


def test_question_mark_anywhere_in_headline_is_hard_filtered():
    raw = _raw(
        "Iran blockade: what happens next? Officials outline possible routes",
        url="https://example.com/question",
        item_id="question",
    )
    result = evaluate_eligibility(normalize_item(raw), datetime.fromisoformat("2026-09-10T16:20:00+00:00"))
    assert result.eligible is False
    assert result.reason == "filtered_question_or_article"


def test_article_style_inside_headline_is_hard_filtered():
    raw = _raw(
        "Inside Iran's naval strategy in the Strait of Hormuz",
        url="https://example.com/inside-analysis",
        item_id="inside-analysis",
    )
    result = evaluate_eligibility(normalize_item(raw), datetime.fromisoformat("2026-09-10T16:20:00+00:00"))
    assert result.eligible is False
    assert result.reason == "filtered_question_or_article"


def test_final_formatter_refuses_question_headline_even_after_translation():
    item = NewsItem(
        "q",
        "Reuters",
        "Iran navy update",
        "",
        "https://example.com/q",
        "Thu, 10 Sep 2026 16:15:00 GMT",
    )
    text = format_news(item, "آیا ایران مسیر کشتی‌ها را تغییر می‌دهد؟", "", marker_override="⚪️")
    assert text == ""


def test_clash_report_keeps_fully_persian_platform_suffix():
    item = NewsItem(
        "clash",
        "Clash Report / Telegram",
        "Iran update",
        "",
        "https://t.me/clashreport/1",
        "Thu, 10 Sep 2026 16:15:00 GMT",
    )
    text = format_news(item, "خبر تازه درباره ایران", "", marker_override="⚪️")
    assert text.splitlines()[0].startswith("⚪️ <b>کلش ریپورت / تلگرام: ")
    assert "Telegram" not in text.splitlines()[0]


def test_final_news_has_relevant_flags_at_very_bottom():
    item = NewsItem(
        "k",
        "CENTCOM / X",
        "US forces intercept Iranian vessel near Strait of Hormuz",
        "",
        "https://example.com/story",
        "Thu, 10 Sep 2026 16:15:00 GMT",
    )
    text = finalize_telegram_message(
        format_news(item, "نیروهای آمریکایی یک شناور ایرانی را نزدیک تنگه هرمز رهگیری کردند", "", marker_override="🛑")
    )
    last_line = text.splitlines()[-1]
    assert "🇮🇷" in last_line
    assert "🇺🇸" in last_line


def test_routine_iran_diplomacy_does_not_auto_publish():
    raw = _raw(
        "Iranian foreign minister meets Omani counterpart to discuss bilateral relations",
        url="https://example.com/routine-meeting",
        item_id="routine-meeting",
        source="Reuters",
    )
    result = evaluate_eligibility(normalize_item(raw), datetime.fromisoformat("2026-09-10T16:20:00+00:00"))
    assert result.eligible is False
    assert result.review is True
    assert result.reason == "outside_selected_topics"


def test_selected_high_value_missile_story_remains_eligible():
    raw = _raw(
        "Iran launches ballistic missiles toward Israel",
        summary="Air defenses activated after launch from Iran",
        url="https://example.com/missile",
        item_id="missile",
        source="Reuters",
    )
    result = evaluate_eligibility(normalize_item(raw), datetime.fromisoformat("2026-09-10T16:20:00+00:00"))
    assert result.eligible is True


def test_publisher_refuses_translation_that_loses_core_event_meaning():
    raw = _raw(
        "Iran launches ballistic missiles toward Israel",
        summary="Missile launch confirmed by officials",
        url="https://example.com/bad-translation",
        item_id="bad-translation",
        source="Reuters",
    )
    publisher = TelegramNewsroomPublisher(
        "token",
        "@bikhabaar",
        session=_OfflineTranslationSession(),
        translator=lambda _text: "ایران درباره رویداد تازه‌ای گزارش داد",
    )
    assert publisher._message(normalize_item(raw)) == ""


def test_publisher_refuses_translation_that_drops_numeric_fact():
    raw = _raw(
        "Iran launches 12 ballistic missiles toward Israel",
        summary="Officials say 12 missiles were launched",
        url="https://example.com/missing-number",
        item_id="missing-number",
        source="Reuters",
    )
    publisher = TelegramNewsroomPublisher(
        "token",
        "@bikhabaar",
        session=_OfflineTranslationSession(),
        translator=lambda _text: "ایران از شلیک موشک‌های بالستیک به سمت اسرائیل خبر داد",
    )
    assert publisher._message(normalize_item(raw)) == ""
