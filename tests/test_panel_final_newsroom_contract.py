from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_v41_dashboard_uses_guarded_luna_translation_endpoint_only():
    dashboard_js = _text("panel/static/newsroom-v4-dashboard.js")
    dashboard = _text("panel/templates/dashboard.html")
    assert "/api/panel/luna/translate-story/" in dashboard_js
    assert "/api/panel/machine-preview/" not in dashboard_js
    assert "ترجمه ماشینی" not in dashboard
    assert "ترجمه با Luna" in dashboard


def test_v41_publish_requires_quality_ready_and_confirmation():
    dashboard_js = _text("panel/static/newsroom-v4-dashboard.js")
    translation = _text("panel/luna_translation.py")
    assert "quality_passed" in translation
    assert "card.dataset.finalReady !== '1'" in dashboard_js
    assert "/api/panel/luna/publish-final/" in dashboard_js
    assert "confirmAction" in dashboard_js
    assert "همین نسخه منتشر شود؟" in dashboard_js


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


def test_v41_keeps_original_and_final_luna_copy_separate_without_judgment_ui():
    dashboard = _text("panel/templates/dashboard.html")
    assert "v41-original" in dashboard
    assert "ترجمه Luna" in dashboard
    assert "ترجمه ماشینی" not in dashboard
    assert "اهمیت:" not in dashboard
    assert "PUBLISH" not in dashboard
