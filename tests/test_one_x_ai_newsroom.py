from __future__ import annotations

import pytest

from src.ai_newsroom import AIServiceError
from src.one_x_ai_newsroom import OneXAIConfig, OneXAINewsAI


class _FakeResponse:
    status_code = 200
    headers = {}
    text = ""

    def __init__(self, content: str = '{"text":"متن آزمایشی","faithful":true}'):
        self.content = content

    def json(self):
        return {
            "choices": [
                {
                    "message": {
                        "content": self.content
                    }
                }
            ]
        }


class _FakeSession:
    def __init__(self, content: str = '{"text":"متن آزمایشی","faithful":true}'):
        self.calls = []
        self.content = content

    def post(self, url, *, headers, json, timeout):
        self.calls.append(
            {
                "url": url,
                "headers": headers,
                "json": json,
                "timeout": timeout,
            }
        )
        return _FakeResponse(self.content)


class _SequenceFakeSession:
    def __init__(self, contents: list[str]):
        self.calls = []
        self.contents = list(contents)

    def post(self, url, *, headers, json, timeout):
        self.calls.append(
            {
                "url": url,
                "headers": headers,
                "json": json,
                "timeout": timeout,
            }
        )
        index = min(len(self.calls) - 1, len(self.contents) - 1)
        return _FakeResponse(self.contents[index])


def _config() -> OneXAIConfig:
    return OneXAIConfig(
        api_key="1xai-test-key",
        base_url="https://1xai.ir/v1",
        mode="required",
        model="gpt-5.6-luna",
        editorial_model="gpt-5.6-luna",
        persian_editor_model="gpt-5.6-luna",
        translation_model="gpt-5.6-luna",
    )


def test_one_x_ai_chat_uses_configured_openai_compatible_endpoint_and_luna_model():
    session = _FakeSession()
    ai = OneXAINewsAI(_config(), session=session)

    result = ai._chat_json(
        model="gpt-5.6-luna",
        system="Return JSON only.",
        user="Translate this news.",
        max_tokens=120,
    )

    assert result == {"text": "متن آزمایشی", "faithful": True}
    assert len(session.calls) == 1
    call = session.calls[0]
    assert call["url"] == "https://1xai.ir/v1/chat/completions"
    assert call["headers"]["Authorization"] == "Bearer 1xai-test-key"
    assert call["json"]["model"] == "gpt-5.6-luna"
    assert "temperature" not in call["json"]
    assert call["json"]["response_format"] == {"type": "json_object"}


def test_one_x_ai_accepts_one_json_object_wrapped_in_luna_prose():
    session = _FakeSession(
        'حتماً. خروجی JSON:\n{"summary":"ترافیک هوایی بر پایه داده زنده دریافت‌شده گزارش شده است."}\nپایان.'
    )
    ai = OneXAINewsAI(_config(), session=session)

    result = ai._chat_json(
        model="gpt-5.6-luna",
        system="Return JSON only.",
        user="Summarize live air traffic.",
        max_tokens=160,
    )

    assert result == {"summary": "ترافیک هوایی بر پایه داده زنده دریافت‌شده گزارش شده است."}


def test_one_x_ai_retries_once_when_luna_returns_plain_text_before_valid_json():
    session = _SequenceFakeSession(
        [
            "ترافیک هوایی منطقه در داده زنده پراکنده است.",
            '{"summary":"ترافیک هوایی منطقه در داده زنده پراکنده است."}',
        ]
    )
    ai = OneXAINewsAI(_config(), session=session)

    result = ai._chat_json(
        model="gpt-5.6-luna",
        system='Return JSON only: {"summary":"..."}.',
        user="Summarize live air traffic.",
        max_tokens=160,
    )

    assert result == {"summary": "ترافیک هوایی منطقه در داده زنده پراکنده است."}
    assert len(session.calls) == 2
    assert session.calls[1]["json"]["max_tokens"] >= 320
    assert "exactly one JSON object" in session.calls[1]["json"]["messages"][0]["content"]


def test_one_x_ai_rejects_multiple_json_objects_in_one_response():
    session = _FakeSession(
        '{"approve":true,"reason":"unique"}\n{"approve":false,"reason":"duplicate"}'
    )
    ai = OneXAINewsAI(_config(), session=session)

    with pytest.raises(AIServiceError, match="invalid_1xai_json"):
        ai._chat_json(
            model="gpt-5.6-luna",
            system="Return JSON only.",
            user="Judge this story.",
            max_tokens=160,
        )


def test_one_x_ai_rejects_response_without_a_json_object():
    session = _FakeSession("بله، این خبر مناسب انتشار است.")
    ai = OneXAINewsAI(_config(), session=session)

    with pytest.raises(AIServiceError, match="invalid_1xai_json"):
        ai._chat_json(
            model="gpt-5.6-luna",
            system="Return JSON only.",
            user="Judge this story.",
            max_tokens=160,
        )
