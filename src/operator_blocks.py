from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


MAX_OPERATOR_BLOCKS = 2000


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalise_url(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        parts = urlsplit(text)
    except ValueError:
        return text.casefold()
    scheme = parts.scheme.lower()
    host = parts.netloc.lower()
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((scheme, host, path, parts.query, ""))


def _read(path: Path) -> list[dict]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return []
    return [dict(row) for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _atomic_write(path: Path, value: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def add_operator_block(
    path: str | Path,
    *,
    story_id: str = "",
    source_url: str = "",
    fingerprint: str = "",
    title: str = "",
    reason: str = "requested_by_admin",
) -> dict:
    target = Path(path)
    record = {
        "story_id": str(story_id or "").strip(),
        "source_url": _normalise_url(source_url),
        "fingerprint": str(fingerprint or "").strip(),
        "title": str(title or "").strip()[:500],
        "reason": str(reason or "requested_by_admin").strip()[:240] or "requested_by_admin",
        "created_at": _now(),
    }
    if not any((record["story_id"], record["source_url"], record["fingerprint"])):
        raise ValueError("operator block needs a stable story identity")

    rows = _read(target)
    rows = [
        row
        for row in rows
        if not (
            record["story_id"] and str(row.get("story_id") or "") == record["story_id"]
            or record["source_url"] and _normalise_url(str(row.get("source_url") or "")) == record["source_url"]
            or record["fingerprint"] and str(row.get("fingerprint") or "") == record["fingerprint"]
        )
    ]
    _atomic_write(target, [record] + rows[: MAX_OPERATOR_BLOCKS - 1])
    return record


def find_operator_block(
    path: str | Path,
    *,
    story_id: str = "",
    source_url: str = "",
    fingerprint: str = "",
) -> dict | None:
    wanted_story = str(story_id or "").strip()
    wanted_url = _normalise_url(source_url)
    wanted_fp = str(fingerprint or "").strip()
    for row in _read(Path(path)):
        if wanted_story and str(row.get("story_id") or "") == wanted_story:
            return row
        if wanted_url and _normalise_url(str(row.get("source_url") or "")) == wanted_url:
            return row
        if wanted_fp and str(row.get("fingerprint") or "") == wanted_fp:
            return row
    return None
