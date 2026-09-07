from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from .editorial_store import LocalEditorialStore
from .manual_publish import publish_review_item, reject_review_item


def load_command_args(path: str | Path) -> dict[str, str]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("invalid_command")
    action = str(payload.get("action") or "").strip()
    item_id = str(payload.get("item_id") or "").strip()
    if action not in {"publish", "reject"}:
        raise ValueError("invalid_action")
    if not item_id:
        raise ValueError("missing_item_id")
    return {
        "action": action,
        "item_id": item_id,
        "title": str(payload.get("title") or ""),
        "body": str(payload.get("body") or ""),
    }


def apply_command(path: str | Path) -> None:
    args = load_command_args(path)
    store = LocalEditorialStore("data/editorial_queue.json", "data/editorial_history.json")
    if args["action"] == "reject":
        reject_review_item(store, args["item_id"])
        return

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "@bikhabaar").strip()
    if not token:
        raise RuntimeError("missing_telegram_token")
    publish_review_item(
        store,
        args["item_id"],
        args["title"],
        args["body"],
        token,
        chat_id,
        state_path="state.json",
    )


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: python -m src.panel_command_file <command.json>")
    apply_command(sys.argv[1])


if __name__ == "__main__":
    main()
