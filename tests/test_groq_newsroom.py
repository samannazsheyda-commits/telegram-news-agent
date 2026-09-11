import json

import pytest

from src.ai_newsroom import AIConfig, AIServiceError
from src.groq_newsroom_ai import GroqNewsAI, LocalFirstGroqNewsAI


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
            "importance": 94,
            "topic": "missile_attack",
            "publish": True,
            "reason": "active kinetic event",
            "new_fact": True,
            "priority_class": "critical",
        })}}]
    }


def test_config_reads_groq_credentials_and_qwen36_model(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    monkeypatch.setenv("GROQ_MODEL", "qwen/qwen3.6-27b")
    monkeypatch.setenv("AI_NEWSROOM_MODE", "required")
    cfg = AIConfig.from_env()
    assert cfg.groq_api_key == "gsk_test"
    assert cfg.groq_model == "qwen/qwen3.6-27b"
    assert cfg.mode == "required"


def test_groq_editor_uses_openai_compatible_endpoint_and_json_mode():
    session = FakeSession([FakeResponse(editorial_payload())])
    cfg = AIConfig(
        groq_api_key="gsk_test",
        groq_model="qwen/qwen3.6-27b",
        mode="required",
        request_min_interval_ms=0,
    )
    ai = GroqNewsAI(cfg, session=session)
    decision = ai.score_story("Iran launched missiles toward Israel")
    assert decision.publish is True
    url, kwargs = session.calls[0]
    assert url == "https://api.groq.com/openai/v1/chat/completions"
    assert kwargs["headers"]["Authorization"] == "Bearer gsk_test"
    assert kwargs["json"]["model"] == "qwen/qwen3.6-27b"
    assert kwargs["json"]["response_format"] == {"type": "json_object"}


def test_local_first_groq_never_calls_remote_embedding_endpoint():
    ai = LocalFirstGroqNewsAI(
        AIConfig(groq_api_key="gsk_test", mode="required", request_min_interval_ms=0),
        session=FakeSession([]),
    )
    vectors = ai.embed_texts([
        "Iran launched ballistic missiles toward Israel overnight",
        "Iran fired ballistic missiles toward Israel overnight",
    ])
    assert len(vectors) == 2
    assert len(vectors[0]) == len(vectors[1])


def test_groq_errors_are_provider_specific_and_fail_closed():
    session = FakeSession([FakeResponse({"error": "rate limit"}, status_code=429)])
    cfg = AIConfig(
        groq_api_key="gsk_test",
        mode="required",
        request_min_interval_ms=0,
        request_max_retries=0,
    )
    ai = GroqNewsAI(cfg, session=session)
    with pytest.raises(AIServiceError, match="groq_http_429"):
        ai.score_story("Iran launched missiles toward Israel")
