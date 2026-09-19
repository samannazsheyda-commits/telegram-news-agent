from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_v41_dashboard_uses_persisted_persian_preview_and_guarded_luna_translation():
    dashboard_js = _text("panel/static/newsroom-v4-dashboard.js")
    dashboard = _text("panel/templates/dashboard.html")
    assert "/api/panel/luna/translate-story/" in dashboard_js
    assert "/api/panel/machine-preview/" not in dashboard_js
    assert "ترجمه ماشینی" in dashboard
    assert "ترجمه با Luna" in dashboard
    assert "item.persian_title" in dashboard


def test_v41_publish_requires_visible_persian_copy_and_confirmation():
    dashboard_js = _text("panel/static/newsroom-v4-dashboard.js")
    translation = _text("panel/luna_translation.py")
    publish = _text("panel/luna_publish.py")
    assert "quality_passed" in translation
    assert "card.dataset.publishReady !== '1'" in dashboard_js
    assert "persian_copy_not_ready" in publish
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


def test_v41_keeps_machine_preview_and_optional_luna_copy_separate_without_judgment_ui():
    dashboard = _text("panel/templates/dashboard.html")
    assert "v41-original" in dashboard
    assert "نسخه Luna" in dashboard
    assert "ترجمه ماشینی" in dashboard
    assert "اهمیت:" not in dashboard
    assert "PUBLISH" not in dashboard
