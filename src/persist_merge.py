from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from .editorial_store import merge_record_sets


RECENT_PUBLISHED_LIMIT = 300


def _read(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _normalise_link(value: object) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        parts = urlsplit(raw)
        return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), "", ""))
    except ValueError:
        return raw


def _text_fingerprint(record: dict) -> str:
    text = f"{record.get('title') or ''} {record.get('summary') or ''}".lower()
    return " ".join(re.findall(r"[a-z0-9\u0600-\u06ff]+", text))


def _record_identity(record: dict) -> tuple[str, str, str]:
    return (
        str(record.get("key") or "").strip(),
        _normalise_link(record.get("link")),
        str(record.get("fingerprint") or "").strip() or _text_fingerprint(record),
    )


def _merge_recent_published(remote: list, local: list) -> list:
    merged: list[dict] = []
    seen_keys: set[str] = set()
    seen_links: set[str] = set()
    seen_fingerprints: set[str] = set()
    for raw in list(local or []) + list(remote or []):
        if not isinstance(raw, dict):
            continue
        record = dict(raw)
        key, link, fingerprint = _record_identity(record)
        if (key and key in seen_keys) or (link and link in seen_links) or (fingerprint and fingerprint in seen_fingerprints):
            continue
        if fingerprint:
            record["fingerprint"] = fingerprint
        if key:
            seen_keys.add(key)
        if link:
            seen_links.add(link)
        if fingerprint:
            seen_fingerprints.add(fingerprint)
        merged.append(record)
        if len(merged) >= RECENT_PUBLISHED_LIMIT:
            break
    return merged


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
    result["recent_published_news"] = _merge_recent_published(
        list((remote or {}).get("recent_published_news") or []),
        list((local or {}).get("recent_published_news") or []),
    )
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
