from __future__ import annotations

from src.newsroom_v5_events import NewsroomEventBroker


def test_event_ids_are_monotonic_and_replay_after_last_id():
    broker = NewsroomEventBroker(max_events=10)
    first = broker.publish("story_added", {"story_id": "a"})
    second = broker.publish("story_updated", {"story_id": "a"})
    third = broker.publish("counts_changed", {"review": 1})

    assert first.id < second.id < third.id
    replay = broker.events_after(first.id)
    assert [event.id for event in replay] == [second.id, third.id]
    assert [event.type for event in replay] == ["story_updated", "counts_changed"]


def test_broker_is_bounded_and_reports_replay_gap():
    broker = NewsroomEventBroker(max_events=2)
    broker.publish("story_added", {"story_id": "a"})
    second = broker.publish("story_added", {"story_id": "b"})
    third = broker.publish("story_added", {"story_id": "c"})

    assert [event.id for event in broker.snapshot()] == [second.id, third.id]
    assert broker.replay_gap(0) is True
    assert broker.replay_gap(second.id) is False


def test_sse_encoding_contains_id_type_and_json_payload():
    broker = NewsroomEventBroker(max_events=5)
    event = broker.publish("story_rejected", {"story_id": "s1", "ok": True})
    encoded = broker.encode_sse(event)
    assert f"id: {event.id}" in encoded
    assert "event: story_rejected" in encoded
    assert '"story_id":"s1"' in encoded
    assert encoded.endswith("\n\n")
