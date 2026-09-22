from pathlib import Path


def test_vps_updater_clears_only_current_panel_live_feed_once():
    script = Path("deploy/update-vps.sh").read_text(encoding="utf-8")
    assert ".panel-live-reset-2026-09-11-v1" in script
    assert 'PANEL_LIVE_PATH="${RUNTIME_DATA}/panel_live_feed.json"' in script
    assert "printf '[]\\n'" in script
    assert "panel live feed cleared once" in script

    reset_block = script.split("reset_panel_live_once()", 1)[1].split("reset_panel_live_once", 1)[0]
    assert "editorial_history.json" not in reset_block
    assert "telegram" not in reset_block.lower()
    assert "deleteMessage" not in script


def test_vps_updater_stops_agent_before_reset_and_restarts_services_afterwards():
    script = Path("deploy/update-vps.sh").read_text(encoding="utf-8")
    reset_block = script.split("reset_panel_live_once()", 1)[1].split("reset_panel_live_once", 1)[0]
    assert "systemctl stop bikhabar-agent" in reset_block
    assert script.index("reset_panel_live_once") < script.rindex("systemctl restart bikhabar-agent")
