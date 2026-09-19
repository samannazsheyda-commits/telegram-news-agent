from __future__ import annotations

from dataclasses import dataclass

from src.newsroom_v5_editorial import route_editorial
from src.newsroom_v5_store import NewsroomV5Store


@dataclass
class Decision:
    importance: int = 90
    topic: str = "security"
    publish: bool = True
    reason: str = "concrete new fact"
    new_fact: bool = True
    priority_class: str = "critical"
    confidence: float = 0.95


def _ready(store, story_id="s1"):
    store.upsert_story({
        "id": story_id,
        "news_key": story_id,
        "source_id": "src",
        "source_name": "Source",
        "source_url": f"https://example.test/{story_id}",
        "source_item_id": story_id,
        "original_title": "Original",
        "published_at_source": "2026-09-20T10:00:00+00:00",
        "state": "translated",
    })
    store.set_translation(story_id, title_fa="خبر فارسی معتبر", body_fa="متن فارسی معتبر", backend="test", quality_passed=True)


def test_auto_publish_off_routes_even_critical_story_to_review(tmp_path):
    store = NewsroomV5Store(tmp_path / "db.sqlite")
    _ready(store)
    outcome = route_editorial(store, "s1", Decision(), auto_publish_enabled=False)
    assert outcome == "review"
    assert store.get_story("s1")["state"] == "review"


def test_auto_publish_candidate_requires_all_gates(tmp_path):
    store = NewsroomV5Store(tmp_path / "db.sqlite")
    _ready(store)
    assert route_editorial(store, "s1", Decision(), auto_publish_enabled=True) == "auto_publish_candidate"


def test_routine_or_low_confidence_relevant_story_falls_back_to_review(tmp_path):
    store = NewsroomV5Store(tmp_path / "db.sqlite")
    _ready(store)
    d = Decision(importance=55, publish=False, new_fact=False, priority_class="normal", confidence=0.5)
    assert route_editorial(store, "s1", d, auto_publish_enabled=True) == "review"


def test_disabled_source_stale_or_missing_qc_never_auto_publishes(tmp_path):
    store = NewsroomV5Store(tmp_path / "db.sqlite")
    _ready(store, "disabled")
    assert route_editorial(store, "disabled", Decision(), auto_publish_enabled=True, source_enabled=False) == "review"
    _ready(store, "stale")
    assert route_editorial(store, "stale", Decision(), auto_publish_enabled=True, fresh=False) == "review"
    _ready(store, "bad-qc")
    store.set_translation("bad-qc", title_fa="x", body_fa="", backend="test", quality_passed=False)
    assert route_editorial(store, "bad-qc", Decision(), auto_publish_enabled=True) == "failed"


def test_duplicate_and_irrelevant_are_terminal_not_review(tmp_path):
    store = NewsroomV5Store(tmp_path / "db.sqlite")
    _ready(store, "dup")
    assert route_editorial(store, "dup", Decision(), duplicate=True) == "duplicate"
    _ready(store, "irr")
    assert route_editorial(store, "irr", Decision(), relevant=False) == "irrelevant"
