from panel.live_api import _panel_section
from panel.newsroom_api import _v3_reason_fa
from src.formatters import _source_label


def test_clashreport_telegram_alias_is_fully_persian():
    assert _source_label("ClashReport / Telegram") == "کلش ریپورت / تلگرام"


def test_v3_cycle_reasons_are_operator_friendly_persian():
    assert _v3_reason_fa("attempt_limit") == "خبرهای آمادهٔ فعلی به سقف تلاش رسیده‌اند"
    assert _v3_reason_fa("final_gate_rejected") == "خبر در بررسی نهایی لونا تأیید نشد"
    assert _v3_reason_fa("published") == "خبر منتشر شد"
    assert _v3_reason_fa("") == "—"


def test_live_feed_sections_keep_noise_out_of_actionable_lane():
    assert _panel_section("new", "eligible") == "live"
    assert _panel_section("waiting", "needs_editorial_review") == "review"
    assert _panel_section("waiting", "outside_selected_topics") == "rejected"
    assert _panel_section("rejected", "final_gate:duplicate_event") == "rejected"
    assert _panel_section("published_manual", "") == "published"
