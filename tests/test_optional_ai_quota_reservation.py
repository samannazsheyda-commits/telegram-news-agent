from types import SimpleNamespace

import src.newsroom_runtime_v2 as runtime
from src.newsroom_v2 import CycleSummary


class FakeAI:
    available = True


def _patch_provider_config(monkeypatch, *, mode: str):
    monkeypatch.setattr(
        runtime.OpenRouterConfig,
        "from_env",
        classmethod(lambda cls: SimpleNamespace(mode=mode, api_key="test-key")),
    )
    monkeypatch.setattr(
        runtime.GroqConfig,
        "from_env",
        classmethod(lambda cls: SimpleNamespace(mode="off", api_key="")),
    )
    monkeypatch.setattr(
        runtime.AIConfig,
        "from_env",
        classmethod(lambda cls: SimpleNamespace(mode="off", token="")),
    )


def test_decision_ai_is_reserved_in_optional_mode_but_kept_in_required_mode():
    ai = FakeAI()
    assert runtime._decision_ai_for_newsroom(ai, "optional") is None
    assert runtime._decision_ai_for_newsroom(ai, "off") is None
    assert runtime._decision_ai_for_newsroom(ai, "required") is ai


def test_run_once_keeps_optional_ai_for_publisher_but_not_newsroom_decisions(tmp_path, monkeypatch):
    _patch_provider_config(monkeypatch, mode="optional")
    ai = FakeAI()
    monkeypatch.setattr(runtime, "LocalFirstOpenRouterNewsAI", lambda config: ai)

    captured = {}

    def fake_run_cycle(*args, **kwargs):
        captured["decision_ai"] = kwargs.get("ai")
        return CycleSummary()

    monkeypatch.setattr(runtime, "run_cycle", fake_run_cycle)

    result = runtime.run_once(
        shadow=False,
        fetchers=[],
        publisher=lambda item: {"ok": True, "message_id": 1},
        data_dir=tmp_path,
    )

    assert captured["decision_ai"] is None
    assert result["ai_provider"] == "openrouter"
    assert result["ai_newsroom_mode"] == "optional"
    assert result["ai_available"] is True


def test_run_once_keeps_remote_decision_ai_in_required_mode(tmp_path, monkeypatch):
    _patch_provider_config(monkeypatch, mode="required")
    ai = FakeAI()
    monkeypatch.setattr(runtime, "LocalFirstOpenRouterNewsAI", lambda config: ai)

    captured = {}

    def fake_run_cycle(*args, **kwargs):
        captured["decision_ai"] = kwargs.get("ai")
        return CycleSummary()

    monkeypatch.setattr(runtime, "run_cycle", fake_run_cycle)

    runtime.run_once(
        shadow=False,
        fetchers=[],
        publisher=lambda item: {"ok": True, "message_id": 1},
        data_dir=tmp_path,
    )

    assert captured["decision_ai"] is ai
