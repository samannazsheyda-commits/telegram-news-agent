from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _between(text: str, start: str, end: str) -> str:
    return text.split(start, 1)[1].split(end, 1)[0]


def test_live_panel_localization_is_offline_only_and_never_builds_final_copy():
    source = _text("panel/live_api.py")
    assert "from src.offline_translation import translate_to_fa_offline" in source
    translate_block = _between(source, "def _translate_persian", "def _final_message")
    assert "translate_to_fa_offline" in translate_block
    assert "LIVE_FEED_TRANSLATOR" not in translate_block

    endpoint_block = source.split('def localize_live_feed():', 1)[1]
    assert '"translation_mode": "offline_literal"' in source
    assert "final_message = _final_message" not in endpoint_block
    assert "_persist_localization(item_id, title_fa, body_fa, final_message)" not in endpoint_block


def test_live_cards_label_literal_preview_and_use_calmer_polling():
    source = _text("panel/static/newsroom-live.js")
    assert "ترجمه آفلاین · تحت‌اللفظی" in source
    assert "document.hidden ? 30000 : 5000" in source


def test_story_publish_and_reject_are_one_tap_without_confirmation():
    source = _text("panel/static/newsroom-actions.js")
    publish_block = _between(source, "async function publishCard", "async function rejectCard")
    reject_block = _between(source, "async function rejectCard", "function liveCheckboxes")
    assert "confirmAction" not in publish_block
    assert "confirmAction" not in reject_block
    # Whole-system publishing controls are still allowed to confirm.
    publishing_toggle_block = source.split("publishingToggle?.addEventListener", 1)[1]
    assert "confirmAction" in publishing_toggle_block


def test_live_publish_queues_original_source_for_luna_not_literal_preview():
    source = _text("panel/newsroom_api.py")
    publish_block = _between(source, "def publish_live", "def command_result")
    assert "original_title" in publish_block
    assert "original_body" in publish_block
    assert 'original_title=original_title' in publish_block
    assert 'original_body=original_body' in publish_block
    assert "final_not_ready" not in publish_block


def test_newsroom_shell_is_light_slate_and_topbar_has_no_backdrop_blur():
    base = _text("panel/templates/base.html")
    css = _text("panel/static/newsroom-shell.css")
    assert '<meta name="color-scheme" content="light">' in base
    assert 'content="#eef2f6"' in base
    assert "--nr-bg: #eef2f6" in css
    topbar = _between(css, ".nr-topbar {", ".nr-brand {")
    assert "backdrop-filter" not in topbar


def test_mobile_nav_has_safe_area_and_high_stable_layer():
    css = _text("panel/static/newsroom-shell.css")
    mobile = _between(css, ".nr-mobile-nav {", ".nr-mobile-nav .newsroom-nav-item")
    assert "env(safe-area-inset-bottom)" in mobile
    assert "z-index: 90" in mobile


def test_clash_report_label_is_persian_in_live_newsroom():
    source = _text("panel/static/newsroom-live.js")
    assert "if (source === 'Clash Report') return 'کلش ریپورت';" in source
