from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import requests


AUDIT_PATH = "data/panel_audit_log.json"
MAX_ROWS = 2000


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def append_audit(
    data,
    *,
    actor: str,
    action: str,
    target: str,
    before: Any,
    after: Any,
    result: str,
) -> dict:
    row = {
        "timestamp": _now(),
        "actor": str(actor or "system"),
        "action": str(action or "unknown"),
        "target": str(target or ""),
        "before": before,
        "after": after,
        "result": str(result or "unknown"),
    }
    for attempt in range(3):
        current, sha = data.read_json(AUDIT_PATH, [])
        rows = [dict(item) for item in current if isinstance(item, dict)] if isinstance(current, list) else []
        rows.insert(0, row)
        rows = rows[:MAX_ROWS]
        try:
            data.write_json(AUDIT_PATH, rows, sha, "panel v4: append audit log")
            return row
        except requests.HTTPError as exc:
            if attempt < 2 and getattr(exc.response, "status_code", None) in {409, 422}:
                continue
            raise
    raise RuntimeError("audit_log_write_conflict")


def list_audit(data, *, limit: int = 50, actor: str = "", action: str = "") -> list[dict]:
    current, _ = data.read_json(AUDIT_PATH, [])
    rows = [dict(item) for item in current if isinstance(item, dict)] if isinstance(current, list) else []
    if actor:
        rows = [row for row in rows if str(row.get("actor") or "") == actor]
    if action:
        rows = [row for row in rows if str(row.get("action") or "") == action]
    return rows[: max(1, min(500, int(limit or 50)))]
