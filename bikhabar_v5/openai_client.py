from __future__ import annotations

import json
from typing import Any

import requests


class OpenAIResponseError(RuntimeError):
    pass


class OpenAIResponsesClient:
    endpoint = "https://api.openai.com/v1/responses"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        session: Any | None = None,
        timeout_seconds: float = 60,
    ) -> None:
        self.api_key = str(api_key or "").strip()
        self.model = str(model or "").strip()
        if not self.api_key or not self.model:
            raise ValueError("OpenAI api_key and model are required")
        self.session = session or requests.Session()
        self.timeout_seconds = max(5.0, float(timeout_seconds))

    def respond(
        self,
        *,
        instructions: str,
        input_items: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        text_format: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.model,
            "instructions": instructions,
            "input": input_items,
            "store": False,
        }
        if tools:
            body["tools"] = tools
        if text_format:
            body["text"] = {"format": text_format}
        response = self.session.post(
            self.endpoint,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        texts: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        for item in payload.get("output") or []:
            if item.get("type") == "message":
                texts.extend(
                    str(part.get("text") or "")
                    for part in item.get("content") or []
                    if part.get("type") == "output_text"
                )
            elif item.get("type") == "function_call":
                tool_calls.append(
                    {
                        "call_id": item.get("call_id"),
                        "name": item.get("name"),
                        "arguments": item.get("arguments") or "{}",
                    }
                )
        text = "\n".join(value for value in texts if value).strip()
        if not text and not tool_calls:
            raise OpenAIResponseError("OpenAI response contained no text or tool call")
        return {
            "text": text,
            "tool_calls": tool_calls,
            "response_id": payload.get("id"),
            "usage": dict(payload.get("usage") or {}),
        }

    def translate(self, *, title: str, body: str, target_language: str) -> dict[str, str]:
        schema = {
            "type": "json_schema",
            "name": "translated_news_copy",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {"title": {"type": "string"}, "body": {"type": "string"}},
                "required": ["title", "body"],
                "additionalProperties": False,
            },
        }
        result = self.respond(
            instructions=(
                f"Translate the supplied newsroom copy into {target_language}. Preserve names, "
                "numbers and factual meaning. Return only the requested structured fields."
            ),
            input_items=[
                {
                    "role": "user",
                    "content": json.dumps({"title": title, "body": body}, ensure_ascii=False),
                }
            ],
            text_format=schema,
        )
        try:
            translated = json.loads(result["text"])
            return {"title": str(translated["title"]), "body": str(translated["body"])}
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise OpenAIResponseError("OpenAI returned invalid structured translation") from exc


class OpenAIAudioTranscriber:
    endpoint = "https://api.openai.com/v1/audio/transcriptions"

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "gpt-4o-mini-transcribe",
        session: Any | None = None,
        timeout_seconds: float = 90,
    ) -> None:
        self.api_key = str(api_key or "").strip()
        self.model = str(model or "").strip()
        if not self.api_key or not self.model:
            raise ValueError("OpenAI api_key and transcription model are required")
        self.session = session or requests.Session()
        self.timeout_seconds = max(5.0, float(timeout_seconds))

    def transcribe(self, *, audio: bytes, filename: str, content_type: str) -> str:
        if not audio:
            raise ValueError("voice audio is empty")
        response = self.session.post(
            self.endpoint,
            headers={"Authorization": f"Bearer {self.api_key}"},
            files={"file": (filename or "voice.ogg", audio, content_type or "audio/ogg")},
            data={"model": self.model, "language": "fa", "response_format": "json"},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        text = str((response.json() or {}).get("text") or "").strip()
        if not text:
            raise OpenAIResponseError("OpenAI transcription returned no text")
        return text
