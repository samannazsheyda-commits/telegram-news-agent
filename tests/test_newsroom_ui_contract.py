from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "docs/panel.html"
CSS = ROOT / "docs/newsroom-v1.css"
JS = ROOT / "docs/newsroom-v1.js"


def test_newsroom_assets_and_views_are_loaded():
    html = HTML.read_text(encoding="utf-8")
    assert 'href="newsroom-v1.css?v=' in html
    assert 'src="newsroom-v1.js?v=' in html
    assert 'data-view="analytics"' in html
    assert 'data-view="settings"' in html
    assert 'id="view-analytics"' in html
    assert 'id="view-settings"' in html


def test_newsroom_uses_doran_as_display_font_without_bundling_font_binary():
    css = CSS.read_text(encoding="utf-8")
    assert '"Doran NoEn ExtraBold"' in css
    assert '"DoranNoEn-ExtraBold"' in css
    assert "@font-face" not in css


def test_newsroom_has_command_center_bulk_clear_preview_and_settings_hooks():
    js = JS.read_text(encoding="utf-8")
    for token in (
        "newsroomCommandBar",
        "situationRail",
        "clearCurrentView",
        "clearFilteredView",
        "confirmDanger",
        "openPreview",
        "settings_save",
        "emergency_lock",
        "renderAnalytics",
        "renderSituation",
    ):
        assert token in js


def test_visible_source_fallback_is_persian_first():
    js = JS.read_text(encoding="utf-8")
    assert "Times of Israel':'تایمز اسرائیل" in js
    assert "if(ascii.test(out))out='منبع خبری'" in js
