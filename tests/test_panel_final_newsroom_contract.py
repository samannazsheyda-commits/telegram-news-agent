from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_live_panel_machine_preview_is_google_first_and_never_builds_final_copy():
    source = _text("panel/live_api.py")
    assert "offline_translation" not in source
    assert "LIVE_FEED_TRANSLATOR" in source
    assert '"translation_mode": "machine"' in source
    assert "/api/live-feed/machine-translate" in source
    assert "_persist_localization" not in source


def test_live_cards_label_machine_preview_and_use_calm_polling():
    source = _text("panel/static/newsroom-live.js")
    assert "ترجمه ماشینی" in source
    assert "Google-first" in source
    assert "document.hidden ? 60000 : 15000" in source


def test_luna_prepare_is_preview_first_and_publish_is_separate():
    source = _text("panel/static/newsroom-actions.js")
    assert "/luna" in source
    assert "/publish-prepared" in source
    assert "نسخه لونا آماده شد؛ هنوز منتشر نشده" in source
    assert "همین متن لونا در کانال بی‌خبر منتشر می‌شود" in source


def test_live_publish_uses_prepared_luna_copy():
    source = _text("panel/newsroom_v4_api.py")
    assert "def luna_preview" in source
    assert "def publish_prepared" in source
    assert '"v3_prepare"' in source
    assert '"v3_publish_prepared"' in source
    assert "luna_preview_required" in source


def test_newsroom_shell_is_light_and_disables_expensive_blur():
    base = _text("panel/templates/base.html")
    css = _text("panel/static/newsroom-v4.css")
    assert '<meta name="color-scheme" content="light">' in base
    assert 'content="#f4f7fb"' in base
    assert "--v4-bg:#f4f7fb" in css
    assert "backdrop-filter:none!important" in css
    assert "animation:none!important" in css


def test_mobile_nav_keeps_safe_area():
    css = _text("panel/static/newsroom-v4.css")
    assert "env(safe-area-inset-bottom)" in css
    assert ".nr-mobile-nav" in css


def test_clash_report_label_stays_exact_in_live_newsroom():
    source = _text("panel/live_api.py")
    assert 'return "Clash Report"' in source
