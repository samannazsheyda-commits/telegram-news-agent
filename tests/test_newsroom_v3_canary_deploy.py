from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_v3_canary_service_is_manual_one_shot_with_offline_mt_disabled():
    service = _read("deploy/bikhabar-newsroom-v3-canary.service")
    assert "Type=oneshot" in service
    assert "User=bikhabar" in service
    assert "EnvironmentFile=/etc/bikhabar/agent.env" in service
    assert "Environment=OFFLINE_TRANSLATION_ENABLED=0" in service
    assert "python -m src.newsroom_v3.canary" in service
    assert "--data-dir /var/lib/bikhabar/runtime/data" in service
    assert "--confirm-one-shot" in service
    assert "AI_NEWSROOM_MODE=" not in service
    assert not (ROOT / "deploy/bikhabar-newsroom-v3-canary.timer").exists()


def test_updater_runs_canary_with_v2_stopped_and_restores_v2_afterward():
    script = _read("deploy/update-vps.sh")
    assert 'install -m 644 "${APP_DIR}/deploy/bikhabar-newsroom-v3-canary.service"' in script
    assert 'CANARY_MARKER="${RUNTIME_DATA}/newsroom_v3_canary_once.json"' in script
    marker_pos = script.index("CANARY_MARKER=")
    preflight_pos = script.index("--preflight", marker_pos)
    stop_pos = script.index("systemctl stop bikhabar-agent", marker_pos)
    canary_pos = script.index("systemctl start bikhabar-newsroom-v3-canary.service", stop_pos)
    restore_pos = script.index("systemctl restart bikhabar-agent", canary_pos)
    assert preflight_pos < stop_pos < canary_pos < restore_pos
    preflight_block = script[marker_pos:stop_pos]
    assert 'cd "${APP_DIR}"' in preflight_block
    assert 'if [[ ! -f "${CANARY_MARKER}" ]]' in script
    assert "newsroom_v3_canary_once.json" in script


def test_fresh_installer_installs_but_does_not_auto_enable_canary():
    script = _read("deploy/install-vps.sh")
    assert 'install -m 644 "${APP_DIR}/deploy/bikhabar-newsroom-v3-canary.service"' in script
    assert "systemctl enable bikhabar-newsroom-v3-canary" not in script
    assert "systemctl start bikhabar-newsroom-v3-canary" not in script
