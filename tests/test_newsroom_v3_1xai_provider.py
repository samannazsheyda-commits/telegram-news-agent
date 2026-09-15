from __future__ import annotations

import src.newsroom_v3.canary as canary_module


def _provider_names(publisher) -> list[str]:
    providers = getattr(getattr(publisher, "ai", None), "_providers", [])
    return [name for name, _provider in providers]


def test_build_production_publisher_uses_1xai_when_openai_key_is_configured(monkeypatch):
    monkeypatch.setenv("AI_NEWSROOM_MODE", "required")
    monkeypatch.setenv("OPENAI_API_KEY", "1xai-test")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://1xai.ir/v1")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-5.6-luna")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("HF_TOKEN", raising=False)

    publisher = canary_module.build_production_publisher().publisher

    assert _provider_names(publisher) == ["1xai"]


def test_build_production_publisher_keeps_existing_providers_after_1xai(monkeypatch):
    monkeypatch.setenv("AI_NEWSROOM_MODE", "required")
    monkeypatch.setenv("OPENAI_API_KEY", "1xai-test")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://1xai.ir/v1")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-5.6-luna")
    monkeypatch.setenv("OPENROUTER_API_KEY", "openrouter-test")
    monkeypatch.setenv("GROQ_API_KEY", "groq-test")
    monkeypatch.setenv("HF_TOKEN", "hf-test")

    publisher = canary_module.build_production_publisher().publisher

    assert _provider_names(publisher) == ["1xai", "openrouter", "groq", "huggingface"]
