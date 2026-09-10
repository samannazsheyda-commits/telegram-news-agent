from __future__ import annotations

import inspect
import json
from datetime import datetime, timezone
from pathlib import Path

import src.newsroom_hybrid_runtime as hybrid


def test_runtime_heartbeat_defaults_to_configured_state_path(tmp_path, monkeypatch):
    signature = inspect.signature(hybrid._record_runtime_heartbeat)
    assert signature.parameters["state_path"].default is None

    target = tmp_path / "runtime" / "state.json"
    monkeypatch.setenv("STATE_PATH", str(target))
    hybrid._record_runtime_heartbeat(
        {
            "rc": 0,
            "published": 1,
            "telegram_writes": 1,
            "publish_failed": 0,
            "sources_ok": 7,
            "sources_failed": 1,
            "items_fetched": 42,
            "panel_commands": 2,
        },
        now=datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc),
    )

    state = json.loads(target.read_text(encoding="utf-8"))
    assert state["last_cycle_at"] == "2026-09-10T12:00:00+00:00"
    assert state["last_publication_at"] == "2026-09-10T12:00:00+00:00"
    assert state["telegram_state"] == "ok"
    assert state["last_sources_ok"] == 7
    assert state["last_sources_failed"] == 1
    assert state["last_items_fetched"] == 42
    assert state["last_panel_commands"] == 2


def test_runtime_heartbeat_marks_real_publish_failure(tmp_path):
    target = tmp_path / "state.json"
    hybrid._record_runtime_heartbeat(
        {
            "rc": 0,
            "published": 0,
            "telegram_writes": 0,
            "publish_failed": 2,
            "sources_ok": 5,
            "sources_failed": 0,
            "items_fetched": 8,
        },
        state_path=target,
    )
    state = json.loads(target.read_text(encoding="utf-8"))
    assert state["telegram_state"] == "error"
    assert state["last_publish_failed"] == 2
    assert "انتشار" in state["last_error"]


def test_quiet_mode_reaches_v2_as_auto_publish_pause(monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(hybrid, "_process_panel_commands", lambda: 0)
    monkeypatch.setattr(hybrid, "run_ancillary_cycle", lambda now: 0)
    monkeypatch.setattr(
        hybrid.v13,
        "load_newsroom_settings",
        lambda: {
            "auto_publish": True,
            "emergency_lock": False,
            "quiet_mode": True,
            "quiet_start": "00:00",
            "quiet_end": "07:00",
        },
    )
    monkeypatch.setattr(hybrid.v13, "newsroom_publish_paused", lambda settings, now: True)

    def fake_v2_once(**kwargs):
        captured.update(kwargs)
        return {"published": 0, "telegram_writes": 0, "publish_failed": 0}

    monkeypatch.setattr(hybrid, "run_v2_once", fake_v2_once)
    monkeypatch.setattr(hybrid, "_record_runtime_heartbeat", lambda *args, **kwargs: None)

    hybrid.run_cycle(shadow=False, now=datetime(2026, 9, 10, 0, 30, tzinfo=timezone.utc))
    assert captured["settings"]["auto_publish"] is False


def test_main_newsroom_does_not_flash_raw_english_source_labels():
    template = Path("panel/templates/dashboard.html").read_text(encoding="utf-8")
    assert "item.source_display or item.source" not in template
    assert "<small>{{ item.source }}</small>" not in template


def test_newsroom_navigation_is_compact_visual_and_fully_persian():
    base = Path("panel/templates/base.html").read_text(encoding="utf-8")
    css = Path("panel/static/newsroom-nav-v2.css").read_text(encoding="utf-8")
    assert "newsroom-nav-item" in base
    assert "nav-icon" in base
    assert "nav-label" in base
    assert "COMMAND CENTER" not in base
    assert "اتاق خبر" in base
    assert "border-radius:999px" in css.replace(" ", "")
    assert "position:fixed" in css.replace(" ", "")
