from __future__ import annotations

import socket
from typing import Any


class TranslationWorker:
    kind = "translate"
    group = "vision5-translation"

    def __init__(self, *, store: Any, queue: Any, pipeline: Any) -> None:
        self.store = store
        self.queue = queue
        self.pipeline = pipeline

    def run_once(self, *, consumer: str, block_ms: int = 1000) -> int:
        jobs = []
        if hasattr(self.queue, "reclaim"):
            jobs = self.queue.reclaim(
                self.kind, group=self.group, consumer=consumer, min_idle_ms=60_000, count=10
            )
        if not jobs:
            jobs = self.queue.read(
                self.kind,
                group=self.group,
                consumer=consumer,
                count=10,
                block_ms=block_ms,
            )
        if not jobs and hasattr(self.store, "story_ids_by_status"):
            jobs = [
                {"message_id": None, "payload": {"story_id": story_id}}
                for story_id in self.store.story_ids_by_status("NEW", limit=10)
            ]
        processed = 0
        for job in jobs:
            story_id = str(job.get("payload", {}).get("story_id") or "").strip()
            if not story_id:
                continue
            story = self.store.get_story(story_id)
            if story is None:
                if job.get("message_id") is not None:
                    self.queue.ack(self.kind, group=self.group, message_id=job["message_id"])
                continue
            status = str(story.get("status") or "")
            if status == "NEW":
                self.store.transition_story(story_id, "GOOGLE_TRANSLATING", actor="translation-worker")
                status = "GOOGLE_TRANSLATING"
            if status == "GOOGLE_TRANSLATING":
                translated = self.pipeline.translate_google(story)
                self.store.record_translation(
                    story_id,
                    provider="google",
                    title=translated["title"],
                    body=translated["body"],
                    actor="translation-worker",
                )
                status = "GOOGLE_TRANSLATED"
            if status == "GOOGLE_TRANSLATED":
                self.store.transition_story(story_id, "READY_FOR_REVIEW", actor="translation-worker")
                status = "READY_FOR_REVIEW"
            if status != "READY_FOR_REVIEW":
                continue
            if job.get("message_id") is not None:
                self.queue.ack(self.kind, group=self.group, message_id=job["message_id"])
            processed += 1
        return processed

    def run_forever(self, *, consumer: str | None = None) -> None:
        identity = consumer or socket.gethostname()
        while True:
            self.run_once(consumer=identity, block_ms=5000)


class PublishWorker:
    kind = "publish"
    group = "vision5-publisher"

    def __init__(self, *, queue: Any, publisher: Any) -> None:
        self.queue = queue
        self.publisher = publisher

    def run_once(self, *, consumer: str, block_ms: int = 1000) -> int:
        jobs = []
        if hasattr(self.queue, "reclaim"):
            jobs = self.queue.reclaim(
                self.kind, group=self.group, consumer=consumer, min_idle_ms=60_000, count=10
            )
        if not jobs:
            jobs = self.queue.read(
                self.kind,
                group=self.group,
                consumer=consumer,
                count=10,
                block_ms=block_ms,
            )
        if not jobs and hasattr(self.publisher, "recover_approved"):
            return len(self.publisher.recover_approved(limit=10))
        processed = 0
        for job in jobs:
            payload = dict(job.get("payload") or {})
            story_id = str(payload.get("story_id") or "").strip()
            if not story_id:
                continue
            self.publisher.publish(
                story_id,
                actor="publisher-worker",
                allow_retry=bool(payload.get("allow_retry", False)),
            )
            self.queue.ack(self.kind, group=self.group, message_id=job["message_id"])
            processed += 1
        return processed

    def run_forever(self, *, consumer: str | None = None) -> None:
        identity = consumer or socket.gethostname()
        while True:
            self.run_once(consumer=identity, block_ms=5000)
