from __future__ import annotations

import json
import sys
from pathlib import Path

from .editorial_store import merge_record_sets


def _read(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def merge_state(remote: dict, local: dict) -> dict:
    result = dict(remote or {})
    result.update(local or {})
    remote_seen = list((remote or {}).get("news_seen") or [])
    local_seen = list((local or {}).get("news_seen") or [])
    seen: list[str] = []
    used = set()
    for key in local_seen + remote_seen:
        if key in used:
            continue
        used.add(key)
        seen.append(key)
    result["news_seen"] = seen[:500]
    return result


def merge_snapshot(snapshot_dir: str | Path, repo_dir: str | Path = ".") -> None:
    snapshot = Path(snapshot_dir)
    repo = Path(repo_dir)

    remote_state = _read(repo / "state.json", {})
    local_state = _read(snapshot / "state.json", {})
    _write(repo / "state.json", merge_state(remote_state, local_state))

    for rel in ("data/editorial_queue.json", "data/editorial_history.json"):
        remote_records = _read(repo / rel, [])
        local_records = _read(snapshot / rel, [])
        if not isinstance(remote_records, list):
            remote_records = []
        if not isinstance(local_records, list):
            local_records = []
        _write(repo / rel, merge_record_sets(remote_records, local_records))


def _cli() -> int:
    if len(sys.argv) != 2:
        print("usage: python -m src.persist_merge SNAPSHOT_DIR", file=sys.stderr)
        return 2
    merge_snapshot(sys.argv[1], ".")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
