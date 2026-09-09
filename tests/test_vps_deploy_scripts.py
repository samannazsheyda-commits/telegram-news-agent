from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_agent_service_uses_paid_vps_as_live_runtime():
    service = _read("deploy/bikhabar-agent.service")
    assert "Environment=BIKHABAR_RUNTIME_ROOT=/var/lib/bikhabar/runtime" in service
    assert "Environment=DATA_DIR=/var/lib/bikhabar/runtime/data" in service
    assert "Environment=STATE_PATH=/var/lib/bikhabar/runtime/state.json" in service
    assert "Environment=CUSTOM_SOURCES_PATH=/var/lib/bikhabar/runtime/data/custom_sources.json" in service
    assert "Environment=NEWSROOM_SETTINGS_PATH=/var/lib/bikhabar/runtime/data/newsroom_settings.json" in service
    assert "Environment=PANEL_COMMAND_DIR=/var/lib/bikhabar/runtime/panel_commands" in service
    assert "Environment=POLL_SECONDS=5" in service
    assert "Environment=SESSION_SECONDS=0" in service
    assert "python -m src.vps_runtime" in service


def test_panel_service_reads_and_writes_same_local_runtime():
    service = _read("deploy/bikhabar-panel.service")
    assert "Environment=PANEL_LOCAL_ROOT=/var/lib/bikhabar/runtime" in service
    assert "Environment=PANEL_COMMAND_DIR=/var/lib/bikhabar/runtime/panel_commands" in service
    assert "--bind 0.0.0.0:80" in service


def test_env_example_defaults_to_fast_vps_paths():
    env = _read("deploy/agent.env.example")
    assert "POLL_SECONDS=5" in env
    assert "SESSION_SECONDS=0" in env
    assert "DATA_DIR=/var/lib/bikhabar/runtime/data" in env
    assert "PANEL_LOCAL_ROOT=/var/lib/bikhabar/runtime" in env


def test_updater_migrates_live_state_before_git_reset_and_never_restores_into_checkout():
    script = _read("deploy/update-vps.sh")
    migrate_pos = script.index('migrate_once "${APP_DIR}/state.json"')
    reset_pos = script.index('reset --hard "origin/${BRANCH}"')
    assert migrate_pos < reset_pos
    assert 'RUNTIME_ROOT="/var/lib/bikhabar/runtime"' in script
    assert 'migrate_once "${APP_DIR}/data/custom_sources.json"' in script
    assert 'migrate_once "${APP_DIR}/data/newsroom_settings.json"' in script
    assert 'seed_once "${APP_DIR}/data/custom_sources.json"' in script
    assert 'seed_once "${APP_DIR}/data/newsroom_settings.json"' in script
    assert 'curl -fsS --max-time 10 http://127.0.0.1/login' in script
    assert 'cp -a "${SNAPSHOT_DIR}' not in script


def test_installer_creates_runtime_root_and_panel_health_check():
    script = _read("deploy/install-vps.sh")
    assert 'RUNTIME_ROOT="/var/lib/bikhabar/runtime"' in script
    assert 'install -d -o bikhabar -g bikhabar -m 700 "${RUNTIME_ROOT}" "${RUNTIME_DATA}" "${COMMAND_DIR}"' in script
    assert 'seed_once "${APP_DIR}/data/custom_sources.json"' in script
    assert 'seed_once "${APP_DIR}/data/newsroom_settings.json"' in script
    assert 'systemctl restart bikhabar-panel' in script
    assert 'curl -fsS --max-time 10 http://127.0.0.1/login' in script
