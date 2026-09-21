from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping
from urllib.parse import urlparse


class RuntimeConfigurationError(RuntimeError):
    """Raised when Vision 5 production configuration is unsafe or incomplete."""


@dataclass(frozen=True, slots=True)
class ProductionConfig:
    database_url: str
    redis_url: str
    app_root: Path = Path("/opt/bikhabar-vision5")
    data_root: Path = Path("/var/lib/bikhabar/vision5")
    log_root: Path = Path("/var/log/bikhabar/vision5")
    env_file: Path = Path("/etc/bikhabar/v5.env")

    @classmethod
    def from_mapping(cls, values: Mapping[str, str]) -> "ProductionConfig":
        database_url = str(values.get("BIKHABAR_V5_DATABASE_URL") or "").strip()
        redis_url = str(values.get("BIKHABAR_V5_REDIS_URL") or "").strip()

        db_scheme = urlparse(database_url).scheme.lower()
        if db_scheme not in {"postgres", "postgresql"}:
            raise RuntimeConfigurationError(
                "Vision 5 production requires an explicit PostgreSQL BIKHABAR_V5_DATABASE_URL"
            )

        redis_scheme = urlparse(redis_url).scheme.lower()
        if redis_scheme not in {"redis", "rediss"}:
            raise RuntimeConfigurationError(
                "Vision 5 production requires an explicit Redis BIKHABAR_V5_REDIS_URL"
            )

        return cls(database_url=database_url, redis_url=redis_url)
