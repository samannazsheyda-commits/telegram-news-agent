from __future__ import annotations

import hashlib
import os
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import requests

from src.custom_sources import XSource, normalize_telegram_channel, validate_website_source
from src.managed_sources import normalize_truth_handle, system_source_definitions
from src.operator_blocks import add_operator_block
from src.newsroom_v3.store import NewsroomV3Store


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _text(value) -> str:
    return str(value or "").strip()


def _custom_id(kind: str, identity: str) -> str:
    return hashlib.sha1(f"{kind}:{identity.lower()}".encode("utf-8")).hexdigest()


def tool_schemas() -> list[dict]:
    """Schemas exposed to Luna come from the single capability registry."""
    from .luna_capabilities import build_capability_registry

    return build_capability_registry().tool_schemas()


class LunaToolbox:
    """Validated newsroom operations used by the Luna control runtime.

    Legacy handlers stay available for backwards compatibility, but the
    operator API proposal-gates mutations before calling them confirmed.
    """

    def __init__(self, data, *, block_path: str | Path | None = None) -> None:
        self.data = data
        data_dir = Path(os.environ.get("DATA_DIR", "data"))
        self.block_path = Path(block_path) if block_path is not None else data_dir / "operator_blocks.json"
        self.v3_store_path = data_dir / "newsroom_v3.sqlite3"

    def _read(self, path: str, default):
        value, _ = self.data.read_json(path, default)
        return value

    def _write(self, path: str, default, transform, message: str):
        for attempt in range(3):
            value, sha = self.data.read_json(path, default)
            updated = transform(value)
            try:
                self.data.write_json(path, updated, sha, message)
                return updated
            except requests.HTTPError as exc:
                status = getattr(getattr(exc, "response", None), "status_code", None)
                if attempt < 2 and status in {409, 422}:
                    continue
                raise
        raise RuntimeError("luna_tool_write_conflict")

    def _list(self, path: str) -> list[dict]:
        value = self._read(path, [])
        return [dict(row) for row in value if isinstance(row, dict)] if isinstance(value, list) else []

    def _story_rows(self) -> list[dict]:
        rows: list[dict] = []
        for location, path in (
            ("live", "data/panel_live_feed.json"),
            ("review", "data/editorial_queue.json"),
            ("history", "data/editorial_history.json"),
        ):
            for row in self._list(path):
                copy = dict(row)
                copy["_location"] = location
                rows.append(copy)
        return rows

    @staticmethod
    def _story_id(row: dict) -> str:
        return _text(row.get("id") or row.get("item_id") or row.get("story_id"))

    @staticmethod
    def _story_public(row: dict) -> dict:
        return {
            "id": LunaToolbox._story_id(row),
            "source": _text(row.get("source")),
            "source_url": _text(row.get("source_url") or row.get("link")),
            "title": _text(row.get("final_persian_title") or row.get("persian_title") or row.get("original_title") or row.get("title")),
            "original_title": _text(row.get("original_title") or row.get("title")),
            "summary": _text(row.get("final_persian_body") or row.get("persian_body") or row.get("original_summary") or row.get("summary") or row.get("body"))[:900],
            "status": _text(row.get("panel_status") or row.get("status") or row.get("_location")),
            "location": _text(row.get("_location")),
        }

    def _find_story(self, story_id: str) -> dict | None:
        wanted = _text(story_id)
        if not wanted:
            return None
        for row in self._story_rows():
            if self._story_id(row) == wanted:
                return row
        return None

    def _sources(self) -> list[dict]:
        custom = self._list("data/custom_sources.json")
        overrides = self._read("data/source_overrides.json", {})
        overrides = overrides if isinstance(overrides, dict) else {}
        rows: list[dict] = []
        for base in system_source_definitions():
            row = dict(base)
            source_id = _text(row.get("id"))
            state = overrides.get(source_id, {})
            state = state if isinstance(state, dict) else {}
            if state.get("hidden"):
                continue
            row["active"] = bool(state.get("active", True))
            row["system"] = True
            row["identity"] = _text(row.get("handle") or row.get("query"))
            row["name"] = _text(state.get("display_name") or row.get("name") or source_id)
            row["review_only"] = bool(state.get("review_only", row.get("review_only", False)))
            rows.append(row)
        for base in custom:
            if base.get("deleted"):
                continue
            row = dict(base)
            row["system"] = False
            row.setdefault("active", True)
            row.setdefault("review_only", False)
            if row.get("kind") == "telegram":
                row["identity"] = "@" + _text(row.get("channel")).lstrip("@")
            elif row.get("kind") in {"x", "truth"}:
                row["identity"] = _text(row.get("handle"))
            else:
                row["identity"] = _text(row.get("feed_url") or row.get("website_url"))
            rows.append(row)
        return rows

    @staticmethod
    def _source_public(row: dict) -> dict:
        return {
            "id": _text(row.get("id")),
            "kind": _text(row.get("kind")),
            "name": _text(row.get("name") or row.get("id")),
            "identity": _text(row.get("identity") or row.get("handle") or row.get("channel") or row.get("website_url")),
            "active": bool(row.get("active", True)),
            "system": bool(row.get("system", False)),
            "review_only": bool(row.get("review_only", False)),
        }

    def _resolve_source(self, args: dict) -> tuple[dict | None, dict | None]:
        source_id = _text(args.get("source_id"))
        query = _text(args.get("query")).casefold().lstrip("@")
        rows = self._sources()
        if source_id:
            matches = [row for row in rows if _text(row.get("id")) == source_id]
        elif query:
            matches = []
            for row in rows:
                values = {
                    _text(row.get("name")).casefold(),
                    _text(row.get("id")).casefold(),
                    _text(row.get("identity")).casefold().lstrip("@"),
                    _text(row.get("handle")).casefold().lstrip("@"),
                    _text(row.get("channel")).casefold().lstrip("@"),
                }
                if query in values:
                    matches.append(row)
        else:
            return None, {"ok": False, "error": "source_target_required", "message": "شناسه یا نام منبع لازم است."}
        if not matches:
            return None, {"ok": False, "error": "source_not_found", "message": "منبع پیدا نشد."}
        if len(matches) > 1:
            return None, {
                "ok": False,
                "error": "ambiguous_source",
                "message": "چند منبع با این نام پیدا شد؛ منبع دقیق را مشخص کن.",
                "matches": [self._source_public(row) for row in matches[:8]],
            }
        return matches[0], None

    @staticmethod
    def _pending(action: str, payload: dict, summary: str) -> dict:
        return {
            "ok": True,
            "confirmation_required": True,
            "pending_action": {"action": action, "payload": payload, "summary_fa": summary},
        }

    def execute(self, name: str, args: dict | None = None, *, confirmed: bool = False) -> dict:
        args = dict(args or {})
        handler = getattr(self, f"_tool_{name}", None)
        if handler is None:
            return {"ok": False, "error": "unknown_tool", "message": f"ابزار {name} تعریف نشده است."}
        try:
            return handler(args, confirmed=confirmed)
        except (ValueError, KeyError) as exc:
            return {"ok": False, "error": "invalid_tool_arguments", "message": str(exc)[:300]}
        except Exception as exc:
            return {"ok": False, "error": "tool_failed", "message": f"اجرای ابزار ناموفق بود: {type(exc).__name__}"}

    def _tool_search_stories(self, args: dict, *, confirmed: bool) -> dict:
        query = _text(args.get("query")).casefold()
        source = _text(args.get("source")).casefold()
        status = _text(args.get("status")).casefold()
        limit = max(1, min(20, int(args.get("limit") or 8)))
        matches = []
        for row in self._story_rows():
            public = self._story_public(row)
            haystack = " ".join((public["title"], public["original_title"], public["summary"], public["source"])).casefold()
            if query and query not in haystack:
                continue
            if source and source not in public["source"].casefold():
                continue
            if status and status not in public["status"].casefold():
                continue
            matches.append(public)
            if len(matches) >= limit:
                break
        return {"ok": True, "stories": matches, "count": len(matches)}

    def _tool_get_story(self, args: dict, *, confirmed: bool) -> dict:
        row = self._find_story(_text(args.get("story_id")))
        if row is None:
            return {"ok": False, "error": "story_not_found", "message": "خبر پیدا نشد."}
        return {"ok": True, "story": self._story_public(row)}

    def _tool_translate_story(self, args: dict, *, confirmed: bool) -> dict:
        row = self._find_story(_text(args.get("story_id")))
        if row is None:
            return {"ok": False, "error": "story_not_found", "message": "خبر پیدا نشد."}
        return {
            "ok": False,
            "error": "translation_pipeline_required",
            "message": "مسیر ترجمه Luna برای این خبر باید اجرا شود.",
            "story": self._story_public(row),
        }

    def _tool_reject_and_block_story(self, args: dict, *, confirmed: bool) -> dict:
        row = self._find_story(_text(args.get("story_id")))
        if row is None:
            return {"ok": False, "error": "story_not_found", "message": "خبر پیدا نشد."}
        public = self._story_public(row)
        reason = _text(args.get("reason")) or "requested_by_admin"
        if not confirmed:
            return self._pending(
                "reject_and_block_story",
                {"story_id": public["id"], "reason": reason},
                f"خبر «{public['title'] or public['original_title']}» رد و برای انتشارهای بعدی مسدود شود؟",
            )
        add_operator_block(
            self.block_path,
            story_id=public["id"],
            source_url=public["source_url"],
            fingerprint=_text(row.get("fingerprint")),
            title=public["original_title"] or public["title"],
            reason=reason,
        )
        if self.v3_store_path.exists():
            store = NewsroomV3Store(self.v3_store_path)
            try:
                if store.get_story(public["id"]) is not None:
                    store.set_decision(public["id"], "rejected", reason=f"operator_block:{reason}")
            finally:
                store.close()
        record = dict(row)
        record.update(status="rejected_manual", decision_reason=f"operator_block:{reason}", decision_at=_now(), updated_at=_now())
        self._write(
            "data/editorial_history.json",
            [],
            lambda rows: [record] + [x for x in list(rows or []) if _text(x.get("id") or x.get("item_id")) != public["id"]],
            "panel v4.1: operator block story",
        )
        for path in ("data/editorial_queue.json", "data/panel_live_feed.json"):
            self._write(
                path,
                [],
                lambda rows, story_id=public["id"]: [x for x in list(rows or []) if _text(x.get("id") or x.get("item_id")) != story_id],
                "panel v4.1: remove blocked story",
            )
        return {"ok": True, "message": "خبر رد و به‌صورت دائمی از چرخه انتشار مسدود شد.", "story": public}

    def _tool_move_story_to_review(self, args: dict, *, confirmed: bool) -> dict:
        row = self._find_story(_text(args.get("story_id")))
        if row is None:
            return {"ok": False, "error": "story_not_found", "message": "خبر پیدا نشد."}
        if not confirmed:
            public = self._story_public(row)
            return self._pending("move_story_to_review", {"story_id": public["id"]}, f"خبر «{public['title']}» به صف بررسی منتقل شود؟")
        record = dict(row)
        record["id"] = self._story_id(row)
        record["status"] = "pending"
        record["updated_at"] = _now()
        self._write(
            "data/editorial_queue.json",
            [],
            lambda rows: [record] + [x for x in list(rows or []) if _text(x.get("id") or x.get("item_id")) != record["id"]],
            "panel v4.1: Luna move story to review",
        )
        return {"ok": True, "message": "خبر به صف بررسی منتقل شد.", "story": self._story_public(record)}

    def _tool_list_recent_published(self, args: dict, *, confirmed: bool) -> dict:
        limit = max(1, min(30, int(args.get("limit") or 10)))
        source = _text(args.get("source")).casefold()
        rows = []
        for row in self._list("data/editorial_history.json"):
            if _text(row.get("status")) not in {"published_auto", "published_manual"}:
                continue
            public = self._story_public(row)
            if source and source not in public["source"].casefold():
                continue
            rows.append(public)
        return {"ok": True, "stories": rows[:limit], "count": min(limit, len(rows))}

    def _tool_diagnose_newsroom(self, args: dict, *, confirmed: bool) -> dict:
        v3 = self._read("data/newsroom_v3_production_status.json", {})
        v3 = v3 if isinstance(v3, dict) else {}
        state = self._read("state.json", {})
        state = state if isinstance(state, dict) else {}
        return {
            "ok": True,
            "daily_published": int(v3.get("daily_published") or 0),
            "daily_limit": int(v3.get("daily_limit") or 0),
            "daily_remaining": int(v3.get("daily_remaining") or 0),
            "ready": int(v3.get("ready") or 0),
            "waiting": int(v3.get("waiting") or 0),
            "sources_failed": int(v3.get("sources_failed") or state.get("last_sources_failed") or 0),
            "publish_failed": int(v3.get("publish_failed") or 0),
            "reason": _text(v3.get("reason") or state.get("newsroom_reason")),
            "telegram_state": _text(state.get("telegram_state")),
        }

    def _tool_list_sources(self, args: dict, *, confirmed: bool) -> dict:
        kind = _text(args.get("kind")).casefold()
        query = _text(args.get("query")).casefold().lstrip("@")
        active_filter = args.get("active")
        rows = []
        for row in self._sources():
            public = self._source_public(row)
            if kind and public["kind"].casefold() != kind:
                continue
            if isinstance(active_filter, bool) and public["active"] is not active_filter:
                continue
            if query:
                haystack = f"{public['name']} {public['identity']} {public['id']}".casefold().lstrip("@")
                if query not in haystack:
                    continue
            rows.append(public)
        return {"ok": True, "sources": rows[:50], "count": len(rows)}

    def _build_source(self, args: dict) -> dict:
        kind = _text(args.get("kind")).lower()
        identity = _text(args.get("identifier"))
        display_name = _text(args.get("display_name"))
        feed_url = _text(args.get("feed_url"))
        if kind == "x":
            return asdict(XSource.create(identity, display_name))
        if kind == "telegram":
            channel = normalize_telegram_channel(identity)
            return {
                "id": _custom_id("telegram", channel),
                "kind": "telegram",
                "name": display_name or channel,
                "channel": channel,
                "active": True,
                "status": "active",
                "last_checked_at": "",
                "last_error": "",
                "updated_at": _now(),
            }
        if kind == "truth":
            handle = normalize_truth_handle(identity)
            return {
                "id": _custom_id("truth", handle),
                "kind": "truth",
                "name": display_name or handle.lstrip("@"),
                "handle": handle,
                "active": True,
                "status": "active",
                "last_checked_at": "",
                "last_error": "",
                "updated_at": _now(),
            }
        if kind == "website":
            record = asdict(validate_website_source(display_name or identity, identity, feed_url))
            if not record.get("feed_url"):
                raise ValueError("برای منبع وب‌سایت، RSS/Feed را هم مشخص کن تا Luna بدون حدس منبع را اضافه کند.")
            return record
        raise ValueError("نوع منبع پشتیبانی نمی‌شود.")

    def _tool_add_source(self, args: dict, *, confirmed: bool) -> dict:
        record = self._build_source(args)
        if not confirmed:
            public = self._source_public({**record, "system": False, "identity": args.get("identifier")})
            return self._pending("add_source", args, f"منبع «{public['name']}» به رصد اضافه شود؟")
        self._write(
            "data/custom_sources.json",
            [],
            lambda rows: [record] + [x for x in list(rows or []) if _text(x.get("id")) != _text(record.get("id"))],
            "panel v4.1: Luna add source",
        )
        return {"ok": True, "message": "منبع اضافه شد و از اسکن بعدی وارد رصد می‌شود.", "source": self._source_public({**record, "system": False})}

    def _set_source_active(self, row: dict, desired: bool) -> dict:
        source_id = _text(row.get("id"))
        if row.get("system"):
            def transform(value):
                overrides = dict(value) if isinstance(value, dict) else {}
                state = dict(overrides.get(source_id) or {})
                state.update(active=desired, updated_at=_now())
                overrides[source_id] = state
                return overrides
            self._write("data/source_overrides.json", {}, transform, "panel v4.1: Luna toggle system source")
        else:
            def transform(value):
                records = list(value) if isinstance(value, list) else []
                for record in records:
                    if isinstance(record, dict) and _text(record.get("id")) == source_id:
                        record["active"] = desired
                        record["updated_at"] = _now()
                        return records
                raise ValueError("منبع پیدا نشد.")
            self._write("data/custom_sources.json", [], transform, "panel v4.1: Luna toggle custom source")
        public = self._source_public(row)
        public["active"] = desired
        return public

    def _toggle_tool(self, action: str, args: dict, *, confirmed: bool, desired: bool) -> dict:
        row, error = self._resolve_source(args)
        if error:
            return error
        public = self._source_public(row)
        if not confirmed:
            return self._pending(action, {"source_id": public["id"]}, f"منبع «{public['name']}» {'فعال' if desired else 'غیرفعال'} شود؟")
        updated = self._set_source_active(row, desired)
        return {"ok": True, "message": f"منبع «{updated['name']}» {'فعال' if desired else 'غیرفعال'} شد.", "source": updated}

    def _tool_enable_source(self, args: dict, *, confirmed: bool) -> dict:
        return self._toggle_tool("enable_source", args, confirmed=confirmed, desired=True)

    def _tool_disable_source(self, args: dict, *, confirmed: bool) -> dict:
        return self._toggle_tool("disable_source", args, confirmed=confirmed, desired=False)

    def _tool_delete_source(self, args: dict, *, confirmed: bool) -> dict:
        row, error = self._resolve_source(args)
        if error:
            return error
        public = self._source_public(row)
        if not confirmed:
            return self._pending("delete_source", {"source_id": public["id"]}, f"منبع «{public['name']}» از رصد حذف شود؟")
        source_id = public["id"]
        if row.get("system"):
            def transform(value):
                overrides = dict(value) if isinstance(value, dict) else {}
                state = dict(overrides.get(source_id) or {})
                state.update(active=False, hidden=True, updated_at=_now())
                overrides[source_id] = state
                return overrides
            self._write("data/source_overrides.json", {}, transform, "panel v4.1: Luna hide system source")
        else:
            self._write(
                "data/custom_sources.json",
                [],
                lambda rows: [x for x in list(rows or []) if _text(x.get("id")) != source_id],
                "panel v4.1: Luna delete source",
            )
        return {"ok": True, "message": f"منبع «{public['name']}» از رصد حذف شد.", "source": public}

    def _tool_inspect_panel_state(self, args: dict, *, confirmed: bool) -> dict:
        return {
            "ok": True,
            "live_count": len(self._list("data/panel_live_feed.json")),
            "review_count": len(self._list("data/editorial_queue.json")),
            "history_count": len(self._list("data/editorial_history.json")),
            "sources_count": len(self._sources()),
            "diagnosis": self._tool_diagnose_newsroom({}, confirmed=False),
        }
