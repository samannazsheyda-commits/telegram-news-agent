from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / "panel/static/newsroom-v4.js").read_text(encoding="utf-8")
CSS = (ROOT / "panel/static/newsroom-v4.css").read_text(encoding="utf-8")
PAGES_CSS = (ROOT / "panel/static/newsroom-v4-pages.css").read_text(encoding="utf-8")
BASE = (ROOT / "panel/templates/base.html").read_text(encoding="utf-8")
DASHBOARD = (ROOT / "panel/templates/dashboard.html").read_text(encoding="utf-8")
V4_API = (ROOT / "panel/v4.py").read_text(encoding="utf-8")


def test_v4_panel_assets_are_the_active_newsroom_layer():
    assert "newsroom-v4.css" in BASE
    assert "newsroom-v4-pages.css" in BASE
    assert "newsroom-v4.js" in BASE
    for legacy in ("newsroom-final.css", "newsroom-final.js", "newsroom-shell.css", "newsroom-ui.js", "newsroom-live.js", "newsroom-actions.js", "newsroom-editor.js"):
        assert legacy not in BASE
    assert 'data-newsroom-shell="v4"' in BASE


def test_v4_has_mobile_first_navigation_and_no_air_traffic_entry():
    assert "v4-mobile-nav" in BASE
    for label in ("داشبورد", "ورودی", "بررسی", "لونا", "منتشرشده", "منابع", "تنظیمات", "سلامت سیستم"):
        assert label in BASE
    assert "ترافیک هوایی" not in BASE
    assert "air-traffic" not in BASE
    assert "env(safe-area-inset-bottom)" in CSS
    assert "backdrop-filter: none" in CSS


def test_v4_dashboard_uses_real_quota_and_health_contract():
    for field in ("regular_limit", "regular_published", "regular_remaining", "special_limit", "special_used"):
        assert f'"{field}"' in V4_API
    for label in ("منتشرشده امروز", "باقی‌مانده", "منتظر بررسی", "خبر ویژه Luna", "سلامت سیستم"):
        assert label in DASHBOARD
    assert "/api/v4/snapshot" in DASHBOARD


def test_v4_common_runtime_exposes_safe_action_helpers():
    for helper in ("postJSON", "confirmAction", "toast"):
        assert helper in JS
    assert "--v4-touch: 44px" in CSS
    assert ".v4-news-card" in PAGES_CSS
