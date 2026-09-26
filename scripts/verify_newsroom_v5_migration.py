from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.newsroom_v5_migration_verify import verify_local_snapshot
from src.newsroom_v5_store import NewsroomV5Store


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify legacy JSON and Newsroom V5 SQLite parity")
    parser.add_argument("--db", required=True)
    parser.add_argument("--from-local-repo", default=".")
    args = parser.parse_args()

    store = NewsroomV5Store(args.db)
    try:
        report = verify_local_snapshot(args.from_local_repo, store)
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if report["ok"] else 2
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
