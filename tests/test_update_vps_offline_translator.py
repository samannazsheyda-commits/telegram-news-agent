from pathlib import Path


def test_update_vps_installs_offline_translator_before_agent_restart():
    script = Path("deploy/update-vps.sh").read_text(encoding="utf-8")

    install_call = '"${APP_DIR}/deploy/install-offline-translator.sh"'
    restart_call = "systemctl restart bikhabar-agent"

    assert install_call in script
    assert script.index(install_call) < script.rindex(restart_call)


def test_agent_service_forces_offline_translation_enabled_after_env_file():
    service = Path("deploy/bikhabar-agent.service").read_text(encoding="utf-8")

    env_file = "EnvironmentFile=/etc/bikhabar/agent.env"
    force_enable = "Environment=OFFLINE_TRANSLATION_ENABLED=1"

    assert force_enable in service
    assert service.index(env_file) < service.index(force_enable)
