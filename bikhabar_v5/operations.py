from __future__ import annotations

import hashlib
import json
import os
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _boolean(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class RuntimeSettings:
    freshness_hours: int = 6
    daily_limit: int = 50
    auto_publish: bool = False

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any]) -> "RuntimeSettings":
        freshness = int(values.get("freshness_hours", 6))
        daily_limit = int(values.get("daily_limit", 50))
        if not 1 <= freshness <= 72:
            raise ValueError("freshness_hours must be between 1 and 72")
        if not 0 <= daily_limit <= 500:
            raise ValueError("daily_limit must be between 0 and 500")
        return cls(
            freshness_hours=freshness,
            daily_limit=daily_limit,
            auto_publish=_boolean(values.get("auto_publish", False)),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class MonitoringService:
    def __init__(self, *, store: Any, probes: Mapping[str, Callable[[], Mapping[str, Any]]], alerter: Any | None = None) -> None:
        self.store = store
        self.probes = dict(probes)
        self.alerter = alerter

    def run(self) -> dict[str, Any]:
        checks: dict[str, dict[str, Any]] = {}
        for name, probe in self.probes.items():
            previous = self.store.get_service_health(name)
            try:
                raw = dict(probe())
                ok = bool(raw.get("ok"))
                detail = str(raw.get("detail") or ("healthy" if ok else "probe failed"))
            except Exception as exc:
                ok = False
                detail = str(exc) or exc.__class__.__name__
            status = "healthy" if ok else "unhealthy"
            check = {"ok": ok, "detail": detail}
            checks[name] = check
            self.store.update_service_health(name, status=status, detail=check)
            previous_status = str((previous or {}).get("status") or "unknown")
            if not ok and previous_status != "unhealthy" and self.alerter is not None:
                self.alerter.send(
                    text=f"هشدار بی‌خبر V5\n\n{name}: {detail}",
                    media={},
                )
        return {"ok": all(check["ok"] for check in checks.values()), "checks": checks}


class BackupManager:
    def __init__(
        self,
        *,
        database_url: str,
        backup_root: str | Path,
        retention: int = 14,
        runner: Callable[..., Any] = subprocess.run,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self.database_url = str(database_url or "").strip()
        if not self.database_url:
            raise ValueError("database_url is required")
        self.backup_root = Path(backup_root).resolve()
        if self.backup_root == Path("/") or self.backup_root == Path("/opt/bikhabar"):
            raise ValueError("unsafe backup_root")
        self.retention = max(1, min(int(retention), 90))
        self.runner = runner
        self.clock = clock

    def create(self) -> dict[str, str]:
        self.backup_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        stamp = self.clock().astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        destination = self.backup_root / f"bikhabar-v5-{stamp}.dump"
        partial = destination.with_suffix(".dump.partial")
        environment = os.environ.copy()
        environment["PGDATABASE"] = self.database_url
        try:
            with partial.open("wb") as output:
                self.runner(
                    ["pg_dump", "--format=custom", "--no-owner", "--no-privileges"],
                    stdout=output,
                    check=True,
                    timeout=1800,
                    env=environment,
                )
            if partial.stat().st_size == 0:
                raise RuntimeError("pg_dump produced an empty backup")
            partial.replace(destination)
        finally:
            if partial.exists():
                partial.unlink()
        digest = hashlib.sha256(destination.read_bytes()).hexdigest()
        manifest = destination.with_suffix(".json")
        manifest.write_text(
            json.dumps(
                {
                    "created_at": self.clock().astimezone(timezone.utc).isoformat(),
                    "filename": destination.name,
                    "sha256": digest,
                    "size_bytes": destination.stat().st_size,
                },
                sort_keys=True,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        self._prune()
        return {"path": str(destination), "manifest": str(manifest), "sha256": digest}

    def _prune(self) -> None:
        backups = sorted(self.backup_root.glob("bikhabar-v5-*.dump"), reverse=True)
        for old in backups[self.retention :]:
            manifest = old.with_suffix(".json")
            old.unlink()
            if manifest.exists():
                manifest.unlink()
