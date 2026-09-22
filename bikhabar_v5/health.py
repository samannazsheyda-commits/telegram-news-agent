from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .config import ProductionConfig


Check = dict[str, bool | str]
PostgresFactory = Callable[[str], Any]
RedisFactory = Callable[[str], Any]


def _default_postgres_factory(database_url: str):
    import psycopg

    return psycopg.connect(database_url, autocommit=True)


def _default_redis_factory(redis_url: str):
    import redis

    return redis.Redis.from_url(redis_url, decode_responses=True)


def _is_within(path: Path, parent: Path) -> bool:
    resolved_path = path.resolve(strict=False)
    resolved_parent = parent.resolve(strict=False)
    return resolved_path == resolved_parent or resolved_parent in resolved_path.parents


def _path_check(config: ProductionConfig) -> Check:
    legacy_roots = (Path("/opt/bikhabar"), Path("/var/lib/bikhabar/runtime"))
    configured = (config.app_root, config.data_root, config.log_root, config.env_file)
    if any(_is_within(path, legacy) for path in configured for legacy in legacy_roots):
        return {"ok": False, "detail": "Vision 5 paths overlap the legacy runtime"}
    return {"ok": True, "detail": "isolated"}


def _postgres_check(database_url: str, factory: PostgresFactory) -> Check:
    connection = None
    try:
        connection = factory(database_url)
        row = connection.execute("SELECT 1").fetchone()
        if not row or int(row[0]) != 1:
            return {"ok": False, "detail": "unexpected SELECT 1 result"}
        return {"ok": True, "detail": "reachable"}
    except Exception as exc:
        return {"ok": False, "detail": str(exc) or exc.__class__.__name__}
    finally:
        if connection is not None:
            connection.close()


def _redis_check(redis_url: str, factory: RedisFactory) -> Check:
    client = None
    try:
        client = factory(redis_url)
        if client.ping() is not True:
            return {"ok": False, "detail": "ping returned false"}
        return {"ok": True, "detail": "reachable"}
    except Exception as exc:
        return {"ok": False, "detail": str(exc) or exc.__class__.__name__}
    finally:
        if client is not None:
            client.close()


def run_preflight(
    config: ProductionConfig,
    *,
    postgres_factory: PostgresFactory = _default_postgres_factory,
    redis_factory: RedisFactory = _default_redis_factory,
) -> dict[str, Any]:
    checks = {
        "paths": _path_check(config),
        "postgres": _postgres_check(config.database_url, postgres_factory),
        "redis": _redis_check(config.redis_url, redis_factory),
    }
    return {"ok": all(bool(check["ok"]) for check in checks.values()), "checks": checks}
