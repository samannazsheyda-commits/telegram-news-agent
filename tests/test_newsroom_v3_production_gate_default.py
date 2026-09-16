from datetime import datetime, timezone

import src.newsroom_v3.production as production
from src.newsroom_v3.final_gate import FinalGateDecision
from src.newsroom_v3.store import NewsroomV3Store


def _ready_story(store: NewsroomV3Store, story_id: str, now: datetime):
    stamp = now.isoformat()
    store.upsert_story(
        story_id=story_id,
        source_item_id=story_id,
        source="Reuters",
        source_url=f"https://example.com/{story_id}",
        title="Iran announces a concrete missile deployment change",
        summary="A current factual event with a named actor and action.",
        published_at=stamp,
        fetched_at=stamp,
        media=[],
        source_priority="protected",
        fingerprint=f"fp-{story_id}",
        decision_state="ready",
        decision_reason="eligible",
    )


def test_real_production_path_automatically_runs_luna_gate_before_publisher(monkeypatch, tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    now = datetime.now(timezone.utc)
    store = NewsroomV3Store(data / "newsroom_v3.sqlite3")
    _ready_story(store, "candidate", now)
    store.close()

    events = []

    class Gate:
        def __call__(self, story, recent):
            events.append(("gate", story.story_id))
            return FinalGateDecision(True, "factual_unique_event")

    monkeypatch.setattr(production, "LunaFinalPublishGate", lambda: Gate())
    monkeypatch.setattr(
        production,
        "_production_publisher",
        lambda: (lambda story: events.append(("telegram", story.story_id)) or {"ok": True, "message_id": 401}),
    )

    result = production.run_once(
        data_dir=data,
        fetchers=[],
        now=now,
        min_publish_interval_seconds=0,
    )

    assert result["reason"] == "published"
    assert events == [("gate", "candidate"), ("telegram", "candidate")]


def test_real_production_path_never_calls_publisher_when_default_luna_gate_fails_closed(monkeypatch, tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    now = datetime.now(timezone.utc)
    store = NewsroomV3Store(data / "newsroom_v3.sqlite3")
    _ready_story(store, "blocked", now)
    store.close()

    class Gate:
        def __call__(self, story, recent):
            return FinalGateDecision(False, "luna_error")

    publisher_built = []
    monkeypatch.setattr(production, "LunaFinalPublishGate", lambda: Gate())
    monkeypatch.setattr(production, "_production_publisher", lambda: publisher_built.append(True))

    result = production.run_once(
        data_dir=data,
        fetchers=[],
        now=now,
        min_publish_interval_seconds=0,
    )

    assert result["reason"] == "final_gate_error"
    assert result["telegram_writes"] == 0
    assert publisher_built == []
