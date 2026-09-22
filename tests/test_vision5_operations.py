from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path


class HealthStore:
    def __init__(self):
        self.current = {}
        self.updates = []

    def get_service_health(self, name):
        return self.current.get(name)

    def update_service_health(self, name, *, status, detail):
        value = {"service_name": name, "status": status, "detail_json": detail}
        self.current[name] = value
        self.updates.append(value)
        return value


class Alerter:
    def __init__(self):
        self.messages = []

    def send(self, *, text, media):
        self.messages.append(text)
        return {"message_id": len(self.messages)}


def test_monitor_persists_checks_and_alerts_only_on_unhealthy_transition():
    from bikhabar_v5.operations import MonitoringService

    store = HealthStore()
    alerter = Alerter()
    probes = {"postgres": lambda: {"ok": True, "detail": "reachable"}, "collector": lambda: {"ok": False, "detail": "stale"}}
    monitor = MonitoringService(store=store, probes=probes, alerter=alerter)

    first = monitor.run()
    second = monitor.run()

    assert first["ok"] is False
    assert store.current["collector"]["status"] == "unhealthy"
    assert len(alerter.messages) == 1
    assert "collector" in alerter.messages[0]
    assert second["checks"]["postgres"]["ok"] is True


class DumpRunner:
    def __init__(self):
        self.commands = []

    def __call__(self, command, *, stdout, check, timeout, env):
        self.commands.append(command)
        assert env["PGDATABASE"] == "postgresql://db/v5"
        stdout.write(b"postgres-backup")


def test_backup_manager_creates_checksum_manifest_in_isolated_directory(tmp_path):
    from bikhabar_v5.operations import BackupManager

    runner = DumpRunner()
    manager = BackupManager(
        database_url="postgresql://db/v5",
        backup_root=tmp_path,
        runner=runner,
        clock=lambda: datetime(2026, 9, 22, 12, 30, tzinfo=timezone.utc),
    )
    result = manager.create()

    assert Path(result["path"]).read_bytes() == b"postgres-backup"
    assert len(result["sha256"]) == 64
    assert runner.commands[0][:2] == ["pg_dump", "--format=custom"]
    assert "postgresql://db/v5" not in " ".join(runner.commands[0])
    assert Path(result["manifest"]).exists()


def test_runtime_settings_validate_operational_limits():
    from bikhabar_v5.operations import RuntimeSettings

    settings = RuntimeSettings.from_mapping(
        {"freshness_hours": "4", "daily_limit": "50", "auto_publish": "false"}
    )

    assert settings.freshness_hours == 4
    assert settings.daily_limit == 50
    assert settings.auto_publish is False
