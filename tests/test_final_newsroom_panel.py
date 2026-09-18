from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
V4_JS = (ROOT / "panel/static/newsroom-v4.js").read_text(encoding="utf-8")
DASHBOARD_JS = (ROOT / "panel/static/newsroom-v4-dashboard.js").read_text(encoding="utf-8")
ASSISTANT_JS = (ROOT / "panel/static/luna-assistant.js").read_text(encoding="utf-8")
CSS = (ROOT / "panel/static/newsroom-v4.css").read_text(encoding="utf-8")
BASE = (ROOT / "panel/templates/base.html").read_text(encoding="utf-8")
DASHBOARD = (ROOT / "panel/templates/dashboard.html").read_text(encoding="utf-8")


def test_final_panel_v4_assets_are_loaded():
    assert "newsroom-v4.css" in BASE
    assert "newsroom-v4.js" in BASE
    assert "newsroom-v4-dashboard.js" in DASHBOARD


def test_v4_panel_has_luna_preview_before_publish_contract():
    assert "send-luna" in DASHBOARD
    assert "publish-final" in DASHBOARD
    assert "/api/panel/luna/preview/" in DASHBOARD_JS
    assert "/api/panel/luna/publish/" in DASHBOARD_JS
    assert "نسخه نهایی Luna منتشر شود؟" in DASHBOARD_JS


def test_v4_panel_has_real_mobile_navigation_and_confirmation():
    assert "v4-mobile-nav" in BASE
    assert "v4ConfirmDialog" in BASE
    assert "confirmAction" in V4_JS
    assert "safe-area-inset-bottom" in CSS


def test_v4_luna_assistant_is_wired_to_control_api():
    assert "/api/panel/luna/assistant" in ASSISTANT_JS
    assert "confirmation_required" in ASSISTANT_JS
    assert "تأیید و اجرا" in ASSISTANT_JS
