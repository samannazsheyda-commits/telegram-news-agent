from __future__ import annotations

import json
import sys

import pytest

from src.newsroom_v3 import canary
from src.newsroom_v3.publisher_adapter import V3TelegramPublisherAdapter
from src.strict_translation import StrictTelegramNewsroomPublisher


def test_default_canary_publisher_uses_existing_strict_guarded_publisher(monkeypatch):
    monkeypatch.setenv("AI_NEWSROOM_MODE", "optional")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "@bikhabaar")
    monkeypatch.setenv("OFFLINE_TRANSLATION_ENABLED", "0")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("HF_TOKEN", raising=False)

    publisher = canary.build_production_publisher()

    assert isinstance(publisher, V3TelegramPublisherAdapter)
    assert isinstance(publisher.publisher, StrictTelegramNewsroomPublisher)
    assert publisher.publisher.ai_mode == "required"
    assert publisher.publisher.offline_translation_enabled is False


def test_canary_cli_has_no_publish_path_without_explicit_confirmation(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["newsroom-v3-canary", "--data-dir", "/tmp/unused"])
    with pytest.raises(SystemExit):
        canary.main()


def test_canary_cli_runs_exactly_one_shot_when_explicitly_confirmed(monkeypatch, capsys, tmp_path):
    calls = []
    fake_publisher = object()
    monkeypatch.setattr(canary, "build_production_publisher", lambda: fake_publisher)

    def fake_run(**kwargs):
        calls.append(kwargs)
        return {"state": "published", "telegram_writes": 1, "telegram_message_id": 77}

    monkeypatch.setattr(canary, "run_one_shot_canary", fake_run)
    monkeypatch.setattr(
        sys,
        "argv",
        ["newsroom-v3-canary", "--data-dir", str(tmp_path), "--confirm-one-shot"],
    )

    assert canary.main() == 0
    assert calls == [{"data_dir": str(tmp_path), "publisher": fake_publisher}]
    payload = json.loads(capsys.readouterr().out)
    assert payload["telegram_writes"] == 1
