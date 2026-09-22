from __future__ import annotations


class Response:
    def __init__(self, *, text="", payload=None):
        self.text = text
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class Session:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, *, headers=None, params=None, timeout=None):
        self.calls.append({"url": url, "headers": headers, "params": params, "timeout": timeout})
        return self.responses.pop(0)


def test_source_fetcher_collects_rss_and_public_telegram_without_legacy_code():
    from bikhabar_v5.source_runtime import SourceFetcher

    rss = """<rss><channel><item><title>Headline</title><link>https://e/1</link><description>Body</description><pubDate>Tue, 22 Sep 2026 10:00:00 GMT</pubDate></item></channel></rss>"""
    telegram = """<div class="tgme_widget_message" data-post="channel/44"><div class="tgme_widget_message_text">Telegram headline<br>Body</div><time datetime="2026-09-22T10:00:00+00:00"></time></div>"""
    session = Session([Response(text=rss), Response(text=telegram)])
    fetcher = SourceFetcher(session=session)
    rss_rows = fetcher.fetch({"id": "s1", "kind": "rss", "identity": "https://e/feed", "display_name": "Feed"})
    tg_rows = fetcher.fetch({"id": "s2", "kind": "telegram", "identity": "channel", "display_name": "Channel"})

    assert rss_rows[0]["source_url"] == "https://e/1"
    assert tg_rows[0]["source_url"] == "https://t.me/channel/44"
    assert "Telegram headline" in tg_rows[0]["original_text"]


def test_source_fetcher_uses_x_recent_search_api_with_bearer_token():
    from bikhabar_v5.source_runtime import SourceFetcher

    session = Session(
        [
            Response(
                payload={
                    "data": [{"id": "99", "text": "Breaking", "created_at": "2026-09-22T10:00:00Z", "author_id": "u1"}],
                    "includes": {"users": [{"id": "u1", "username": "Reuters"}]},
                }
            )
        ]
    )
    rows = SourceFetcher(session=session, x_bearer_token="bearer").fetch(
        {"id": "s1", "kind": "x", "identity": "Reuters", "display_name": "Reuters X"}
    )

    assert rows[0]["source_url"] == "https://x.com/Reuters/status/99"
    assert session.calls[0]["headers"]["Authorization"] == "Bearer bearer"
    assert session.calls[0]["params"]["query"] == "from:Reuters -is:retweet"


class CollectorStore:
    def __init__(self):
        self.sources = [{"id": "s1", "kind": "rss", "identity": "feed", "display_name": "Feed", "enabled": True}]
        self.health = []

    def list_sources(self):
        return self.sources

    def ingest_story(self, story):
        return ({"id": story["id"]}, True)

    def record_collector_run(self, source_id, *, status, received, inserted, error=None):
        self.health.append((source_id, status, received, inserted, error))


class Fetcher:
    def fetch(self, source):
        return [{"id": "story-1", "source": "Feed", "original_title": "Title"}]


class JobQueue:
    def __init__(self):
        self.jobs = []

    def enqueue(self, kind, payload):
        self.jobs.append((kind, payload))


def test_collector_runtime_ingests_queues_translation_and_records_health():
    from bikhabar_v5.source_runtime import CollectorRuntime

    store = CollectorStore()
    queue = JobQueue()
    result = CollectorRuntime(store=store, queue=queue, fetcher=Fetcher()).run_once()

    assert result == {"sources": 1, "received": 1, "inserted": 1, "duplicates": 0, "failed": 0}
    assert queue.jobs == [("translate", {"story_id": "story-1"})]
    assert store.health[0][1] == "succeeded"
