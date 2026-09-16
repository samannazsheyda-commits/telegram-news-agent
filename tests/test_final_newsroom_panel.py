from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / "panel/static/newsroom-final.js").read_text(encoding="utf-8")
CSS = (ROOT / "panel/static/newsroom-final.css").read_text(encoding="utf-8")
BASE = (ROOT / "panel/templates/base.html").read_text(encoding="utf-8")
API = (ROOT / "panel/newsroom_api.py").read_text(encoding="utf-8")


def test_final_panel_assets_are_loaded():
    assert "newsroom-final.css" in BASE
    assert "newsroom-final.js" in BASE


def test_clashreport_alias_and_persian_cycle_copy_are_present():
    assert "'ClashReport / Telegram': 'کلش ریپورت / تلگرام'" in JS
    assert "attempt_limit: 'خبرهای آمادهٔ فعلی به سقف تلاش رسیده‌اند'" in JS
    assert "final_gate_rejected: 'خبر در بررسی نهایی لونا تأیید نشد'" in JS


def test_final_panel_has_actionable_review_rejected_and_published_lanes():
    assert "const FILTER_LABELS" in JS
    for label in ("قابل اقدام", "نیازمند بررسی", "ردشده", "منتشرشده"):
        assert label in JS
    assert "outside_selected_topics" in JS
    assert "needs_editorial_review" in JS
    assert "published_manual" in JS


def test_final_panel_uses_exact_v3_daily_capacity_and_keeps_raw_codes_in_details():
    for field in ("daily_published", "daily_limit", "daily_remaining"):
        assert f'"{field}":' in API
        assert field in JS
    assert "dailyCapacitySummary" in JS
    assert "technicalReasonCode" in JS
    assert "technicalErrorCode" in JS
    assert ".nr-capacity-strip" in CSS
    assert ".nr-feed-tabs" in CSS
