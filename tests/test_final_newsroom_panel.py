from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
V4_JS = (ROOT / "panel/static/newsroom-v4.js").read_text(encoding="utf-8")
DASHBOARD_JS = (ROOT / "panel/static/newsroom-v4-dashboard.js").read_text(encoding="utf-8")
ASSISTANT_JS = (ROOT / "panel/static/luna-assistant.js").read_text(encoding="utf-8")
CSS = (ROOT / "panel/static/newsroom-v4.css").read_text(encoding="utf-8")
POLISH = (ROOT / "panel/static/newsroom-v4-polish.css").read_text(encoding="utf-8")
BASE = (ROOT / "panel/templates/base.html").read_text(encoding="utf-8")
DASHBOARD = (ROOT / "panel/templates/dashboard.html").read_text(encoding="utf-8")


def test_final_panel_v41_assets_are_loaded():
    assert "newsroom-v4.css" in BASE
    assert "newsroom-v4-polish.css" in BASE
    assert "newsroom-v4.js" in BASE
    assert "newsroom-v4-dashboard.js" in DASHBOARD
    assert 'data-newsroom-shell="v4-1"' in BASE


def test_v41_story_flow_has_distinct_machine_and_luna_publish_paths():
    assert "translate-luna" in DASHBOARD
    assert "publish-machine" in DASHBOARD
    assert "publish-luna" in DASHBOARD
    assert "send-luna" not in DASHBOARD
    assert "/api/panel/luna/translate-story/" in DASHBOARD_JS
    assert "/api/panel/luna/publish-machine/" in DASHBOARD_JS
    assert "/api/panel/luna/publish-final/" in DASHBOARD_JS
    assert "confirmAction" in DASHBOARD_JS
    assert 'data-v4-action="reject"' in DASHBOARD
    assert "reject-block" not in DASHBOARD
    assert "/api/panel/luna/block-story/" not in DASHBOARD_JS


def test_v41_panel_has_real_mobile_navigation_and_confirmation():
    assert "v4-mobile-nav" in BASE
    assert "v4ConfirmDialog" in BASE
    assert "confirmAction" in V4_JS
    assert "safe-area-inset-bottom" in CSS
    assert "Noto Sans Arabic" in POLISH


def test_v41_luna_assistant_is_wired_to_operator_api():
    assert "/api/panel/luna/operator-chat" in ASSISTANT_JS
    assert "/api/panel/luna/operator-confirm/" in ASSISTANT_JS
    assert "confirmation_required" in ASSISTANT_JS
    assert "تأیید و اجرا" in ASSISTANT_JS
