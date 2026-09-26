from __future__ import annotations

import json
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterator


@dataclass(frozen=True)
class NewsroomEvent:
    id: int
    type: str
    payload: dict[str, Any]
    created_monotonic: float


class NewsroomEventBroker:
    def __init__(self, *, max_events: int = 512) -> None:
        self.max_events = max(2, int(max_events))
        self._events: deque[NewsroomEvent] = deque(maxlen=self.max_events)
        self._next_id = 1
        self._condition = threading.Condition()

    def publish(self, event_type: str, payload: dict[str, Any] | None = None) -> NewsroomEvent:
        with self._condition:
            # deque.maxlen cannot be changed after construction. Tests may tune
            # max_events, so enforce the public bound before appending.
            while len(self._events) >= self.max_events:
                self._events.popleft()
            event = NewsroomEvent(
                id=self._next_id,
                type=str(event_type),
                payload=dict(payload or {}),
                created_monotonic=time.monotonic(),
            )
            self._next_id += 1
            self._events.append(event)
            self._condition.notify_all()
            return event

    def snapshot(self) -> list[NewsroomEvent]:
        with self._condition:
            return list(self._events)

    def events_after(self, last_event_id: int) -> list[NewsroomEvent]:
        with self._condition:
            return [event for event in self._events if event.id > int(last_event_id)]

    def replay_gap(self, last_event_id: int) -> bool:
        with self._condition:
            if not self._events:
                return False
            return int(last_event_id) < self._events[0].id - 1

    @staticmethod
    def encode_sse(event: NewsroomEvent) -> str:
        data = json.dumps(event.payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return f"id: {event.id}\nevent: {event.type}\ndata: {data}\n\n"

    def stream(self, last_event_id: int = 0, *, heartbeat_seconds: float = 20.0) -> Iterator[str]:
        cursor = max(0, int(last_event_id))
        if self.replay_gap(cursor):
            yield "event: refetch_required\ndata: {\"reason\":\"replay_gap\"}\n\n"
            snapshot = self.snapshot()
            cursor = snapshot[-1].id if snapshot else cursor
        else:
            for event in self.events_after(cursor):
                cursor = event.id
                yield self.encode_sse(event)

        while True:
            with self._condition:
                ready = [event for event in self._events if event.id > cursor]
                if not ready:
                    self._condition.wait(timeout=max(1.0, float(heartbeat_seconds)))
                    ready = [event for event in self._events if event.id > cursor]
            if not ready:
                yield ": heartbeat\n\n"
                continue
            for event in ready:
                cursor = event.id
                yield self.encode_sse(event)


class SqliteEventLog:
    """Durable post-commit event log shared by every process using the same DB.

    The panel runs several gunicorn workers and the ingest/publish worker runs in
    another process, so an in-memory broker cannot see their events. Writers
    append rows; SSE streams tail the table by id.
    """

    def __init__(self, store, *, max_events: int = 5000, poll_seconds: float = 0.5) -> None:
        self.store = store
        self.max_events = max(2, int(max_events))
        self.poll_seconds = max(0.01, float(poll_seconds))

    @property
    def _conn(self):
        return self.store.conn

    @staticmethod
    def _event(row) -> NewsroomEvent:
        try:
            payload = json.loads(row["payload_json"] or "{}")
        except ValueError:
            payload = {}
        return NewsroomEvent(id=int(row["id"]), type=str(row["type"]), payload=payload, created_monotonic=0.0)

    def publish(self, event_type: str, payload: dict[str, Any] | None = None) -> NewsroomEvent:
        data = json.dumps(dict(payload or {}), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        cur = self._conn.execute(
            "INSERT INTO events(type, payload_json, created_at) VALUES (?,?,?)",
            (str(event_type), data, datetime.now(timezone.utc).isoformat()),
        )
        event_id = int(cur.lastrowid)
        if event_id > self.max_events:
            self._conn.execute("DELETE FROM events WHERE id <= ?", (event_id - self.max_events,))
        return NewsroomEvent(id=event_id, type=str(event_type), payload=dict(payload or {}), created_monotonic=time.monotonic())

    def snapshot(self) -> list[NewsroomEvent]:
        return self.events_after(0)

    def events_after(self, last_event_id: int, *, limit: int = 500) -> list[NewsroomEvent]:
        rows = self._conn.execute(
            "SELECT id, type, payload_json FROM events WHERE id > ? ORDER BY id LIMIT ?",
            (int(last_event_id), int(limit)),
        ).fetchall()
        return [self._event(row) for row in rows]

    def latest_id(self) -> int:
        row = self._conn.execute("SELECT MAX(id) FROM events").fetchone()
        return int(row[0] or 0)

    def replay_gap(self, last_event_id: int) -> bool:
        row = self._conn.execute("SELECT MIN(id) FROM events").fetchone()
        oldest = row[0]
        if oldest is None:
            return False
        return int(last_event_id) < int(oldest) - 1

    encode_sse = staticmethod(NewsroomEventBroker.encode_sse)

    def stream(self, last_event_id: int = 0, *, heartbeat_seconds: float = 20.0) -> Iterator[str]:
        cursor = max(0, int(last_event_id))
        if self.replay_gap(cursor):
            yield "event: refetch_required\ndata: {\"reason\":\"replay_gap\"}\n\n"
            cursor = self.latest_id()
        last_output = time.monotonic()
        while True:
            ready = self.events_after(cursor)
            for event in ready:
                cursor = event.id
                yield self.encode_sse(event)
            if ready:
                last_output = time.monotonic()
                continue
            if time.monotonic() - last_output >= max(1.0, float(heartbeat_seconds)):
                last_output = time.monotonic()
                yield ": heartbeat\n\n"
            time.sleep(self.poll_seconds)
