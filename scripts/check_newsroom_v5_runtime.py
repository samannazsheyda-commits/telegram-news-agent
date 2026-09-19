from __future__ import annotations

import argparse
import json
import os
import sqlite3
from pathlib import Path
from urllib.parse import urlparse


REQUIRED_TABLES = {
    "stories", "translations", "editorial_decisions", "publications",
    "story_tombstones", "sources", "jobs", "luna_conversations", "audit_log",
}


def check_runtime(db_path: str | Path, *, public_url: str = "") -> dict:
    path = Path(db_path).expanduser()
    report = {
        "ok": True,
        "db_path": str(path),
        "db_exists": path.is_file(),
        "parent_writable": os.access(path.parent if path.parent.exists() else path.parent.parent, os.W_OK),
        "journal_mode": None,
        "foreign_keys": None,
        "missing_tables": [],
        "https_ready": None,
        "errors": [],
    }
    if public_url:
        report["https_ready"] = urlparse(public_url).scheme.lower() == "https"
        if not report["https_ready"]:
            report["errors"].append("public_url_is_not_https_voice_capture_may_be_limited")

    if not path.is_file():
        report["ok"] = False
        report["errors"].append("sqlite_database_missing")
        return report

    try:
        uri = f"file:{path.resolve()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=2.0)
        try:
            report["journal_mode"] = str(conn.execute("PRAGMA journal_mode").fetchone()[0]).lower()
            # foreign_keys is connection-local and defaults off for this read-only
            # inspection connection; report schema integrity separately.
            report["foreign_keys"] = [
                dict(zip(("id", "seq", "table", "from", "to", "on_update", "on_delete", "match"), row))
                for row in conn.execute("PRAGMA foreign_key_list(translations)").fetchall()
            ]
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            report["missing_tables"] = sorted(REQUIRED_TABLES - tables)
            integrity = conn.execute("PRAGMA quick_check").fetchone()[0]
            report["quick_check"] = integrity
        finally:
            conn.close()
    except Exception as exc:
        report["ok"] = False
        report["errors"].append(f"sqlite_read_failed:{type(exc).__name__}:{exc}")
        return report

    if report["journal_mode"] != "wal":
        report["ok"] = False
        report["errors"].append("journal_mode_is_not_wal")
    if report["missing_tables"]:
        report["ok"] = False
        report["errors"].append("required_tables_missing")
    if report.get("quick_check") != "ok":
        report["ok"] = False
        report["errors"].append("sqlite_quick_check_failed")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only Newsroom V5 runtime preflight")
    parser.add_argument("--db", default=os.environ.get("NEWSROOM_SQLITE_PATH", "/var/lib/bikhabar/newsroom-v5.db"))
    parser.add_argument("--public-url", default=os.environ.get("PANEL_PUBLIC_URL", ""))
    args = parser.parse_args()
    report = check_runtime(args.db, public_url=args.public_url)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
