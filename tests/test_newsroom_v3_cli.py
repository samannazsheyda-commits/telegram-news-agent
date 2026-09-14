from __future__ import annotations

import json
import sys

import pytest

from src.newsroom_v3 import runtime


def test_v3_module_entrypoint_is_shadow_only_by_default(monkeypatch, capsys, tmp_path):
    calls = []

    def fake_run_once(**kwargs):
        calls.append(kwargs)
        return {"mode": "shadow", "telegram_writes": 0, "processed": 3}

    monkeypatch.setattr(runtime, "run_once", fake_run_once)
    monkeypatch.setattr(sys, "argv", ["newsroom-v3", "--data-dir", str(tmp_path)])

    assert runtime.main() == 0
    assert calls == [{"data_dir": str(tmp_path), "shadow": True}]
    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "shadow"
    assert payload["telegram_writes"] == 0


def test_v3_cli_atomically_writes_status_file_and_still_prints_json(monkeypatch, capsys, tmp_path):
    result = {
        "mode": "shadow",
        "sources_ok": 6,
        "sources_failed": 0,
        "processed": 171,
        "ready": 4,
        "waiting": 2,
        "rejected": 160,
        "duplicates": 5,
        "telegram_writes": 0,
        "story_ids": ["story-1"],
        "publish_results": [],
    }
    monkeypatch.setattr(runtime, "run_once", lambda **kwargs: result)
    status_path = tmp_path / "newsroom_v3_shadow_status.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "newsroom-v3",
            "--data-dir",
            str(tmp_path),
            "--status-file",
            str(status_path),
        ],
    )

    assert runtime.main() == 0
    assert json.loads(status_path.read_text(encoding="utf-8")) == result
    assert json.loads(capsys.readouterr().out) == result
    assert list(tmp_path.glob(".newsroom_v3_shadow_status.json.*")) == []


def test_atomic_status_write_preserves_previous_valid_file_if_replace_fails(monkeypatch, tmp_path):
    status_path = tmp_path / "newsroom_v3_shadow_status.json"
    previous = {"mode": "shadow", "telegram_writes": 0, "processed": 10}
    status_path.write_text(json.dumps(previous), encoding="utf-8")

    def fail_replace(*args, **kwargs):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(runtime.os, "replace", fail_replace)

    with pytest.raises(OSError, match="replace failure"):
        runtime._atomic_write_json(status_path, {"mode": "shadow", "processed": 11})

    assert json.loads(status_path.read_text(encoding="utf-8")) == previous
    assert list(tmp_path.glob(".newsroom_v3_shadow_status.json.*")) == []


def test_v3_cli_has_no_canary_switch_before_live_shadow_validation(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["newsroom-v3", "--canary"])
    with pytest.raises(SystemExit):
        runtime.main()
