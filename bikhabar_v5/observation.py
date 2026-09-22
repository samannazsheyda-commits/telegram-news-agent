from __future__ import annotations

import fcntl
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable


class ObservationLedger:
    def __init__(
        self,
        *,
        root: str | Path,
        store: Any,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self.root = Path(root).resolve()
        self.store = store
        self.clock = clock
        self.path = self.root / "vision5-observation.jsonl"

    def record(self) -> dict[str, Any]:
        self.root.mkdir(parents=True, exist_ok=True, mode=0o750)
        health = self.store.list_service_health()
        metrics = self.store.dashboard_metrics()
        healthy = bool(health) and all(str(row.get("status")) == "healthy" for row in health)
        healthy = healthy and int(metrics.get("publish_failed") or 0) == 0
        sample = {
            "observed_at": self.clock().astimezone(timezone.utc).isoformat(),
            "healthy": healthy,
            "health": health,
            "metrics": metrics,
        }
        with self.path.open("a", encoding="utf-8") as output:
            fcntl.flock(output.fileno(), fcntl.LOCK_EX)
            output.write(json.dumps(sample, ensure_ascii=False, sort_keys=True, default=str) + "\n")
            output.flush()
            os.fsync(output.fileno())
            fcntl.flock(output.fileno(), fcntl.LOCK_UN)
        return sample

    def verify(self, *, hours: int = 24) -> dict[str, Any]:
        required_hours = max(1, int(hours))
        if not self.path.exists():
            return {
                "ok": False,
                "sample_count": 0,
                "unhealthy_samples": 0,
                "duration_hours": 0.0,
                "required_hours": required_hours,
            }
        samples = [
            json.loads(line)
            for line in self.path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        samples.sort(key=lambda row: row["observed_at"])
        last_at = datetime.fromisoformat(samples[-1]["observed_at"])
        cutoff = last_at - timedelta(hours=required_hours)
        window = [row for row in samples if datetime.fromisoformat(row["observed_at"]) >= cutoff]
        first_at = datetime.fromisoformat(window[0]["observed_at"])
        duration_hours = (last_at - first_at).total_seconds() / 3600
        unhealthy = sum(1 for row in window if not bool(row.get("healthy")))
        return {
            "ok": duration_hours >= required_hours and unhealthy == 0,
            "sample_count": len(window),
            "unhealthy_samples": unhealthy,
            "duration_hours": duration_hours,
            "required_hours": required_hours,
            "from": first_at.isoformat(),
            "to": last_at.isoformat(),
        }
