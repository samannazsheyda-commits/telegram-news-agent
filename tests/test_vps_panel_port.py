from pathlib import Path


def test_panel_service_binds_standard_http_port():
    text = Path("deploy/bikhabar-panel.service").read_text(encoding="utf-8")
    assert "--bind 0.0.0.0:80" in text
    assert "CAP_NET_BIND_SERVICE" in text
    assert "0.0.0.0:8080" not in text


def test_vps_updater_health_checks_standard_http_port():
    text = Path("deploy/update-vps.sh").read_text(encoding="utf-8")
    assert "http://127.0.0.1/login" in text
    assert "127.0.0.1:8080" not in text
