from __future__ import annotations

import pytest


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = ""

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError(f"status={self.status_code}", response=self)


def test_responses_api_uses_server_key_and_parses_output_text(monkeypatch):
    from panel.openai_luna import OpenAILunaClient

    seen = {}

    def fake_post(url, **kwargs):
        seen["url"] = url
        seen.update(kwargs)
        return FakeResponse(
            {
                "id": "resp_1",
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "سلام، انجامش می‌دم."}],
                    }
                ],
                "usage": {"input_tokens": 12, "output_tokens": 7},
            }
        )

    monkeypatch.setattr("panel.openai_luna.requests.post", fake_post)
    client = OpenAILunaClient(api_key="secret-test-key", fast_model="gpt-5.6-luna")
    response = client.create_response(input_items="سلام")

    assert seen["url"].endswith("/v1/responses")
    assert seen["headers"]["Authorization"] == "Bearer secret-test-key"
    assert seen["json"]["model"] == "gpt-5.6-luna"
    assert client.output_text(response) == "سلام، انجامش می‌دم."


def test_function_calls_are_extracted_from_responses_output(monkeypatch):
    from panel.openai_luna import OpenAILunaClient

    def fake_post(url, **kwargs):
        return FakeResponse(
            {
                "id": "resp_tools",
                "output": [
                    {
                        "type": "function_call",
                        "call_id": "call_1",
                        "name": "list_sources",
                        "arguments": '{"active":true}',
                    }
                ],
            }
        )

    monkeypatch.setattr("panel.openai_luna.requests.post", fake_post)
    client = OpenAILunaClient(api_key="k")
    response = client.create_response(input_items="منابع فعال رو نشون بده", tools=[])

    calls = client.function_calls(response)
    assert calls == [
        {"call_id": "call_1", "name": "list_sources", "arguments": {"active": True}}
    ]


def test_missing_api_key_fails_without_network(monkeypatch):
    from panel.openai_luna import LunaProviderError, OpenAILunaClient

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    client = OpenAILunaClient(api_key="")

    with pytest.raises(LunaProviderError) as exc:
        client.create_response(input_items="سلام")

    assert exc.value.code == "missing_api_key"


def test_transcription_posts_multipart_audio_and_returns_text(monkeypatch):
    from panel.openai_luna import OpenAILunaClient

    seen = {}

    def fake_post(url, **kwargs):
        seen["url"] = url
        seen.update(kwargs)
        return FakeResponse({"text": "این یک تست فارسی است", "usage": {"input_tokens": 5}})

    monkeypatch.setattr("panel.openai_luna.requests.post", fake_post)
    client = OpenAILunaClient(api_key="k", transcribe_model="gpt-transcribe")
    result = client.transcribe(b"voice-bytes", filename="voice.webm", mimetype="audio/webm")

    assert seen["url"].endswith("/v1/audio/transcriptions")
    assert seen["data"]["model"] == "gpt-transcribe"
    assert seen["files"]["file"][0] == "voice.webm"
    assert result["text"] == "این یک تست فارسی است"
