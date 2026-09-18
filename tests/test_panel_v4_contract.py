from __future__ import annotations

from pathlib import Path


def test_panel_v4_never_auto_runs_translation_during_live_refresh():
    js = Path("panel/static/newsroom-v4.js").read_text(encoding="utf-8")

    assert "machine-translate" in js
    assert "ترجمه ماشینی" in js
    assert "localizeMissing(currentStories)" not in js
    assert "setTimeout(() => refresh(), document.hidden ? 60000 : 12000)" in js


def test_panel_v4_has_two_step_luna_prepare_then_publish_flow():
    dashboard = Path("panel/templates/dashboard.html").read_text(encoding="utf-8")
    js = Path("panel/static/newsroom-v4.js").read_text(encoding="utf-8")

    assert "ترجمه و ویراستاری با لونا" in dashboard or "ترجمه و ویراستاری با لونا" in js
    assert "پیش‌نمایش نهایی لونا" in dashboard or "پیش‌نمایش نهایی لونا" in js
    assert "/prepare-luna" in js
    assert "/publish-prepared" in js


def test_panel_v4_exposes_daily_and_special_quota_controls():
    dashboard = Path("panel/templates/dashboard.html").read_text(encoding="utf-8")
    api = Path("panel/v4_api.py").read_text(encoding="utf-8")

    assert 'name="daily_limit"' in dashboard
    assert 'name="special_limit"' in dashboard
    assert '"daily_limit"' in api
    assert '"special_limit"' in api


def test_panel_v4_does_not_show_air_traffic_module():
    dashboard = Path("panel/templates/dashboard.html").read_text(encoding="utf-8")

    assert "air-traffic" not in dashboard
    assert "ترافیک هوایی" not in dashboard


def test_panel_v4_uses_consistent_passwordless_mode_for_routes_and_apis():
    wsgi = Path("panel/wsgi.py").read_text(encoding="utf-8")

    assert "PANEL_AUTH_DISABLED" in wsgi
    assert 'session["admin"] = True' in wsgi


def test_panel_v4_styles_mobile_actions_without_overlap():
    css = Path("panel/static/newsroom-v4.css").read_text(encoding="utf-8")

    assert "minmax(0,1fr)" in css
    assert "overflow-wrap:anywhere" in css.replace(" ", "")
    assert "touch-action:manipulation" in css.replace(" ", "")
