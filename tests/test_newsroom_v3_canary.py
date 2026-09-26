from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.newsroom_v3.canary import canary_preflight, run_one_shot_canary
from src.newsroom_v3.store import NewsroomV3Store


def _ready_story(store: NewsroomV3Store, story_id: str, url: str) -> None:
    now = datetime.now(timezone.utc)
    store.upsert_story(
        story_id=story_id,
        source_item_id=story_id,
        source="Reuters",
        source_url=url,
        title=f"Fresh Iran story {story_id}",
        summary="Fresh verified detail.",
        published_at=(now - timedelta(minutes=10)).isoformat(),
        fetched_at=(now - timedelta(minutes=9)).isoformat(),
        media=[],
        source_priority="protected",
        fingerprint=f"fp-{story_id}",
        decision_state="ready",
        decision_reason="eligible",
    )


def _healthy_shadow(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "mode": "shadow",
                "sources_ok": 3,
                "sources_failed": 0,
                "processed": 8,
                "ready": 2,
                "telegram_writes": 0,
            }
        ),
        encoding="utf-8",
    )


def test_canary_refuses_to_publish_without_healthy_zero_write_shadow(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    store = NewsroomV3Store(data_dir / "newsroom_v3.sqlite3")
    _ready_story(store, "story-1", "https://example.com/1")
    store.close()

    status = data_dir / "newsroom_v3_shadow_status.json"
    status.write_text(json.dumps({"mode": "shadow", "processed": 5, "ready": 1, "sources_ok": 2, "telegram_writes": 1}), encoding="utf-8")
    calls = []

    result = run_one_shot_canary(
        data_dir=data_dir,
        publisher=lambda story: calls.append(story.story_id) or {"ok": True, "message_id": 99},
    )

    assert result["state"] == "shadow_not_healthy"
    assert result["telegram_writes"] == 0
    assert calls == []


def test_canary_skips_story_already_published_by_v2_and_publishes_only_one_safe_story(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    store = NewsroomV3Store(data_dir / "newsroom_v3.sqlite3")
    _ready_story(store, "story-old", "https://example.com/already-live")
    _ready_story(store, "story-safe", "https://example.com/safe")
    store.close()
    _healthy_shadow(data_dir / "newsroom_v3_shadow_status.json")

    (data_dir / "event_ledger.json").write_text(
        json.dumps(
            [
                {
                    "event_id": "v2-event",
                    "fingerprint": "old-fp",
                    "canonical_title": "Already live",
                    "first_seen": "2026-09-14T07:00:00+00:00",
                    "last_updated": "2026-09-14T07:00:00+00:00",
                    "primary_source": "Reuters",
                    "source_variants": ["https://example.com/already-live"],
                    "key_facts": [],
                    "published_message_ids": [444],
                    "status": "published",
                    "fingerprint_data": {},
                }
            ]
        ),
        encoding="utf-8",
    )
    calls = []

    result = run_one_shot_canary(
        data_dir=data_dir,
        publisher=lambda story: calls.append(story.story_id) or {"ok": True, "message_id": 555},
    )

    assert result["state"] == "published"
    assert result["story_id"] == "story-safe"
    assert result["telegram_message_id"] == 555
    assert result["telegram_writes"] == 1
    assert calls == ["story-safe"]


def test_canary_preflight_only_becomes_ready_for_a_safe_unpublished_candidate(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _healthy_shadow(data_dir / "newsroom_v3_shadow_status.json")
    store = NewsroomV3Store(data_dir / "newsroom_v3.sqlite3")
    _ready_story(store, "story-old", "https://example.com/already-live")
    store.close()
    (data_dir / "event_ledger.json").write_text(
        json.dumps(
            [
                {
                    "event_id": "v2-event",
                    "fingerprint": "fp-story-old",
                    "canonical_title": "Already live",
                    "first_seen": "2026-09-14T07:00:00+00:00",
                    "last_updated": "2026-09-14T07:00:00+00:00",
                    "primary_source": "Reuters",
                    "source_variants": ["https://example.com/already-live"],
                    "key_facts": [],
                    "published_message_ids": [444],
                    "status": "published",
                    "fingerprint_data": {"source_item_id": "story-old"},
                }
            ]
        ),
        encoding="utf-8",
    )

    assert canary_preflight(data_dir=data_dir)["ready"] is False

    store = NewsroomV3Store(data_dir / "newsroom_v3.sqlite3")
    _ready_story(store, "story-safe", "https://example.com/safe")
    store.close()

    result = canary_preflight(data_dir=data_dir)
    assert result["ready"] is True
    assert result["story_id"] == "story-safe"


def test_canary_never_selects_a_stale_ready_story_left_in_sqlite(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _healthy_shadow(data_dir / "newsroom_v3_shadow_status.json")
    store = NewsroomV3Store(data_dir / "newsroom_v3.sqlite3")
    store.upsert_story(
        story_id="stale-story",
        source_item_id="stale-story",
        source="Reuters",
        source_url="https://example.com/stale",
        title="Old Iran story left in the V3 store",
        summary="This was fresh several days ago.",
        published_at="2026-09-10T07:00:00+00:00",
        fetched_at="2026-09-10T07:01:00+00:00",
        media=[],
        source_priority="protected",
        fingerprint="fp-stale",
        decision_state="ready",
        decision_reason="eligible",
    )
    store.close()

    preflight = canary_preflight(data_dir=data_dir)
    assert preflight["ready"] is False
    assert preflight["reason"] == "no_safe_candidate"

    calls = []
    result = run_one_shot_canary(
        data_dir=data_dir,
        publisher=lambda story: calls.append(story.story_id) or {"ok": True, "message_id": 777},
    )
    assert result["state"] == "no_candidate"
    assert calls == []


def test_canary_marker_makes_the_external_attempt_strictly_one_shot(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    store = NewsroomV3Store(data_dir / "newsroom_v3.sqlite3")
    _ready_story(store, "story-1", "https://example.com/1")
    store.close()
    _healthy_shadow(data_dir / "newsroom_v3_shadow_status.json")
    calls = []

    first = run_one_shot_canary(
        data_dir=data_dir,
        publisher=lambda story: calls.append(story.story_id) or {"ok": False, "error": "network_ambiguous"},
    )
    second = run_one_shot_canary(
        data_dir=data_dir,
        publisher=lambda story: calls.append(story.story_id) or {"ok": True, "message_id": 999},
    )

    assert first["state"] == "failed"
    assert second["state"] == "already_attempted"
    assert calls == ["story-1"]
    marker = json.loads((data_dir / "newsroom_v3_canary_once.json").read_text(encoding="utf-8"))
    assert marker["story_id"] == "story-1"


def test_canary_requires_explicit_publisher_and_never_uses_shadow_cli_implicitly(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _healthy_shadow(data_dir / "newsroom_v3_shadow_status.json")
    with pytest.raises(ValueError, match="publisher"):
        run_one_shot_canary(data_dir=data_dir, publisher=None)


def test_production_publisher_fails_over_from_openrouter_daily_quota_to_groq(monkeypatch):
    from types import SimpleNamespace

    import src.newsroom_channel_publisher as channel_publisher
    import src.newsroom_v3.canary as canary_module
    from src.ai_newsroom import AIServiceError

    calls: list[str] = []

    class FakeOpenRouter:
        def __init__(self, config):
            self.available = True

        def translate_to_fa(self, text):
            calls.append("openrouter.translate")
            raise AIServiceError(
                "openrouter_http_429:Rate limit exceeded: free-models-per-day"
            )

        def edit_persian(self, source_text, draft_text):
            calls.append("openrouter.edit")
            raise AssertionError("quota-exhausted OpenRouter must not be retried for edit")

    class FakeGroq:
        def __init__(self, config):
            self.available = True

        def translate_to_fa(self, text):
            calls.append("groq.translate")
            return SimpleNamespace(text="ترجمه گروک", faithful=True)

        def edit_persian(self, source_text, draft_text):
            calls.append("groq.edit")
            return SimpleNamespace(
                text="متن نهایی گروک",
                faithful=True,
                natural=True,
                reason="ok",
            )

    class FakeHF:
        def __init__(self, config):
            self.available = True

        def translate_to_fa(self, text):
            calls.append("hf.translate")
            raise AssertionError("HF should not run when Groq succeeds")

        def edit_persian(self, source_text, draft_text):
            calls.append("hf.edit")
            raise AssertionError("HF should not run when Groq succeeds")

    monkeypatch.setenv("AI_NEWSROOM_MODE", "required")
    monkeypatch.setenv("OPENROUTER_API_KEY", "openrouter-test")
    monkeypatch.setenv("GROQ_API_KEY", "groq-test")
    monkeypatch.setenv("HF_TOKEN", "hf-test")
    monkeypatch.setattr(channel_publisher, "LocalFirstOpenRouterNewsAI", FakeOpenRouter)
    monkeypatch.setattr(channel_publisher, "LocalFirstGroqNewsAI", FakeGroq)
    monkeypatch.setattr(channel_publisher, "LocalFirstNewsAI", FakeHF)

    publisher = canary_module.build_production_publisher().publisher
    draft = publisher.ai.translate_to_fa("Iran launched two missiles")
    edit = publisher.ai.edit_persian("Iran launched two missiles", draft.text)

    assert draft.text == "ترجمه گروک"
    assert edit.text == "متن نهایی گروک"
    assert calls == ["openrouter.translate", "groq.translate", "groq.edit"]


def test_production_publisher_fails_over_from_groq_to_hf_when_needed(monkeypatch):
    from types import SimpleNamespace

    import src.newsroom_channel_publisher as channel_publisher
    import src.newsroom_v3.canary as canary_module
    from src.ai_newsroom import AIServiceError

    calls: list[str] = []

    class FakeOpenRouter:
        def __init__(self, config):
            self.available = True

        def translate_to_fa(self, text):
            calls.append("openrouter.translate")
            raise AIServiceError("openrouter_network_error")

    class FakeGroq:
        def __init__(self, config):
            self.available = True

        def translate_to_fa(self, text):
            calls.append("groq.translate")
            raise AIServiceError("groq_http_503")

    class FakeHF:
        def __init__(self, config):
            self.available = True

        def translate_to_fa(self, text):
            calls.append("hf.translate")
            return SimpleNamespace(text="ترجمه اچ اف", faithful=True)

        def edit_persian(self, source_text, draft_text):
            calls.append("hf.edit")
            return SimpleNamespace(
                text="متن نهایی اچ اف",
                faithful=True,
                natural=True,
                reason="ok",
            )

    monkeypatch.setenv("AI_NEWSROOM_MODE", "required")
    monkeypatch.setenv("OPENROUTER_API_KEY", "openrouter-test")
    monkeypatch.setenv("GROQ_API_KEY", "groq-test")
    monkeypatch.setenv("HF_TOKEN", "hf-test")
    monkeypatch.setattr(channel_publisher, "LocalFirstOpenRouterNewsAI", FakeOpenRouter)
    monkeypatch.setattr(channel_publisher, "LocalFirstGroqNewsAI", FakeGroq)
    monkeypatch.setattr(channel_publisher, "LocalFirstNewsAI", FakeHF)

    publisher = canary_module.build_production_publisher().publisher
    draft = publisher.ai.translate_to_fa("Iran launched two missiles")
    edit = publisher.ai.edit_persian("Iran launched two missiles", draft.text)

    assert draft.text == "ترجمه اچ اف"
    assert edit.text == "متن نهایی اچ اف"
    assert calls == [
        "openrouter.translate",
        "groq.translate",
        "hf.translate",
        "hf.edit",
    ]
