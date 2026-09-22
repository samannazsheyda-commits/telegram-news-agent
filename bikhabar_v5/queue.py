from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any


_KIND_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class RedisJobQueue:
    """Redis Streams-backed queue isolated under the bikhabar:v5 namespace."""

    def __init__(self, redis_url: str, *, client=None, namespace: str = "bikhabar:v5:jobs") -> None:
        self.redis_url = str(redis_url or "").strip()
        if not self.redis_url:
            raise ValueError("redis_url is required")
        self.namespace = str(namespace or "").strip().rstrip(":")
        if not self.namespace.startswith("bikhabar:v5:"):
            raise ValueError("Vision 5 Redis namespace must start with bikhabar:v5:")
        self._client = client

    def _redis(self):
        if self._client is None:
            try:
                import redis
            except ImportError as exc:  # pragma: no cover - deployment dependency guard
                raise RuntimeError("redis package is required for Vision 5 production") from exc
            self._client = redis.Redis.from_url(self.redis_url, decode_responses=True)
        return self._client

    def key(self, kind: str) -> str:
        normalized = str(kind or "").strip().lower()
        if not _KIND_RE.fullmatch(normalized):
            raise ValueError("invalid Vision 5 job kind")
        return f"{self.namespace}:{normalized}"

    def enqueue(self, kind: str, payload: dict[str, Any], *, job_id: str | None = None) -> str:
        resolved_job_id = job_id or uuid.uuid4().hex
        fields = {
            "job_id": resolved_job_id,
            "payload": json.dumps(dict(payload or {}), ensure_ascii=False, separators=(",", ":")),
            "created_at": _now(),
        }
        self._redis().xadd(self.key(kind), fields)
        return resolved_job_id

    def ensure_group(self, kind: str, group: str) -> None:
        try:
            self._redis().xgroup_create(self.key(kind), group, id="0", mkstream=True)
        except Exception as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    def read(self, kind: str, *, group: str, consumer: str, count: int = 1, block_ms: int = 1000) -> list[dict]:
        self.ensure_group(kind, group)
        rows = self._redis().xreadgroup(
            group,
            consumer,
            {self.key(kind): ">"},
            count=max(1, min(int(count), 100)),
            block=max(0, int(block_ms)),
        )
        result: list[dict] = []
        for _stream, messages in rows or []:
            for message_id, fields in messages:
                result.append(self._decode(message_id, fields))
        return result

    def reclaim(
        self,
        kind: str,
        *,
        group: str,
        consumer: str,
        min_idle_ms: int = 60_000,
        count: int = 10,
    ) -> list[dict]:
        self.ensure_group(kind, group)
        client = self._redis()
        stream = self.key(kind)
        idle = max(1000, int(min_idle_ms))
        limit = max(1, min(int(count), 100))
        try:
            response = client.xautoclaim(
                stream,
                group,
                consumer,
                min_idle_time=idle,
                start_id="0-0",
                count=limit,
            )
            messages = response[1] if response and len(response) > 1 else []
        except Exception as exc:
            message = str(exc).lower()
            if "unknown command" not in message or "xautoclaim" not in message:
                raise
            messages = self._reclaim_redis5(
                client,
                stream=stream,
                group=group,
                consumer=consumer,
                min_idle_ms=idle,
                count=limit,
            )
        return [self._decode(message_id, fields) for message_id, fields in messages]

    @staticmethod
    def _reclaim_redis5(client, *, stream: str, group: str, consumer: str, min_idle_ms: int, count: int):
        scan_count = max(1000, min(10_000, count * 20))
        pending = client.xpending_range(stream, group, min="-", max="+", count=scan_count)
        message_ids = [
            str(row.get("message_id") or "")
            for row in pending or []
            if int(row.get("time_since_delivered") or 0) >= min_idle_ms
        ][:count]
        message_ids = [message_id for message_id in message_ids if message_id]
        if not message_ids:
            return []
        return client.xclaim(stream, group, consumer, min_idle_ms, message_ids)

    @staticmethod
    def _decode(message_id: str, fields: dict[str, str]) -> dict:
        raw_payload = fields.get("payload") or "{}"
        return {
            "message_id": message_id,
            "job_id": fields.get("job_id") or "",
            "payload": json.loads(raw_payload),
            "created_at": fields.get("created_at") or "",
        }

    def ack(self, kind: str, *, group: str, message_id: str) -> int:
        return int(self._redis().xack(self.key(kind), group, message_id))
