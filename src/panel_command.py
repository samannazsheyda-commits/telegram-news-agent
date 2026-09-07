from __future__ import annotations

import argparse
import os

from .editorial_store import LocalEditorialStore
from .manual_publish import publish_review_item, reject_review_item


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["publish", "reject"])
    parser.add_argument("item_id")
    parser.add_argument("--title", default="")
    parser.add_argument("--body", default="")
    args = parser.parse_args()

    store = LocalEditorialStore("data/editorial_queue.json", "data/editorial_history.json")
    if args.action == "reject":
        reject_review_item(store, args.item_id)
        return

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "@bikhabaar").strip()
    if not token:
        raise RuntimeError("missing_telegram_token")
    publish_review_item(
        store,
        args.item_id,
        args.title,
        args.body,
        token,
        chat_id,
        state_path="state.json",
    )


if __name__ == "__main__":
    main()
