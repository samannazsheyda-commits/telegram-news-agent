from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path


_CONTEXT_ROLE = "__context__"
_ALLOWED_CONTEXT = {"last_story_id", "last_source_id", "last_action_id", "pending_action_id", "last_builder_pr"}


class LunaConversationStore:
    def __init__(self, path: str | Path, *, max_messages: int = 12, ttl_hours: int = 24) -> None:
        self.path = Path(path)
        self.max_messages = max(2, min(40, int(max_messages)))
        self.ttl = timedelta(hours=max(1, min(168, int(ttl_hours))))

    def _read(self) -> dict:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return {}
        return value if isinstance(value, dict) else {}

    def _write(self, value: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=f".{self.path.name}.", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(value, handle, ensure_ascii=False, separators=(",", ":"))
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, self.path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    @staticmethod
    def _parse_time(value: str) -> datetime | None:
        try:
            parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def _is_fresh(self, row: dict, now: datetime) -> bool:
        stamp = self._parse_time(str(row.get("at") or ""))
        return stamp is None or now - stamp <= self.ttl

    def _bounded_rows(self, rows: list[dict]) -> list[dict]:
        messages = [
            dict(row)
            for row in rows
            if str(row.get("role") or "") in {"user", "assistant"}
        ][-self.max_messages :]
        context_rows = [
            dict(row)
            for row in rows
            if str(row.get("role") or "") == _CONTEXT_ROLE and isinstance(row.get("context"), dict)
        ]
        if context_rows:
            messages.append(context_rows[-1])
        return messages

    def _prune(self, data: dict) -> dict:
        now = datetime.now(timezone.utc)
        result = {}
        for key, raw in data.items():
            if not isinstance(raw, list):
                continue
            rows = [dict(row) for row in raw if isinstance(row, dict) and self._is_fresh(row, now)]
            bounded = self._bounded_rows(rows)
            if bounded:
                result[str(key)] = bounded
        return result

    def recent(self, conversation_id: str) -> list[dict]:
        key = str(conversation_id or "").strip()
        if not key:
            return []
        data = self._prune(self._read())
        return [
            dict(row)
            for row in data.get(key, [])
            if str(row.get("role") or "") in {"user", "assistant"}
        ][-self.max_messages :]

    def append(self, conversation_id: str, role: str, content: str) -> None:
        key = str(conversation_id or "").strip()
        text = str(content or "").strip()
        resolved_role = str(role or "").strip().lower()
        if not key or not text or resolved_role not in {"user", "assistant"}:
            return
        data = self._prune(self._read())
        rows = list(data.get(key, []))
        rows.append({"role": resolved_role, "content": text[:12000], "at": datetime.now(timezone.utc).isoformat()})
        data[key] = self._bounded_rows(rows)
        self._write(data)

    def get_context(self, conversation_id: str) -> dict:
        key = str(conversation_id or "").strip()
        if not key:
            return {}
        data = self._prune(self._read())
        rows = list(data.get(key, []))
        for row in reversed(rows):
            if str(row.get("role") or "") != _CONTEXT_ROLE:
                continue
            value = row.get("context")
            if not isinstance(value, dict):
                continue
            return {
                key: value[key]
                for key in _ALLOWED_CONTEXT
                if key in value and value[key] not in (None, "")
            }
        return {}

    def update_context(self, conversation_id: str, **values) -> dict:
        key = str(conversation_id or "").strip()
        if not key:
            return {}
        clean = {name: value for name, value in values.items() if name in _ALLOWED_CONTEXT}
        data = self._prune(self._read())
        rows = list(data.get(key, []))
        current = {}
        for row in reversed(rows):
            if str(row.get("role") or "") == _CONTEXT_ROLE and isinstance(row.get("context"), dict):
                current = {
                    name: value
                    for name, value in dict(row["context"]).items()
                    if name in _ALLOWED_CONTEXT and value not in (None, "")
                }
                break
        for name, value in clean.items():
            if value in (None, ""):
                current.pop(name, None)
            else:
                current[name] = value
        rows = [row for row in rows if str(row.get("role") or "") != _CONTEXT_ROLE]
        rows.append(
            {
                "role": _CONTEXT_ROLE,
                "context": current,
                "at": datetime.now(timezone.utc).isoformat(),
            }
        )
        data[key] = self._bounded_rows(rows)
        self._write(data)
        return dict(current)


class LunaSqliteConversationStore:
    """Conversation messages and structured context in the V5 `luna_conversations` table.

    Same interface as the legacy file store. Context lives in one row per
    conversation (role `__context__`), so it never counts against the message window.
    """

    _KEEP_ROWS = 200

    def __init__(self, store, *, max_messages: int = 12, ttl_hours: int = 24) -> None:
        self.store = store
        self.max_messages = max(2, min(40, int(max_messages)))
        self.ttl = timedelta(hours=max(1, min(168, int(ttl_hours))))

    def _cutoff(self) -> str:
        return (datetime.now(timezone.utc) - self.ttl).isoformat()

    def recent(self, conversation_id: str) -> list[dict]:
        key = str(conversation_id or "").strip()
        if not key:
            return []
        rows = self.store.conn.execute(
            """
            SELECT role, content, created_at FROM (
                SELECT role, content, created_at, id FROM luna_conversations
                WHERE conversation_id=? AND role IN ('user','assistant') AND created_at>=?
                ORDER BY created_at DESC, id DESC LIMIT ?
            ) ORDER BY created_at, id
            """,
            (key, self._cutoff(), self.max_messages),
        ).fetchall()
        return [{"role": row[0], "content": row[1], "at": row[2]} for row in rows]

    def append(self, conversation_id: str, role: str, content: str) -> None:
        key = str(conversation_id or "").strip()
        text = str(content or "").strip()
        resolved_role = str(role or "").strip().lower()
        if not key or not text or resolved_role not in {"user", "assistant"}:
            return
        self.store.append_luna_message(key, role=resolved_role, content=text[:12000])
        self.store.conn.execute(
            """
            DELETE FROM luna_conversations
            WHERE conversation_id=? AND role IN ('user','assistant') AND id NOT IN (
                SELECT id FROM luna_conversations WHERE conversation_id=? AND role IN ('user','assistant')
                ORDER BY created_at DESC, id DESC LIMIT ?
            )
            """,
            (key, key, self._KEEP_ROWS),
        )

    def _context_row(self, key: str) -> dict:
        row = self.store.conn.execute(
            "SELECT context_json, created_at FROM luna_conversations WHERE id=?",
            (f"ctx:{key}",),
        ).fetchone()
        if row is None or str(row[1] or "") < self._cutoff():
            return {}
        try:
            value = json.loads(row[0] or "{}")
        except (TypeError, ValueError):
            return {}
        return value if isinstance(value, dict) else {}

    def get_context(self, conversation_id: str) -> dict:
        key = str(conversation_id or "").strip()
        if not key:
            return {}
        value = self._context_row(key)
        return {name: value[name] for name in _ALLOWED_CONTEXT if value.get(name) not in (None, "")}

    def update_context(self, conversation_id: str, **values) -> dict:
        key = str(conversation_id or "").strip()
        if not key:
            return {}
        current = self.get_context(key)
        for name, value in values.items():
            if name not in _ALLOWED_CONTEXT:
                continue
            if value in (None, ""):
                current.pop(name, None)
            else:
                current[name] = value
        self.store.conn.execute(
            """
            INSERT INTO luna_conversations(id,conversation_id,role,content,context_json,created_at)
            VALUES(?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET context_json=excluded.context_json, created_at=excluded.created_at
            """,
            (
                f"ctx:{key}",
                key,
                _CONTEXT_ROLE,
                "",
                json.dumps(current, ensure_ascii=False, sort_keys=True),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        return dict(current)


def default_conversation_store() -> LunaConversationStore:
    path = str(os.environ.get("LUNA_CONVERSATION_PATH") or "/var/lib/bikhabar/luna_conversations.json")
    return LunaConversationStore(path)
