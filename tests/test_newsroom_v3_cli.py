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


def test_v3_cli_has_no_canary_switch_before_live_shadow_validation(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["newsroom-v3", "--canary"])
    with pytest.raises(SystemExit):
        runtime.main()
