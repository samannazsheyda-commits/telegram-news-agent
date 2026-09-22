from __future__ import annotations

from dataclasses import replace
from io import StringIO
from pathlib import Path
import json

from bikhabar_v5.config import ProductionConfig


class FakePostgresConnection:
    def __init__(self, *, fails: bool = False) -> None:
        self.fails = fails
        self.closed = False

    def execute(self, statement: str):
        assert statement == "SELECT 1"
        if self.fails:
            raise RuntimeError("postgres unavailable")
        return self

    def fetchone(self):
        return (1,)

    def close(self) -> None:
        self.closed = True


class FakeRedisClient:
    def __init__(self, *, healthy: bool = True) -> None:
        self.healthy = healthy
        self.closed = False

    def ping(self) -> bool:
        return self.healthy

    def close(self) -> None:
        self.closed = True


def _config(tmp_path: Path) -> ProductionConfig:
    base = ProductionConfig.from_mapping(
        {
            "BIKHABAR_V5_DATABASE_URL": "postgresql://vision5:test@127.0.0.1:5432/vision5",
            "BIKHABAR_V5_REDIS_URL": "redis://127.0.0.1:6379/5",
        }
    )
    return replace(
        base,
        app_root=tmp_path / "opt" / "bikhabar-vision5",
        data_root=tmp_path / "var" / "lib" / "bikhabar" / "vision5",
        log_root=tmp_path / "var" / "log" / "bikhabar" / "vision5",
        env_file=tmp_path / "etc" / "bikhabar" / "v5.env",
    )


def test_preflight_reports_isolated_paths_and_live_dependencies(tmp_path):
    from bikhabar_v5.health import run_preflight

    postgres = FakePostgresConnection()
    redis = FakeRedisClient()
    report = run_preflight(
        _config(tmp_path),
        postgres_factory=lambda _url: postgres,
        redis_factory=lambda _url: redis,
    )

    assert report["ok"] is True
    assert report["checks"] == {
        "paths": {"ok": True, "detail": "isolated"},
        "postgres": {"ok": True, "detail": "reachable"},
        "redis": {"ok": True, "detail": "reachable"},
    }
    assert postgres.closed is True
    assert redis.closed is True


def test_preflight_fails_closed_when_a_dependency_is_unhealthy(tmp_path):
    from bikhabar_v5.health import run_preflight

    report = run_preflight(
        _config(tmp_path),
        postgres_factory=lambda _url: FakePostgresConnection(fails=True),
        redis_factory=lambda _url: FakeRedisClient(healthy=False),
    )

    assert report["ok"] is False
    assert report["checks"]["postgres"] == {"ok": False, "detail": "postgres unavailable"}
    assert report["checks"]["redis"] == {"ok": False, "detail": "ping returned false"}


def test_preflight_rejects_any_path_overlapping_legacy_runtime(tmp_path):
    from bikhabar_v5.health import run_preflight

    config = replace(_config(tmp_path), app_root=Path("/opt/bikhabar/app"))
    report = run_preflight(
        config,
        postgres_factory=lambda _url: FakePostgresConnection(),
        redis_factory=lambda _url: FakeRedisClient(),
    )

    assert report["ok"] is False
    assert report["checks"]["paths"] == {
        "ok": False,
        "detail": "Vision 5 paths overlap the legacy runtime",
    }


def test_preflight_cli_returns_machine_readable_status():
    from bikhabar_v5.preflight import main

    output = StringIO()
    code = main(
        {
            "BIKHABAR_V5_DATABASE_URL": "postgresql://vision5:test@127.0.0.1:5432/vision5",
            "BIKHABAR_V5_REDIS_URL": "redis://127.0.0.1:6379/5",
        },
        postgres_factory=lambda _url: FakePostgresConnection(),
        redis_factory=lambda _url: FakeRedisClient(),
        stdout=output,
    )

    assert code == 0
    payload = json.loads(output.getvalue())
    assert payload["ok"] is True
    assert payload["checks"]["postgres"]["detail"] == "reachable"
