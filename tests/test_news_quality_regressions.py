from datetime import datetime

from src.event_ledger import EventLedger
from src.final_output import finalize_telegram_message
from src.formatters import format_news
from src.newsroom_decision import decide_item
from src.newsroom_eligibility import evaluate_eligibility
from src.newsroom_fingerprint import build_fingerprint
from src.newsroom_models import EventRecord, RawNewsItem
from src.newsroom_normalize import normalize_item
from src.sources import NewsItem


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


def test_clash_report_is_not_presented_as_a_telegram_source():
    item = NewsItem(
        "clash",
        "Clash Report / Telegram",
        "Iran update",
        "",
        "https://t.me/clashreport/1",
        "Thu, 10 Sep 2026 16:15:00 GMT",
    )
    text = format_news(item, "خبر تازه درباره ایران", "", marker_override="⚪️")
    assert text.splitlines()[0].startswith("⚪️ <b>کلش ریپورت: ")
    assert "/ تلگرام" not in text.splitlines()[0]


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
