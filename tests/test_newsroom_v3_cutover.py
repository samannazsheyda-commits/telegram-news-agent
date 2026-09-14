from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import src.newsroom_hybrid_runtime as hybrid
from src.newsroom_v3.outbox import NewsroomV3PublisherWorker
from src.newsroom_v3.production import cutover_gate, run_once as run_v3_production_once
from src.newsroom_v3.store import NewsroomV3Store


def _ready_story(
    store: NewsroomV3Store,
    story_id: str,
    url: str,
    *,
    published_at: str,
) -> None:
    store.upsert_story(
        story_id=story_id,
        source_item_id=story_id,
        source="Reuters",
        source_url=url,
        title=f"Fresh Iran story {story_id}",
        summary="Fresh verified detail.",
        published_at=published_at,
        fetched_at=published_at,
        media=[],
        source_priority="protected",
        fingerprint=f"fp-{story_id}",
        decision_state="ready",
        decision_reason="eligible",
    )


def _published_canary(data_dir: Path) -> None:
    (data_dir / "newsroom_v3_canary_once.json").write_text(
        json.dumps(
            {
                "state": "published",
                "attempt_no": 1,
                "telegram_writes": 1,
                "telegram_message_id": 1438,
            }
        ),
        encoding="utf-8",
    )


def test_cutover_gate_requires_one_verified_published_canary(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    assert cutover_gate(data_dir=data_dir)["ready"] is False

    (data_dir / "newsroom_v3_canary_once.json").write_text(
        json.dumps({"state": "failed", "attempt_no": 1, "telegram_writes": 0}),
        encoding="utf-8",
    )
    assert cutover_gate(data_dir=data_dir)["ready"] is False

    _published_canary(data_dir)
    result = cutover_gate(data_dir=data_dir)
    assert result["ready"] is True
    assert result["telegram_message_id"] == 1438


def test_v3_production_skips_v2_published_and_stale_and_publishes_only_one(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    store = NewsroomV3Store(data_dir / "newsroom_v3.sqlite3")
    _ready_story(
        store,
        "v2-old",
        "https://example.com/already-live",
        published_at="2026-09-14T09:55:00+00:00",
    )
    _ready_story(
        store,
        "safe-new",
        "https://example.com/safe-new",
        published_at="2026-09-14T09:58:00+00:00",
    )
    _ready_story(
        store,
        "stale",
        "https://example.com/stale",
        published_at="2026-09-10T09:58:00+00:00",
    )
    store.close()

    (data_dir / "event_ledger.json").write_text(
        json.dumps(
            [
                {
                    "event_id": "v2-event",
                    "fingerprint": "fp-v2-old",
                    "canonical_title": "Already live",
                    "first_seen": "2026-09-14T09:55:00+00:00",
                    "last_updated": "2026-09-14T09:55:00+00:00",
                    "primary_source": "Reuters",
                    "source_variants": ["https://example.com/already-live"],
                    "key_facts": [],
                    "published_message_ids": [1400],
                    "status": "published",
                    "fingerprint_data": {"source_item_id": "v2-old"},
                }
            ]
        ),
        encoding="utf-8",
    )

    calls: list[str] = []
    result = run_v3_production_once(
        data_dir=data_dir,
        fetchers=[],
        publisher=lambda story: calls.append(story.story_id)
        or {"ok": True, "message_id": 1500},
        now=datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc),
        publish_enabled=True,
        min_publish_interval_seconds=0,
    )

    assert result["mode"] == "production"
    assert result["published"] == 1
    assert result["telegram_writes"] == 1
    assert result["story_id"] == "safe-new"
    assert calls == ["safe-new"]


def test_v3_production_does_not_retry_a_recent_failed_publish(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    now = datetime.now(timezone.utc)
    stamp = now.isoformat()
    store = NewsroomV3Store(data_dir / "newsroom_v3.sqlite3")
    _ready_story(store, "retry-me", "https://example.com/retry", published_at=stamp)
    NewsroomV3PublisherWorker(
        store,
        lambda story: {"ok": False, "error": "temporary_failure"},
    ).publish_story("retry-me")
    store.close()

    calls: list[str] = []
    result = run_v3_production_once(
        data_dir=data_dir,
        fetchers=[],
        publisher=lambda story: calls.append(story.story_id)
        or {"ok": True, "message_id": 1600},
        now=now,
        publish_enabled=True,
        min_publish_interval_seconds=0,
        retry_cooldown_seconds=600,
    )

    assert result["published"] == 0
    assert result["telegram_writes"] == 0
    assert result["reason"] == "retry_cooldown"
    assert calls == []


def test_v3_production_respects_publish_pause(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    store = NewsroomV3Store(data_dir / "newsroom_v3.sqlite3")
    _ready_story(
        store,
        "paused",
        "https://example.com/paused",
        published_at="2026-09-14T09:58:00+00:00",
    )
    store.close()
    calls: list[str] = []

    result = run_v3_production_once(
        data_dir=data_dir,
        fetchers=[],
        publisher=lambda story: calls.append(story.story_id),
        now=datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc),
        publish_enabled=False,
    )

    assert result["published"] == 0
    assert result["telegram_writes"] == 0
    assert result["reason"] == "publish_paused"
    assert calls == []


def test_hybrid_v3_cutover_keeps_v2_shadow_for_panel_but_only_v3_can_publish(monkeypatch):
    calls: list[tuple[str, object]] = []
    monkeypatch.setenv("NEWSROOM_ENGINE", "v3")
    monkeypatch.setenv("DATA_DIR", "/runtime/data")
    monkeypatch.setattr(hybrid, "run_ancillary_cycle", lambda now: 0)
    monkeypatch.setattr(hybrid.v13, "load_newsroom_settings", lambda: {"auto_publish": True})
    monkeypatch.setattr(hybrid.v13, "newsroom_publish_paused", lambda settings, now: False)
    monkeypatch.setattr(
        hybrid,
        "v3_cutover_gate",
        lambda **kwargs: {"ready": True, "reason": "verified_canary"},
    )

    def v2(**kwargs):
        calls.append(("v2", kwargs["shadow"]))
        return {"published": 0, "telegram_writes": 0}

    def v3(**kwargs):
        calls.append(("v3", kwargs["publish_enabled"]))
        return {
            "mode": "production",
            "published": 1,
            "telegram_writes": 1,
            "publish_failed": 0,
        }

    monkeypatch.setattr(hybrid, "run_v2_once", v2)
    monkeypatch.setattr(hybrid, "run_v3_production_once", v3)

    result = hybrid.run_cycle(
        shadow=False,
        now=datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc),
    )

    assert calls == [("v2", True), ("v3", True)]
    assert result["newsroom_engine"] == "v3"
    assert result["telegram_writes"] == 1


def test_hybrid_refuses_v3_without_verified_canary_and_keeps_v2_primary(monkeypatch):
    calls: list[tuple[str, object]] = []
    monkeypatch.setenv("NEWSROOM_ENGINE", "v3")
    monkeypatch.setenv("DATA_DIR", "/runtime/data")
    monkeypatch.setattr(hybrid, "run_ancillary_cycle", lambda now: 0)
    monkeypatch.setattr(hybrid.v13, "load_newsroom_settings", lambda: {"auto_publish": True})
    monkeypatch.setattr(hybrid.v13, "newsroom_publish_paused", lambda settings, now: False)
    monkeypatch.setattr(
        hybrid,
        "v3_cutover_gate",
        lambda **kwargs: {"ready": False, "reason": "canary_missing"},
    )

    def v2(**kwargs):
        calls.append(("v2", kwargs["shadow"]))
        return {"published": 1, "telegram_writes": 1}

    monkeypatch.setattr(hybrid, "run_v2_once", v2)
    monkeypatch.setattr(
        hybrid,
        "run_v3_production_once",
        lambda **kwargs: calls.append(("v3", True)) or {},
    )

    result = hybrid.run_cycle(
        shadow=False,
        now=datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc),
    )

    assert calls == [("v2", False)]
    assert result["newsroom_engine"] == "v2_fallback"
    assert result["v3_gate_reason"] == "canary_missing"


def test_standalone_shadow_service_skips_when_v3_is_primary():
    service = Path("deploy/bikhabar-newsroom-v3-shadow.service").read_text(encoding="utf-8")
    assert "ExecCondition=" in service
    assert "NEWSROOM_ENGINE:-v2" in service
    assert '!= "v3"' in service
