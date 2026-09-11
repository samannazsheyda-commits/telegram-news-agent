import json

import pytest

from src.ai_newsroom import AIServiceError
from src.openrouter_newsroom_ai import (
    OpenRouterConfig,
    OpenRouterNewsAI,
    LocalFirstOpenRouterNewsAI,
)


class FakeResponse:
    def __init__(self, payload, status_code=200, headers=None):
        self._payload = payload
        self.status_code = status_code
        self.headers = dict(headers or {})
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if not self.responses:
            raise AssertionError("unexpected HTTP call")
        return self.responses.pop(0)


def editorial_payload():
    return {
        "choices": [{"message": {"content": json.dumps({
            "importance": 95,
            "topic": "missile_attack",
            "publish": True,
            "reason": "active kinetic event",
            "new_fact": True,
            "priority_class": "critical",
        })}}]
    }


def test_config_reads_openrouter_credentials_and_free_qwen_model(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-test")
    monkeypatch.setenv("OPENROUTER_MODEL", "qwen/qwen3-235b-a22b-2507:free")
    monkeypatch.setenv("AI_NEWSROOM_MODE", "required")
    cfg = OpenRouterConfig.from_env()
    assert cfg.api_key == "sk-or-v1-test"
    assert cfg.model == "qwen/qwen3-235b-a22b-2507:free"
    assert cfg.mode == "required"


def test_openrouter_editor_uses_openai_endpoint_and_json_mode():
    session = FakeSession([FakeResponse(editorial_payload())])
    cfg = OpenRouterConfig(
        api_key="sk-or-v1-test",
        model="qwen/qwen3-235b-a22b-2507:free",
        editorial_model="qwen/qwen3-235b-a22b-2507:free",
        persian_editor_model="qwen/qwen3-235b-a22b-2507:free",
        translation_model="qwen/qwen3-235b-a22b-2507:free",
        mode="required",
        request_min_interval_ms=0,
    )
    ai = OpenRouterNewsAI(cfg, session=session)
    decision = ai.score_story("Iran launched missiles toward Israel")
    assert decision.publish is True
    url, kwargs = session.calls[0]
    assert url == "https://openrouter.ai/api/v1/chat/completions"
    assert kwargs["headers"]["Authorization"] == "Bearer sk-or-v1-test"
    assert kwargs["headers"]["X-Title"] == "Bikhabar Newsroom"
    assert kwargs["json"]["model"] == "qwen/qwen3-235b-a22b-2507:free"
    assert kwargs["json"]["response_format"] == {"type": "json_object"}


def test_local_first_openrouter_never_calls_remote_embedding_endpoint():
    ai = LocalFirstOpenRouterNewsAI(
        OpenRouterConfig(api_key="sk-or-v1-test", mode="required", request_min_interval_ms=0),
        session=FakeSession([]),
    )
    vectors = ai.embed_texts([
        "Iran launched ballistic missiles toward Israel overnight",
        "Iran fired ballistic missiles toward Israel overnight",
    ])
    assert len(vectors) == 2
    assert len(vectors[0]) == len(vectors[1])


def test_openrouter_errors_are_provider_specific_and_fail_closed():
    session = FakeSession([FakeResponse({"error": "rate limit"}, status_code=429)])
    cfg = OpenRouterConfig(
        api_key="sk-or-v1-test",
        mode="required",
        request_min_interval_ms=0,
        request_max_retries=0,
    )
    ai = OpenRouterNewsAI(cfg, session=session)
    with pytest.raises(AIServiceError, match="openrouter_http_429"):
        ai.score_story("Iran launched missiles toward Israel")
