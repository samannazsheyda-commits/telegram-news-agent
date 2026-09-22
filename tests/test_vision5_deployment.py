from __future__ import annotations

from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_runtime_environment_requires_all_production_secrets_and_isolated_paths():
    from bikhabar_v5.runtime import RuntimeEnvironment

    values = {
        "BIKHABAR_V5_DATABASE_URL": "postgresql://db/v5",
        "BIKHABAR_V5_REDIS_URL": "redis://redis/5",
        "BIKHABAR_V5_SECRET_KEY": "s" * 32,
        "BIKHABAR_V5_ADMIN_USERNAME": "editor",
        "BIKHABAR_V5_ADMIN_PASSWORD_HASH": "pbkdf2:sha256:test",
        "BIKHABAR_V5_TELEGRAM_BOT_TOKEN": "token",
        "BIKHABAR_V5_TELEGRAM_CHAT_ID": "@channel",
        "BIKHABAR_V5_OPENAI_API_KEY": "key",
        "BIKHABAR_V5_OPENAI_MODEL": "gpt-test",
    }
    env = RuntimeEnvironment.from_mapping(values)

    assert env.database_url.endswith("/v5")
    assert env.app_root == Path("/opt/bikhabar-vision5")
    with pytest.raises(ValueError):
        RuntimeEnvironment.from_mapping({**values, "BIKHABAR_V5_SECRET_KEY": "short"})


def test_systemd_staging_units_are_isolated_restartable_and_have_recovery_timers():
    unit_root = ROOT / "deploy" / "vision5"
    required = {
        "bikhabar-v5-panel.service",
        "bikhabar-v5-translation.service",
        "bikhabar-v5-publisher.service",
        "bikhabar-v5-collector.service",
        "bikhabar-v5-collector.timer",
        "bikhabar-v5-monitor.service",
        "bikhabar-v5-monitor.timer",
        "bikhabar-v5-backup.service",
        "bikhabar-v5-backup.timer",
        "bikhabar-v5-observation.service",
        "bikhabar-v5-observation.timer",
    }
    assert required.issubset({path.name for path in unit_root.glob("*")})
    combined = "\n".join((unit_root / name).read_text(encoding="utf-8") for name in required)
    assert "/opt/bikhabar-vision5" in combined
    assert "/etc/bikhabar/v5.env" in combined
    assert "Restart=on-failure" in combined
    assert "/opt/bikhabar\n" not in combined
    assert "Persistent=true" in combined


def test_staging_install_script_never_stops_or_overwrites_legacy_services():
    script = (ROOT / "deploy" / "vision5" / "install-staging.sh").read_text(encoding="utf-8")
    assert "systemctl stop bikhabar-agent" not in script
    assert "systemctl disable bikhabar-agent" not in script
    assert "rm -rf /opt/bikhabar" not in script
    assert "bikhabar-v5" in script
