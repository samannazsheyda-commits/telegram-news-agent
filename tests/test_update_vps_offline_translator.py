from pathlib import Path


def test_update_vps_installs_offline_translator_before_agent_restart():
    script = Path("deploy/update-vps.sh").read_text(encoding="utf-8")

    install_call = '"${APP_DIR}/deploy/install-offline-translator.sh"'
    restart_call = "systemctl restart bikhabar-agent"

    assert install_call in script
    assert script.index(install_call) < script.rindex(restart_call)
