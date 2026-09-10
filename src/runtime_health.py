from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {}
    return dict(value) if isinstance(value, dict) else {}


def _write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def health_path(data_dir: str | Path | None = None) -> Path:
    root = Path(data_dir or os.environ.get("DATA_DIR", "data"))
    return root / "runtime_health.json"


def record_cycle(result: dict[str, Any], *, started_at: str, finished_at: str | None = None, path: str | Path | None = None) -> dict[str, Any]:
    target = Path(path) if path is not None else health_path()
    previous = _read(target)
    finished = finished_at or _now()
    published = int(result.get("published") or result.get("telegram_writes") or 0)
    publish_failed = int(result.get("publish_failed") or 0)
    rc = int(result.get("rc") or 0)

    telegram_state = str(previous.get("telegram_state") or "unknown")
    if published > 0:
        telegram_state = "ok"
    elif publish_failed > 0:
        telegram_state = "error"

    last_publication = str(previous.get("last_publication_at") or "")
    if published > 0:
        last_publication = finished

    last_error = ""
    if rc != 0:
        last_error = str(result.get("error") or f"runtime_rc_{rc}")
    elif publish_failed > 0:
        last_error = f"{publish_failed} انتشار ناموفق"
    elif int(result.get("sources_failed") or 0) > 0:
        last_error = f"{int(result.get('sources_failed') or 0)} منبع ناموفق"

    value = {
        "cycle_started_at": started_at,
        "last_cycle_at": finished,
        "last_publication_at": last_publication,
        "last_error": last_error,
        "telegram_state": telegram_state,
        "sources_ok": int(result.get("sources_ok") or 0),
        "sources_failed": int(result.get("sources_failed") or 0),
        "items_fetched": int(result.get("items_fetched") or 0),
        "published": published,
        "publish_failed": publish_failed,
        "panel_feed_count": int(result.get("panel_feed_count") or 0),
        "mode": str(result.get("mode") or "production"),
        "rc": rc,
    }
    _write(target, value)
    return value
