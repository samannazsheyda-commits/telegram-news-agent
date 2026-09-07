from datetime import datetime, timedelta, timezone

from src.queue_freshness import expire_stale_queue


class FakeStore:
    def __init__(self, rows):
        self.rows = rows
        self.moved = []

    def queue(self):
        return list(self.rows)

    def move_to_history(self, item_id, status, **kwargs):
        self.moved.append((item_id, status))
        self.rows = [row for row in self.rows if row.get("id") != item_id]
        return {"id": item_id, "status": status}


def test_expire_stale_queue_removes_news_older_than_freshness_window():
    now = datetime(2026, 9, 7, 13, 30, tzinfo=timezone.utc)
    stale = (now - timedelta(hours=2, minutes=5)).strftime("%a, %d %b %Y %H:%M:%S GMT")
    fresh = (now - timedelta(minutes=45)).strftime("%a, %d %b %Y %H:%M:%S GMT")
    store = FakeStore([
        {"id": "old", "status": "pending", "published_at_source": stale},
        {"id": "new", "status": "pending", "published_at_source": fresh},
    ])

    moved = expire_stale_queue(now, settings={"freshness_hours": 2}, store=store)

    assert moved == 1
    assert store.moved == [("old", "superseded")]
    assert [row["id"] for row in store.queue()] == ["new"]
