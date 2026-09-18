from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_v4_machine_preview_avoids_legacy_argos_endpoint():
    dashboard_js = _text("panel/static/newsroom-v4-dashboard.js")
    v4 = _text("panel/v4.py")
    assert "/api/panel/machine-preview/" in dashboard_js
    assert "translate_to_fa_offline" not in v4
    assert "PANEL_MACHINE_TRANSLATOR" in v4


def test_v4_publish_requires_luna_preview_and_confirmation():
    source = _text("panel/v4.py")
    dashboard_js = _text("panel/static/newsroom-v4-dashboard.js")
    assert "luna_preview_required" in source
    assert "luna_preview_not_publishable" in source
    assert '"v3_publish"' in source
    assert "confirmAction" in dashboard_js
    assert "نسخه نهایی Luna منتشر شود؟" in dashboard_js


def test_newsroom_v4_shell_is_slate_and_topbar_has_no_backdrop_blur():
    base = _text("panel/templates/base.html")
    css = _text("panel/static/newsroom-v4.css")
    assert '<meta name="color-scheme" content="dark light">' in base
    assert 'content="#161d27"' in base
    assert "--v4-bg:#111821" in css
    topbar = css.split(".v4-topbar{", 1)[1].split(".v4-brand{", 1)[0]
    assert "backdrop-filter" not in topbar


def test_mobile_nav_has_safe_area_and_stable_layer():
    css = _text("panel/static/newsroom-v4.css")
    assert "safe-area-inset-bottom" in css
    assert "z-index:70" in css
    assert ".v4-mobile-nav" in css


def test_v4_keeps_original_and_machine_and_luna_copy_visually_separate():
    dashboard = _text("panel/templates/dashboard.html")
    assert "Original" in dashboard
    assert "🌐 ترجمه ماشینی" in dashboard
    assert "🧠 Luna" in dashboard
    assert "ارسال به Luna" in dashboard
