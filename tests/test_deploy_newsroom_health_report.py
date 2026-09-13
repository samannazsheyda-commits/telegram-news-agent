from pathlib import Path


def test_vps_update_prints_newsroom_health_report():
    script = Path("deploy/update-vps.sh").read_text(encoding="utf-8")

    assert "NEWSROOM HEALTH" in script
    assert "panel_live_feed.json" in script
    assert "publish_failed" in script
    assert "telegram_writes" in script
