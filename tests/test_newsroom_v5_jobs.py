from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.newsroom_v5_jobs import retry_delay_seconds
from src.newsroom_v5_store import NewsroomV5Store


def test_retry_delay_is_bounded_exponential_and_deterministic():
    delays = [retry_delay_seconds(i, seed="story-1") for i in range(1, 8)]
    assert delays[0] > 0
    assert delays[-1] <= 3600
    assert delays == [retry_delay_seconds(i, seed="story-1") for i in range(1, 8)]


def test_expired_job_lease_becomes_claimable(tmp_path):
    store = NewsroomV5Store(tmp_path / "db.sqlite")
    job = store.enqueue_job("translate_story", payload={})
    first = store.claim_jobs("translate_story", worker_id="a", limit=1, lease_seconds=60)
    assert first[0]["id"] == job["id"]

    expired = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    store.conn.execute("UPDATE jobs SET lease_until=? WHERE id=?", (expired, job["id"]))
    second = store.claim_jobs("translate_story", worker_id="b", limit=1, lease_seconds=60)
    assert second[0]["id"] == job["id"]
    assert second[0]["lease_owner"] == "b"
