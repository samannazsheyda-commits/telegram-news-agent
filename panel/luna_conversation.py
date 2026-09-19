from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path


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

    def _prune(self, data: dict) -> dict:
        now = datetime.now(timezone.utc)
        result = {}
        for key, raw in data.items():
            if not isinstance(raw, list):
                continue
            rows = [dict(row) for row in raw if isinstance(row, dict)]
            fresh = []
            for row in rows:
                stamp = self._parse_time(str(row.get("at") or ""))
                if stamp is None or now - stamp <= self.ttl:
                    fresh.append(row)
            if fresh:
                result[str(key)] = fresh[-self.max_messages :]
        return result

    def recent(self, conversation_id: str) -> list[dict]:
        key = str(conversation_id or "").strip()
        if not key:
            return []
        data = self._prune(self._read())
        return [dict(row) for row in data.get(key, [])][-self.max_messages :]

    def append(self, conversation_id: str, role: str, content: str) -> None:
        key = str(conversation_id or "").strip()
        text = str(content or "").strip()
        resolved_role = str(role or "").strip().lower()
        if not key or not text or resolved_role not in {"user", "assistant"}:
            return
        data = self._prune(self._read())
        rows = list(data.get(key, []))
        rows.append({"role": resolved_role, "content": text[:12000], "at": datetime.now(timezone.utc).isoformat()})
        data[key] = rows[-self.max_messages :]
        self._write(data)


def default_conversation_store() -> LunaConversationStore:
    path = str(os.environ.get("LUNA_CONVERSATION_PATH") or "/var/lib/bikhabar/luna_conversations.json")
    return LunaConversationStore(path)
