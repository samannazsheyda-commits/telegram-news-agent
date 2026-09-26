from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.newsroom_v5_migration import migrate_local_snapshot
from src.newsroom_v5_store import NewsroomV5Store


def main() -> int:
    parser = argparse.ArgumentParser(description="Import legacy newsroom JSON into the V5 SQLite store")
    parser.add_argument("--db", required=True)
    parser.add_argument("--from-local-repo", default=".")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    # Dry-run only builds the projection; opening the store would create the DB file.
    store = NewsroomV5Store(args.db if args.apply else ":memory:")
    try:
        report = migrate_local_snapshot(args.from_local_repo, store, apply=bool(args.apply))
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if not report.get("conflicts") else 2
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
