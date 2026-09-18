from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LIVE = (ROOT / "panel/static/newsroom-live.js").read_text(encoding="utf-8")
ACTIONS = (ROOT / "panel/static/newsroom-actions.js").read_text(encoding="utf-8")
CSS = (ROOT / "panel/static/newsroom-v4.css").read_text(encoding="utf-8")
BASE = (ROOT / "panel/templates/base.html").read_text(encoding="utf-8")
API = (ROOT / "panel/newsroom_v4_api.py").read_text(encoding="utf-8")


def test_final_panel_assets_are_loaded():
    assert "newsroom-v4.css" in BASE
    assert "newsroom-live.js" in (ROOT / "panel/templates/dashboard.html").read_text(encoding="utf-8")
    assert "newsroom-actions.js" in (ROOT / "panel/templates/dashboard.html").read_text(encoding="utf-8")


def test_luna_preview_and_machine_translation_copy_are_present():
    assert "ترجمه ماشینی" in LIVE
    assert "ترجمه و ویراستاری با لونا" in LIVE
    assert "نسخه نهایی لونا" in LIVE
    assert "هنوز منتشر نشده" in ACTIONS


def test_final_panel_has_actionable_operator_lanes():
    for label in ("متن اصلی منبع", "ترجمه ماشینی", "انتشار نسخه لونا", "رد"):
        assert label in LIVE
    assert "ویرایش نسخه لونا" in LIVE


def test_final_panel_uses_exact_v3_daily_capacity_and_visible_health():
    for field in ("daily_published", "daily_limit", "daily_remaining"):
        assert field in API
        assert field in LIVE
    assert "dailyLimitInput" in (ROOT / "panel/templates/dashboard.html").read_text(encoding="utf-8")
    assert ".v4-overview" in CSS
    assert ".v4-health" in CSS
