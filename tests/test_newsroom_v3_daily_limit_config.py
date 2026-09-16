from pathlib import Path


def test_vps_service_persists_daily_limit_35():
    unit = Path("deploy/bikhabar-agent.service").read_text(encoding="utf-8")
    assert "Environment=NEWSROOM_V3_DAILY_LIMIT=35" in unit
