from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping
from typing import Any, TextIO

from .config import ProductionConfig, RuntimeConfigurationError
from .health import PostgresFactory, RedisFactory, run_preflight


def main(
    environ: Mapping[str, str] | None = None,
    *,
    postgres_factory: PostgresFactory | None = None,
    redis_factory: RedisFactory | None = None,
    stdout: TextIO | None = None,
) -> int:
    destination = stdout or sys.stdout
    try:
        config = ProductionConfig.from_mapping(environ or os.environ)
        options: dict[str, Any] = {}
        if postgres_factory is not None:
            options["postgres_factory"] = postgres_factory
        if redis_factory is not None:
            options["redis_factory"] = redis_factory
        report = run_preflight(config, **options)
    except RuntimeConfigurationError as exc:
        report = {
            "ok": False,
            "checks": {"configuration": {"ok": False, "detail": str(exc)}},
        }
    destination.write(json.dumps(report, ensure_ascii=False, sort_keys=True) + "\n")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
