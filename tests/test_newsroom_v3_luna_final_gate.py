from types import SimpleNamespace

from src.newsroom_v3.final_gate import LunaFinalPublishGate
from src.newsroom_v3.store import StoryRecord


def _story(story_id: str = "candidate") -> StoryRecord:
    return StoryRecord(
        story_id=story_id,
        source_item_id=story_id,
        source="Clash Report",
        source_url="https://x.com/clashreport/status/1",
        title="Iran announced a concrete missile deployment change",
        summary="The announcement specifies a new operational deployment.",
        published_at="2026-09-16T08:00:00+00:00",
        fetched_at="2026-09-16T08:01:00+00:00",
        media=[],
        source_priority="protected",
        fingerprint=f"fp-{story_id}",
        decision_state="ready",
        decision_reason="eligible",
        duplicate_of="",
        publish_state="not_attempted",
        last_publish_error="",
        telegram_message_id=None,
        created_at="2026-09-16T08:01:00+00:00",
        updated_at="2026-09-16T08:01:00+00:00",
    )


class _FakeAI:
    def __init__(self, payload=None, *, available=True, error=None):
        self.available = available
        self.payload = payload
        self.error = error
        self.config = SimpleNamespace(model="gpt-5.6-luna")
        self.calls = []

    def _chat_json(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.payload


def test_luna_gate_accepts_only_valid_structured_approval():
    ai = _FakeAI({"approve": True, "reason": "factual_unique_event"})
    result = LunaFinalPublishGate(ai)(_story(), [_story("recent")])
    assert result.approved is True
    assert result.reason == "factual_unique_event"
    assert ai.calls[0]["model"] == "gpt-5.6-luna"
    assert "Clash Report" in ai.calls[0]["user"]
    assert "recent" in ai.calls[0]["user"]


def test_luna_gate_rejects_duplicate_decision():
    ai = _FakeAI({"approve": False, "reason": "duplicate_event"})
    result = LunaFinalPublishGate(ai)(_story(), [])
    assert result.approved is False
    assert result.reason == "duplicate_event"


def test_luna_gate_fails_closed_when_unavailable_invalid_or_error():
    unavailable = LunaFinalPublishGate(_FakeAI(available=False))(_story(), [])
    invalid = LunaFinalPublishGate(_FakeAI({"approve": "yes", "reason": "ok"}))(_story(), [])
    failed = LunaFinalPublishGate(_FakeAI(error=RuntimeError("timeout")))(_story(), [])
    assert (unavailable.approved, unavailable.reason) == (False, "luna_unavailable")
    assert (invalid.approved, invalid.reason) == (False, "invalid_luna_decision")
    assert (failed.approved, failed.reason) == (False, "luna_error")
