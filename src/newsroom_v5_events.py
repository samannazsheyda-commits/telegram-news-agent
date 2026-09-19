from __future__ import annotations

import json
import threading
import time
from collections import deque
from dataclasses import dataclass
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
