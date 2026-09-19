from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class PaceDecision:
    allow: bool
    route: str
    reason: str
    retry_after_seconds: int = 0


class AutoPublishPacer:
    def __init__(self, *, min_interval_seconds: int = 20) -> None:
        self.min_interval_seconds = max(0, int(min_interval_seconds))

    def decide(
        self,
        *,
        now: datetime | None = None,
        last_publish_at: datetime | None = None,
        daily_limit_reached: bool = False,
        paused: bool = False,
    ) -> PaceDecision:
        now = now or datetime.now(timezone.utc)
        if daily_limit_reached:
            return PaceDecision(False, "review", "daily_limit_reached", 0)
        if paused:
            return PaceDecision(False, "review", "auto_publish_paused", 0)
        if last_publish_at is None or self.min_interval_seconds <= 0:
            return PaceDecision(True, "publish", "allowed", 0)
        elapsed = max(0.0, (now - last_publish_at).total_seconds())
        remaining = max(0, int(round(self.min_interval_seconds - elapsed)))
        if remaining > 0:
            return PaceDecision(False, "review", "anti_flood_pacing", remaining)
        return PaceDecision(True, "publish", "allowed", 0)
