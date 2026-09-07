from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import requests

from .editorial_store import LocalEditorialStore
from .manual_publish import publish_review_item, reject_review_item
from .runtime_v12 import _normalise_url, extract_public_telegram_source_links
from .services import send_telegram
from .sources import USER_AGENT

OWN_CHANNEL = "bikhabaar"
TERMINAL = {"succeeded", "failed", "reconciled"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_command_args(path: str | Path) -> dict[str, str]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("invalid_command")
    action = str(payload.get("action") or "").strip()
    item_id = str(payload.get("item_id") or "").strip()
    command_id = str(payload.get("command_id") or Path(path).stem).strip()
    if action not in {"publish", "reject", "refresh"}:
        raise ValueError("invalid_action")
    if action != "refresh" and not item_id:
        raise ValueError("missing_item_id")
    if not command_id:
        raise ValueError("missing_command_id")
    return {
        "command_id": command_id,
        "action": action,
        "item_id": item_id,
        "title": str(payload.get("title") or ""),
        "body": str(payload.get("body") or ""),
        "created_at": str(payload.get("created_at") or ""),
    }


def _result_path(result_dir: str | Path, command_id: str) -> Path:
    return Path(result_dir) / f"{command_id}.json"


def _write_result(result_dir: str | Path, payload: dict) -> dict:
    path = _result_path(result_dir, payload["command_id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
    return payload


def _terminal_result(result_dir: str | Path, command_id: str) -> dict | None:
    path = _result_path(result_dir, command_id)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if payload.get("status") in TERMINAL else None


def _result(args: dict[str, str], status: str, message: str) -> dict:
    return {
        "command_id": args["command_id"],
        "item_id": args["item_id"],
        "action": args["action"],
        "status": status,
        "message": message,
        "updated_at": _now(),
    }


def _source_already_published_in_channel(source_url: str, session=requests) -> bool:
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
    store.move_to_history(
        item.id,
        status="published_manual",
        final_persian_title=(title or "").strip() or str(getattr(item, "persian_title", "") or "").strip(),
        final_persian_body=(body or "").strip() or str(getattr(item, "persian_body", "") or "").strip(),
    )


def _consume(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def _run_refresh_cycle() -> int:
    # Import lazily so ordinary publish/reject commands stay fast and isolated.
    from . import runtime_v13

    return int(runtime_v13.run() or 0)


def process_command_file(
    path: str | Path,
    *,
    store: LocalEditorialStore | None = None,
    token: str = "",
    chat_id: str = "@bikhabaar",
    state_path: str | Path = "state.json",
    result_dir: str | Path = "panel_results",
    sender=send_telegram,
    channel_checker: Callable[[str], bool] | None = None,
    refresh_runner: Callable[[], int] | None = None,
) -> dict:
    command_path = Path(path)

    if not command_path.exists():
        existing = _terminal_result(result_dir, command_path.stem)
        if existing:
            return existing
        raise FileNotFoundError(command_path)

    args = load_command_args(command_path)
    existing = _terminal_result(result_dir, args["command_id"])
    if existing:
        _consume(command_path)
        return existing

    store = store or LocalEditorialStore("data/editorial_queue.json", "data/editorial_history.json")
    _write_result(result_dir, _result(args, "processing", "در حال پردازش"))

    try:
        if args["action"] == "refresh":
            runner = refresh_runner or _run_refresh_cycle
            rc = int(runner() or 0)
            if rc != 0:
                raise RuntimeError(f"refresh_failed_rc_{rc}")
            terminal = _write_result(result_dir, _result(args, "succeeded", "اسکن تازه ایجنت انجام شد"))
            _consume(command_path)
            return terminal

        if args["action"] == "reject":
            if store.get_pending(args["item_id"]) is None:
                terminal = _write_result(result_dir, _result(args, "reconciled", "خبر قبلاً از صف خارج شده بود"))
            else:
                reject_review_item(store, args["item_id"])
                terminal = _write_result(result_dir, _result(args, "succeeded", "خبر رد شد"))
            _consume(command_path)
            return terminal

        item = store.get_pending(args["item_id"])
        if item is None:
            terminal = _write_result(result_dir, _result(args, "reconciled", "خبر قبلاً پردازش شده بود"))
            _consume(command_path)
            return terminal

        checker = channel_checker or _source_already_published_in_channel
        if checker(item.source_url):
            _record_already_published(store, item, args["title"], args["body"])
            terminal = _write_result(result_dir, _result(args, "reconciled", "خبر قبلاً در کانال منتشر شده بود"))
            _consume(command_path)
            return terminal

        if not token:
            raise RuntimeError("missing_telegram_token")

        publish_review_item(
            store,
            args["item_id"],
            args["title"],
            args["body"],
            token,
            chat_id,
            state_path=state_path,
            sender=sender,
        )
        terminal = _write_result(result_dir, _result(args, "succeeded", "در تلگرام منتشر شد"))
        _consume(command_path)
        return terminal
    except Exception as exc:
        terminal = _write_result(result_dir, _result(args, "failed", str(exc)))
        _consume(command_path)
        return terminal


def _apply_paths(path: str | Path) -> tuple[Path, Path]:
    """Use repo-level runtime paths for real panel commands, isolated paths for tests/tools."""
    command_path = Path(path)
    if command_path.parent.name == "panel_commands":
        return Path("state.json"), Path("panel_results")
    return command_path.parent / "state.json", command_path.parent / "panel_results"


def apply_command(path: str | Path) -> dict:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "@bikhabaar").strip()
    state_path, result_dir = _apply_paths(path)
    result = process_command_file(
        path,
        token=token,
        chat_id=chat_id,
        state_path=state_path,
        result_dir=result_dir,
    )
    if result.get("status") == "failed":
        raise RuntimeError(str(result.get("message") or "panel_command_failed"))
    return result


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: python -m src.panel_command_file <command.json>")
    result = apply_command(sys.argv[1])
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
