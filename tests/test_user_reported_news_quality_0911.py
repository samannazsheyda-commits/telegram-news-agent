from datetime import datetime

from src import services
from src.news_output import clean_visible_x_text
from src.newsroom_decision import decide_item
from src.newsroom_eligibility import evaluate_eligibility
from src.newsroom_fingerprint import build_fingerprint
from src.newsroom_models import EventRecord, RawNewsItem
from src.newsroom_normalize import normalize_item


NOW = datetime.fromisoformat("2026-09-11T09:15:00+00:00")


def _raw(*, source="Reuters", title, summary="", priority="normal", item_id="item-1", url="https://example.com/story", published="2026-09-11T08:55:00+00:00"):
    return RawNewsItem(
        source=source,
        source_url=url,
        source_item_id=item_id,
        published_at=published,
        fetched_at="2026-09-11T09:00:00+00:00",
        title=title,
        summary=summary,
        source_priority=priority,
    )


def _event(raw: RawNewsItem, event_id="event-1") -> EventRecord:
    item = normalize_item(raw)
    fp = build_fingerprint(item)
    return EventRecord(
        event_id=event_id,
        fingerprint=fp.key,
        canonical_title=raw.title,
        first_seen=raw.fetched_at,
        last_updated=raw.fetched_at,
        primary_source=raw.source,
        source_variants=[raw.source_url],
        key_facts=list(fp.key_facts),
        published_message_ids=[1001],
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


def test_routine_hormuz_diplomatic_call_is_not_auto_publishable():
    item = normalize_item(_raw(
        title="South Korean foreign minister spoke by phone with Iranian counterpart Abbas Araghchi about the situation in the Strait of Hormuz",
    ))
    result = evaluate_eligibility(item, NOW)
    assert result.eligible is False
    # Preserve the established public reason contract while making the routine
    # diplomacy filter explicit internally.
    assert result.reason == "outside_selected_topics"


def test_hormuz_operational_change_remains_publishable():
    item = normalize_item(_raw(
        title="Iran closes the Strait of Hormuz to commercial shipping after a tanker attack",
    ))
    result = evaluate_eligibility(item, NOW)
    assert result.eligible is True


def test_generic_trump_opinion_about_iran_war_is_not_auto_publishable():
    item = normalize_item(_raw(
        source="France 24 / X",
        title="Trump says he has no regrets about the war with Iran",
        priority="protected",
    ))
    result = evaluate_eligibility(item, NOW)
    assert result.eligible is False
    assert result.reason == "filtered_low_value_commentary"


def test_cross_source_trump_no_regret_paraphrase_is_one_event():
    prior_raw = _raw(
        source="France 24 / X",
        item_id="fr24-1",
        url="https://x.com/FRANCE24/status/1",
        title="Trump says he has no regrets about launching the war with Iran",
        priority="protected",
        published="2026-09-11T08:30:00+00:00",
    )
    current_raw = _raw(
        source="Al Arabiya English / X",
        item_id="alarabiya-2",
        url="https://x.com/AlArabiya_Eng/status/2",
        title="Trump says he is not regretful about the war with Iran despite possible midterm election impact",
        priority="protected",
        published="2026-09-11T08:45:00+00:00",
    )
    current = normalize_item(current_raw)
    result = decide_item(current, build_fingerprint(current), [_event(prior_raw)])
    assert result.decision == "duplicate_same_claim"
    assert result.duplicate_of == "event-1"


def test_cross_source_houthi_dhubab_paraphrase_is_one_event():
    prior_raw = _raw(
        source="Al Arabiya English / X",
        item_id="aa-1",
        url="https://x.com/AlArabiya_Eng/status/11",
        title="Iran-backed Houthis reach Yemen's Dhubab: sources",
        priority="protected",
        published="2026-09-11T09:00:00+00:00",
    )
    current_raw = _raw(
        source="Reuters",
        item_id="reuters-2",
        url="https://reuters.com/world/middle-east/example",
        title="Sources say Iran-backed Houthi forces reached Dhubab in Yemen",
        published="2026-09-11T09:05:00+00:00",
    )
    current = normalize_item(current_raw)
    result = decide_item(current, build_fingerprint(current), [_event(prior_raw)])
    assert result.decision == "duplicate_same_claim"
    assert result.duplicate_of == "event-1"


def test_x_cleanup_removes_scoop_and_dangling_story_promo():
    source = (
        "Scoop: MBS called President Trump twice Thursday and urged him to strike the Houthis as the Iran-backed group approached a vital Red Sea chokepoint. "
        "US officials said Trump rejected it for now. My story at https://axios.com/example"
    )
    cleaned = clean_visible_x_text(source)
    assert not cleaned.lower().startswith("scoop:")
    assert "my story at" not in cleaned.lower()
    assert cleaned.endswith("for now.")


def test_editor_repairs_mbs_and_chokepoint_literal_translation():
    source = "MBS urged Trump to act as the Iran-backed Houthis approached a vital Red Sea chokepoint."
    bad = "ام. بی. اس از ترامپ خواست اقدام کند زیرا حوثی‌های مورد حمایت ایران به یک نقطه خفه کننده حیاتی دریای سرخ نزدیک شدند."
    repaired = services._repair_news_idioms(source, bad)
    assert "محمد بن سلمان" in repaired
    assert "گلوگاه حیاتی دریای سرخ" in repaired
    assert "نقطه خفه کننده" not in repaired
    assert "ام. بی. اس" not in repaired


def test_quality_gate_rejects_known_mechanical_persian_if_repair_misses():
    source = "MBS says Iran-backed Houthis are approaching a vital Red Sea chokepoint."
    bad = "ام. بی. اس می‌گوید حوثی‌های مورد حمایت ایران در حال نزدیک شدن به یک نقطه خفه کننده حیاتی دریای سرخ هستند."
    assert services.translation_is_publishable(source, bad) is False
