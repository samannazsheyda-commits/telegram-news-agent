from __future__ import annotations


class Queue:
    def __init__(self, jobs):
        self.jobs = list(jobs)
        self.acks = []
        self.enqueued = []

    def read(self, kind, *, group, consumer, count, block_ms):
        return self.jobs[:count]

    def ack(self, kind, *, group, message_id):
        self.acks.append((kind, group, message_id))
        return 1

    def enqueue(self, kind, payload):
        self.enqueued.append((kind, payload))
        return "job-new"


class TranslationStore:
    def __init__(self):
        self.transitions = []
        self.translations = []

    def get_story(self, story_id):
        return {"id": story_id, "status": "NEW", "original_title": "English", "original_text": "Body"}

    def transition_story(self, story_id, target, *, actor, detail=None):
        self.transitions.append((story_id, target, actor))
        return {"id": story_id, "status": target}

    def record_translation(self, story_id, *, provider, title, body, actor):
        self.translations.append((story_id, provider, title, body, actor))
        return {"id": story_id, "status": "GOOGLE_TRANSLATED"}


class Pipeline:
    def translate_google(self, story):
        return {"provider": "google", "title": "تیتر فارسی", "body": "متن فارسی"}


def test_translation_worker_moves_one_story_to_review_and_acks_only_success():
    from bikhabar_v5.workers import TranslationWorker

    queue = Queue([{"message_id": "1-0", "payload": {"story_id": "story-1"}}])
    store = TranslationStore()
    processed = TranslationWorker(store=store, queue=queue, pipeline=Pipeline()).run_once(
        consumer="worker-1"
    )

    assert processed == 1
    assert [target for _, target, _ in store.transitions] == ["GOOGLE_TRANSLATING", "READY_FOR_REVIEW"]
    assert store.translations[0][1] == "google"
    assert queue.acks == [("translate", "vision5-translation", "1-0")]


class Publisher:
    def __init__(self):
        self.calls = []

    def publish(self, story_id, *, actor, allow_retry=False):
        self.calls.append((story_id, actor, allow_retry))
        return {"id": story_id, "status": "PUBLISHED"}


def test_publish_worker_publishes_and_acknowledges_job():
    from bikhabar_v5.workers import PublishWorker

    queue = Queue([{"message_id": "2-0", "payload": {"story_id": "story-2", "allow_retry": False}}])
    publisher = Publisher()
    processed = PublishWorker(queue=queue, publisher=publisher).run_once(consumer="worker-1")

    assert processed == 1
    assert publisher.calls == [("story-2", "publisher-worker", False)]
    assert queue.acks == [("publish", "vision5-publisher", "2-0")]
