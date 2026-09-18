from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import requests

from .ai_newsroom import AIServiceError
from .editorial_store import LocalEditorialStore
from .event_ledger import EventLedger
from .manual_publish import publish_review_item, reject_review_item
from .newsroom_models import RawNewsItem
from .newsroom_v2 import CycleSummary, run_cycle
from .newsroom_v3.manual_publish import publish_manual_story
from .one_x_ai_newsroom import OneXAINewsAI
from .panel_live_feed import LiveFeedStore
from .runtime_v12 import _normalise_url, extract_public_telegram_source_links
from .services import send_telegram
from .sources import USER_AGENT
from .strict_translation import _natural_persian_copy
from .truth_social import fetch_trump_truth_items

OWN_CHANNEL = "bikhabaar"
TERMINAL = {"succeeded", "failed", "reconciled"}
_ALLOWED_ACTIONS = {"publish", "reject", "refresh", "luna_preview", "publish_final"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: str | Path, default: Any) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default


def _atomic_write_json(path: str | Path, value: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(target)


def load_command_args(path: str | Path) -> dict[str, str]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("invalid_command")
    action = str(payload.get("action") or "").strip()
    item_id = str(payload.get("item_id") or "").strip()
    command_id = str(payload.get("command_id") or Path(path).stem).strip()
    if action not in _ALLOWED_ACTIONS:
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
        "source": str(payload.get("source") or ""),
        "source_url": str(payload.get("source_url") or ""),
        "original_title": str(payload.get("original_title") or ""),
        "original_body": str(payload.get("original_body") or ""),
        "news_key": str(payload.get("news_key") or ""),
        "published_at": str(payload.get("published_at") or ""),
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


def _row_id(row: Any) -> str:
    if not isinstance(row, dict):
        return ""
    return str(row.get("id") or row.get("item_id") or row.get("news_key") or "").strip()


def _find_row(path: str | Path, item_id: str) -> dict:
    rows = _read_json(path, [])
    if not isinstance(rows, list):
        return {}
    match = next((row for row in rows if isinstance(row, dict) and _row_id(row) == item_id), None)
    return dict(match) if isinstance(match, dict) else {}


def _upsert_row(path: str | Path, row: dict) -> None:
    rows = _read_json(path, [])
    rows = [dict(item) for item in rows if isinstance(item, dict)] if isinstance(rows, list) else []
    item_id = _row_id(row)
    updated = [dict(row)]
    updated.extend(item for item in rows if _row_id(item) != item_id)
    _atomic_write_json(path, updated)


def _remove_row(path: str | Path, item_id: str) -> None:
    rows = _read_json(path, [])
    if not isinstance(rows, list):
        return
    _atomic_write_json(path, [row for row in rows if not isinstance(row, dict) or _row_id(row) != item_id])


def _has_persian(value: str) -> bool:
    return any("\u0600" <= char <= "\u06ff" for char in str(value or ""))


def _luna_finalize_piece(ai: OneXAINewsAI, source_text: str) -> str:
    source = str(source_text or "").strip()
    if not source:
        return ""
    if _has_persian(source):
        draft_text = source
    else:
        draft = ai.translate_to_fa(source)
        draft_text = str(getattr(draft, "text", "") or "").strip()
        if not draft_text or getattr(draft, "faithful", False) is not True:
            raise AIServiceError("luna_manual_translation_rejected")
    edit = ai.edit_persian(source, draft_text)
    if getattr(edit, "faithful", False) is not True or getattr(edit, "natural", False) is not True:
        raise AIServiceError("luna_manual_edit_rejected")
    edited_text = str(getattr(edit, "text", "") or "").strip()
    if not edited_text:
        raise AIServiceError("luna_manual_edit_empty")
    guarded = _natural_persian_copy(source, edited_text)
    if not guarded or not _has_persian(guarded):
        raise AIServiceError("luna_manual_guard_rejected")
    return guarded


def _finalize_manual_copy_with_luna(original_title: str, original_body: str) -> tuple[str, str]:
    source_title = str(original_title or "").strip()
    source_body = str(original_body or "").strip()
    if not source_title:
        raise AIServiceError("missing_original_title")
    ai = OneXAINewsAI()
    if not ai.available:
        raise AIServiceError("luna_manual_unavailable")
    final_title = _luna_finalize_piece(ai, source_title)
    final_body = _luna_finalize_piece(ai, source_body) if source_body else ""
    return final_title, final_body


def _manual_source(args: dict[str, str]) -> dict:
    item_id = args["item_id"]
    queued = _find_row("data/editorial_queue.json", item_id)
    live = _find_row("data/panel_live_feed.json", item_id)
    current = {**live, **queued}
    source = str(args.get("source") or current.get("source") or "").strip()
    source_url = str(args.get("source_url") or current.get("source_url") or "").strip()
    original_title = str(
        args.get("original_title")
        or current.get("original_title")
        or current.get("title")
        or ""
    ).strip()
    original_body = str(
        args.get("original_body")
        or current.get("original_summary")
        or current.get("summary")
        or current.get("body")
        or ""
    ).strip()
    return {
        **current,
        "id": item_id,
        "item_id": item_id,
        "news_key": str(args.get("news_key") or current.get("news_key") or item_id).strip(),
        "source": source,
        "source_url": source_url,
        "original_title": original_title,
        "original_summary": original_body,
        "published_at_source": str(args.get("published_at") or current.get("published_at_source") or "").strip(),
    }


def _apply_luna_preview(args: dict[str, str]) -> dict:
    current = _manual_source(args)
    if not current.get("source") or not current.get("source_url"):
        raise ValueError("missing_source")
    if not current.get("original_title"):
        raise ValueError("missing_original_title")
    title, body = _finalize_manual_copy_with_luna(
        str(current.get("original_title") or ""),
        str(current.get("original_summary") or ""),
    )
    now = _now()
    queued = dict(current)
    queued.update(
        status="pending",
        luna_status="ready",
        luna_finalized_at=now,
        persian_title=title,
        persian_body=body,
        final_persian_title=title,
        final_persian_body=body,
        updated_at=now,
    )
    _upsert_row("data/editorial_queue.json", queued)
    result = _result(args, "succeeded", "نسخه نهایی Luna آماده شد؛ قبل از انتشار آن را بررسی کن")
    result.update(
        telegram_message_id=None,
        review_url=f"/review/{args['item_id']}",
    )
    return result


def _finalize_published_item(item: dict, result: dict, title: str, body: str) -> None:
    now = _now()
    final = dict(item)
    final.update(
        status="published_manual",
        persian_title=title,
        persian_body=body,
        final_persian_title=title,
        final_persian_body=body,
        decision_at=now,
        updated_at=now,
        telegram_message_id=result.get("telegram_message_id"),
        v3_story_id=str(result.get("story_id") or ""),
    )
    _upsert_row("data/editorial_history.json", final)
    _remove_row("data/editorial_queue.json", _row_id(item))
    _remove_row("data/panel_live_feed.json", _row_id(item))


def _apply_publish_final(args: dict[str, str]) -> dict:
    current = _manual_source(args)
    title = str(args.get("title") or current.get("final_persian_title") or current.get("persian_title") or "").strip()
    body = str(args.get("body") or current.get("final_persian_body") or current.get("persian_body") or "").strip()
    if not current.get("source") or not current.get("source_url"):
        raise ValueError("missing_source")
    if not title or not _has_persian(title):
        raise ValueError("missing_final_persian_title")
    publish_result = publish_manual_story(
        data_dir=Path(os.environ.get("DATA_DIR", "data")),
        item_id=args["item_id"],
        news_key=str(current.get("news_key") or args["item_id"]),
        source=str(current.get("source") or ""),
        source_url=str(current.get("source_url") or ""),
        title=title,
        body=body,
        published_at=str(current.get("published_at_source") or ""),
    )
    status = str(publish_result.get("status") or "failed")
    if status in {"succeeded", "reconciled"}:
        _finalize_published_item(current, publish_result, title, body)
    messages = {
        "succeeded": "نسخه تأییدشده در تلگرام منتشر شد",
        "reconciled": "انتشار قبلی تأیید و همگام شد",
        "ambiguous": "وضعیت ارسال تلگرام نامشخص است؛ انتشار دوباره خودکار مسدود شد",
        "processing": "انتشار در حال پردازش است",
        "failed": "انتشار ناموفق بود",
    }
    result = _result(args, status, messages.get(status, "وضعیت انتشار ثبت شد"))
    result.update(
        story_id=str(publish_result.get("story_id") or ""),
        telegram_message_id=publish_result.get("telegram_message_id") if isinstance(publish_result.get("telegram_message_id"), int) else None,
        error=str(publish_result.get("error") or ""),
    )
    return result


def scan_items_into_v2_panel(
    items: list[RawNewsItem],
    *,
    store: LocalEditorialStore,
    ledger: EventLedger,
    live_feed: LiveFeedStore,
    settings: dict,
    now: datetime,
) -> CycleSummary:
    """Run a shadow V2 cycle for the panel.

    Shadow mode never publishes. With auto-publish enabled, normal new events
    appear only in the live feed. If publication is paused or a decision needs
    editorial review, the item is also placed in the manual queue.
    """
    return run_cycle(
        fetcher=lambda: items,
        ledger=ledger,
        live_feed=live_feed,
        editorial_store=store,
        publisher=lambda item: (_ for _ in ()).throw(RuntimeError("panel_refresh_must_not_publish")),
        settings=settings,
        now=now,
        shadow=True,
    )


def _legacy_news_to_raw(item, now: datetime) -> RawNewsItem | None:
    key = str(getattr(item, "key", "") or "").strip()
    title = str(getattr(item, "title", "") or "").strip()
    if not key or not title:
        return None
    media: list[str] = []
    for attr in ("photo_url", "image_url", "media_url"):
        value = str(getattr(item, attr, "") or "").strip()
        if value and value not in media:
            media.append(value)
    return RawNewsItem(
        source=str(getattr(item, "source", "") or "").strip(),
        source_url=str(getattr(item, "link", "") or "").strip(),
        source_item_id=key,
        published_at=str(getattr(item, "published", "") or "").strip(),
        fetched_at=now.isoformat(),
        title=title,
        summary=str(getattr(item, "summary", "") or "").strip(),
        media=media,
        source_priority="normal",
    )


def _scan_fresh_items_into_queue(store: LocalEditorialStore) -> int:
    """Compatibility entrypoint: refresh the V2 live feed, not the old catch-all queue."""
    from . import runtime_v13

    runtime_v13.install_production_policies()
    agent = runtime_v13.base.agent
    now = datetime.now(timezone.utc)
    raw_items: list[RawNewsItem] = []
    for item in list(agent.fetch_news_items() or []):
        converted = _legacy_news_to_raw(item, now)
        if converted is not None:
            raw_items.append(converted)
    try:
        raw_items.extend(fetch_trump_truth_items())
    except Exception as exc:
        print(f"V2_PANEL_SOURCE_FAILED source=truth_social error={exc}", file=sys.stderr)

    settings = runtime_v13.load_newsroom_settings()
    summary = scan_items_into_v2_panel(
        raw_items,
        store=store,
        ledger=EventLedger("data/event_ledger.json"),
        live_feed=LiveFeedStore("data/panel_live_feed.json"),
        settings=settings,
        now=now,
    )
    print(
        "V2_PANEL_REFRESH "
        f"fetched={summary.items_fetched} live={summary.panel_feed_count} "
        f"waiting={summary.review_items} duplicates={summary.exact_duplicates + summary.same_claim_duplicates}"
    )
    return summary.panel_feed_count


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
            if refresh_runner is not None:
                rc = int(refresh_runner() or 0)
                if rc != 0:
                    raise RuntimeError(f"refresh_failed_rc_{rc}")
                message = "اسکن تازه ایجنت انجام شد"
            else:
                visible = _scan_fresh_items_into_queue(store)
                message = f"اسکن تازه انجام شد؛ {visible} خبر در ورودی زنده پنل موجود است"
            terminal = _write_result(result_dir, _result(args, "succeeded", message))
            _consume(command_path)
            return terminal

        if args["action"] == "luna_preview":
            terminal = _write_result(result_dir, _apply_luna_preview(args))
            _consume(command_path)
            return terminal

        if args["action"] == "publish_final":
            terminal = _write_result(result_dir, _apply_publish_final(args))
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
