from pathlib import Path


def test_v3_default_daily_limit_is_35():
    source = Path("src/newsroom_v3/production.py").read_text(encoding="utf-8")
    assert 'os.environ.get("NEWSROOM_V3_DAILY_LIMIT", "35")' in source


def test_vps_deploy_persists_daily_limit_35():
    deploy = Path("deploy/update-vps.sh").read_text(encoding="utf-8")
    assert '"NEWSROOM_V3_DAILY_LIMIT=35"' in deploy
