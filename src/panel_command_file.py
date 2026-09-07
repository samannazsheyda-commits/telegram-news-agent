from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import requests

from .editorial_store import LocalEditorialStore
from .manual_publish import publish_review_item, reject_review_item
from .runtime_v12 import _normalise_url, extract_public_telegram_source_links
from .sources import USER_AGENT


OWN_CHANNEL = "bikhabaar"


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


def _source_already_published_in_channel(source_url: str, session=requests) -> bool:
    """Strict preflight for browser publish.

    A publish command must never send while we are unable to verify our own public
    channel history. This makes command retries fail closed instead of duplicating a
    Telegram post after a partial workflow failure.
    """
    source_url = _normalise_url(source_url)
    if not source_url:
        return False
    response = session.get(
        f"https://t.me/s/{OWN_CHANNEL}",
        headers={"User-Agent": USER_AGENT},
        timeout=15,
    )
    response.raise_for_status()
    published_links = {
        _normalise_url(link)
        for link in extract_public_telegram_source_links(response.text, OWN_CHANNEL)
        if link
    }
    return source_url in published_links


def _record_already_published(store: LocalEditorialStore, item, title: str, body: str) -> None:
    """Consume an already-visible manual publication without sending Telegram again."""
    store.move_to_history(
        item.id,
        status="published_manual",
        final_persian_title=(title or "").strip() or str(getattr(item, "persian_title", "") or "").strip(),
        final_persian_body=(body or "").strip() or str(getattr(item, "persian_body", "") or "").strip(),
    )


def apply_command(path: str | Path) -> None:
    args = load_command_args(path)
    store = LocalEditorialStore("data/editorial_queue.json", "data/editorial_history.json")
    if args["action"] == "reject":
        try:
            reject_review_item(store, args["item_id"])
        except ValueError as exc:
            # Retrying an already-consumed reject is a no-op, not a workflow failure.
            if str(exc) != "not_pending":
                raise
        return

    item = store.get_pending(args["item_id"])
    if item is None:
        # A retry after the first successful state transition must not resend.
        existing = next(
            (
                row
                for row in store.history()
                if row.get("id") == args["item_id"]
                and row.get("status") in {"published_manual", "published_auto"}
            ),
            None,
        )
        if existing is not None:
            return
        raise ValueError("not_pending")

    # Do the strict own-channel check BEFORE reading the Telegram token or sending.
    # If the check fails, the command stays on disk and can safely retry later.
    if _source_already_published_in_channel(item.source_url):
        _record_already_published(store, item, args["title"], args["body"])
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
