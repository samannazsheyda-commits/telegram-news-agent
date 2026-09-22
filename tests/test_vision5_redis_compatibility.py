from __future__ import annotations

import pytest


class Redis5StreamsClient:
    def __init__(self) -> None:
        self.claimed_ids: list[str] = []

    def xgroup_create(self, *_args, **_kwargs):
        return True

    def xautoclaim(self, *_args, **_kwargs):
        raise RuntimeError("unknown command `XAUTOCLAIM`")

    def xpending_range(self, *_args, **kwargs):
        if kwargs.get("idle") is not None:
            raise RuntimeError("syntax error")
        return [
            {
                "message_id": "1-0",
                "consumer": "worker-a",
                "time_since_delivered": 500,
                "times_delivered": 1,
            },
            {
                "message_id": "2-0",
                "consumer": "worker-a",
                "time_since_delivered": 70_000,
                "times_delivered": 1,
            },
        ]

    def xclaim(self, _key, _group, _consumer, _min_idle_time, message_ids):
        self.claimed_ids = list(message_ids)
        return [
            (
                "2-0",
                {
                    "job_id": "job-2",
                    "payload": '{"story_id":"story-2"}',
                    "created_at": "2026-09-22T17:00:00+00:00",
                },
            )
        ]


def test_reclaim_falls_back_to_xpending_and_xclaim_on_redis_5():
    from bikhabar_v5.queue import RedisJobQueue

    client = Redis5StreamsClient()
    queue = RedisJobQueue("redis://127.0.0.1:6379/5", client=client)

    jobs = queue.reclaim(
        "translate",
        group="vision5-translation",
        consumer="worker-b",
        min_idle_ms=60_000,
        count=10,
    )

    assert client.claimed_ids == ["2-0"]
    assert jobs == [
        {
            "message_id": "2-0",
            "job_id": "job-2",
            "payload": {"story_id": "story-2"},
            "created_at": "2026-09-22T17:00:00+00:00",
        }
    ]


class BrokenStreamsClient(Redis5StreamsClient):
    def xautoclaim(self, *_args, **_kwargs):
        raise RuntimeError("READONLY You can't write against a read only replica")


def test_reclaim_does_not_hide_unrelated_redis_errors():
    from bikhabar_v5.queue import RedisJobQueue

    queue = RedisJobQueue("redis://127.0.0.1:6379/5", client=BrokenStreamsClient())

    with pytest.raises(RuntimeError, match="READONLY"):
        queue.reclaim(
            "translate",
            group="vision5-translation",
            consumer="worker-b",
        )
