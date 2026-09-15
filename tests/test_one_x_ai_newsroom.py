from __future__ import annotations

from src.one_x_ai_newsroom import OneXAIConfig, OneXAINewsAI


class _FakeResponse:
    status_code = 200
    headers = {}
    text = ""

    def json(self):
        return {
            "choices": [
                {
                    "message": {
                        "content": '{"text":"متن آزمایشی","faithful":true}'
                    }
                }
            ]
        }


class _FakeSession:
    def __init__(self):
        self.calls = []

    def post(self, url, *, headers, json, timeout):
        self.calls.append(
            {
                "url": url,
                "headers": headers,
                "json": json,
                "timeout": timeout,
            }
        )
        return _FakeResponse()


def test_one_x_ai_chat_uses_configured_openai_compatible_endpoint_and_luna_model():
    session = _FakeSession()
    config = OneXAIConfig(
        api_key="1xai-test-key",
        base_url="https://1xai.ir/v1",
        mode="required",
        model="gpt-5.6-luna",
        editorial_model="gpt-5.6-luna",
        persian_editor_model="gpt-5.6-luna",
        translation_model="gpt-5.6-luna",
    )
    ai = OneXAINewsAI(config, session=session)

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
