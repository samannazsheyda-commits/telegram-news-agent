from pathlib import Path


def test_vps_updater_forces_http_safe_panel_cookie():
    script = Path("deploy/update-vps.sh").read_text(encoding="utf-8")
    assert 'PANEL_COOKIE_SECURE=0' in script


def test_panel_still_binds_plain_http_port_80():
    unit = Path("deploy/bikhabar-panel.service").read_text(encoding="utf-8")
    assert '--bind 0.0.0.0:80' in unit
