from __future__ import annotations

import json
from datetime import datetime, timezone

from src import newsroom_hybrid_runtime as runtime


def test_record_runtime_heartbeat_preserves_state_and_records_cycle(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "state.json").write_text(json.dumps({"news_seen": ["a"]}), encoding="utf-8")
    now = datetime(2026, 9, 9, 15, 30, tzinfo=timezone.utc)

    runtime._record_runtime_heartbeat({"rc": 0, "published": 2, "telegram_writes": 1}, now=now)

    state = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert state["news_seen"] == ["a"]
    assert state["last_cycle_at"] == now.isoformat()
    assert state["last_cycle_rc"] == 0
    assert state["last_cycle_published"] == 2
    assert state["last_cycle_telegram_writes"] == 1


def test_shadow_cycle_does_not_write_production_heartbeat(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(runtime, "run_ancillary_cycle", lambda now: 0)
    monkeypatch.setattr(runtime.v13, "load_newsroom_settings", lambda: {})
    monkeypatch.setattr(runtime, "run_v2_once", lambda **kwargs: {"published": 0, "telegram_writes": 0})

    runtime.run_cycle(shadow=True, now=datetime(2026, 9, 9, tzinfo=timezone.utc))

    assert not (tmp_path / "state.json").exists()
