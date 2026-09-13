from pathlib import Path

from src.newsroom_runtime_v2 import _offline_translation_enabled


def test_update_vps_installs_offline_translator_before_agent_restart():
    script = Path("deploy/update-vps.sh").read_text(encoding="utf-8")

    install_call = '"${APP_DIR}/deploy/install-offline-translator.sh"'
    restart_call = "systemctl restart bikhabar-agent"

    assert install_call in script
    assert script.index(install_call) < script.rindex(restart_call)


def test_agent_service_forces_offline_translation_disabled_on_low_memory_vps():
    service = Path("deploy/bikhabar-agent.service").read_text(encoding="utf-8")

    env_file = "EnvironmentFile=/etc/bikhabar/agent.env"
    force_disable = "Environment=OFFLINE_TRANSLATION_ENABLED=0"

    assert force_disable in service
    assert service.index(env_file) < service.index(force_disable)


def test_runtime_defaults_offline_translation_disabled(monkeypatch):
    monkeypatch.delenv("OFFLINE_TRANSLATION_ENABLED", raising=False)

    assert _offline_translation_enabled() is False
