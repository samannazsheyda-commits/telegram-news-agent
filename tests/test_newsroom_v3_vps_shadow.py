from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_v3_shadow_service_is_one_shot_and_cannot_publish():
    service = _read("deploy/bikhabar-newsroom-v3-shadow.service")
    assert "Type=oneshot" in service
    assert "User=bikhabar" in service
    assert "EnvironmentFile=/etc/bikhabar/agent.env" in service
    assert "python -m src.newsroom_v3.runtime" in service
    assert "--data-dir /var/lib/bikhabar/runtime/data" in service
    assert "--canary" not in service
    assert "MemoryMax=" in service


def test_v3_shadow_timer_runs_repeatedly_without_overlap_pressure():
    timer = _read("deploy/bikhabar-newsroom-v3-shadow.timer")
    assert "OnBootSec=" in timer
    assert "OnUnitActiveSec=" in timer
    assert "Unit=bikhabar-newsroom-v3-shadow.service" in timer
    assert "Persistent=true" in timer


def test_updater_installs_enables_and_health_checks_v3_shadow():
    script = _read("deploy/update-vps.sh")
    assert 'bikhabar-newsroom-v3-shadow.service' in script
    assert 'bikhabar-newsroom-v3-shadow.timer' in script
    assert 'systemctl is-active --quiet bikhabar-newsroom-v3-shadow.timer' in script
    assert 'V3_SHADOW_TIMER=' in script
    assert 'newsroom_v3_shadow_status.json' in script


def test_installer_wires_v3_shadow_for_fresh_vps_installs():
    script = _read("deploy/install-vps.sh")
    assert 'bikhabar-newsroom-v3-shadow.service' in script
    assert 'bikhabar-newsroom-v3-shadow.timer' in script
    assert 'systemctl is-active --quiet bikhabar-newsroom-v3-shadow.timer' in script
