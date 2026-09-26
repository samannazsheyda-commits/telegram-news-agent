from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_v5_defaults_stay_off_and_worker_is_not_enabled_by_deploy():
    env = (ROOT / "deploy/agent.env.example").read_text(encoding="utf-8")
    deploy = (ROOT / "deploy/update-vps.sh").read_text(encoding="utf-8")
    rollback = (ROOT / "docs/newsroom-v5-rollback.md").read_text(encoding="utf-8")

    for flag in (
        "NEWSROOM_STORE_BACKEND=github",
        "NEWSROOM_V5_UI_ENABLED=false",
        "NEWSROOM_V5_SHADOW_PIPELINE=false",
        "NEWSROOM_V5_TELEGRAM_WRITES_ENABLED=false",
        "NEWSROOM_AUTO_PUBLISH_ENABLED=false",
    ):
        assert flag in env
        assert flag.split("=", 1)[0] in rollback

    assert "bikhabar-newsroom-v5-worker" not in deploy
    assert "NEWSROOM_AUTO_PUBLISH_ENABLED=false" in rollback
    assert "NEWSROOM_STORE_BACKEND=github" in rollback
    assert "Do not skip to automatic publishing." in rollback
