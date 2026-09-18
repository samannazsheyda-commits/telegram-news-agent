from __future__ import annotations

import json
import os
from dataclasses import dataclass

import requests


OPENAI_BASE_URL = "https://api.openai.com"


@dataclass
class LunaProviderError(RuntimeError):
    code: str
    message_fa: str
    retryable: bool = False
    status_code: int | None = None

    def __str__(self) -> str:
        return self.message_fa


class OpenAILunaClient:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        fast_model: str | None = None,
        complex_model: str | None = None,
        transcribe_model: str | None = None,
        timeout: int = 45,
        base_url: str | None = None,
    ) -> None:
        self.api_key = str(api_key if api_key is not None else os.environ.get("OPENAI_API_KEY", "")).strip()
        self.fast_model = str(fast_model or os.environ.get("LUNA_MODEL_FAST") or "gpt-5.6-luna").strip()
        self.complex_model = str(complex_model or os.environ.get("LUNA_MODEL_COMPLEX") or "gpt-5.6-terra").strip()
        self.transcribe_model = str(transcribe_model or os.environ.get("LUNA_TRANSCRIBE_MODEL") or "gpt-transcribe").strip()
        self.timeout = max(5, int(timeout))
        self.base_url = str(base_url or os.environ.get("OPENAI_BASE_URL") or OPENAI_BASE_URL).rstrip("/")

    @property
    def connected(self) -> bool:
        return bool(self.api_key)

    def _auth_headers(self, *, json_content: bool = True) -> dict[str, str]:
        if not self.api_key:
            raise LunaProviderError("missing_api_key", "Luna متصل نیست؛ کلید OpenAI روی سرور تنظیم نشده است.")
        headers = {"Authorization": f"Bearer {self.api_key}"}
        if json_content:
            headers["Content-Type"] = "application/json"
        return headers

    def _map_http_error(self, exc: requests.HTTPError) -> LunaProviderError:
        response = getattr(exc, "response", None)
        status = int(getattr(response, "status_code", 0) or 0) or None
        if status == 429:
            return LunaProviderError("rate_limited", "Luna موقتاً به سقف درخواست API رسیده؛ کمی بعد دوباره امتحان کن.", True, status)
        if status is not None and status >= 500:
            return LunaProviderError("provider_unavailable", "سرویس Luna موقتاً در دسترس نیست؛ دوباره تلاش کن.", True, status)
        return LunaProviderError("provider_error", "ارتباط Luna با OpenAI ناموفق بود.", False, status)

    def create_response(
        self,
        *,
        input_items,
        tools: list[dict] | None = None,
        model: str | None = None,
        instructions: str | None = None,
        reasoning_effort: str | None = None,
        previous_response_id: str | None = None,
        text_format: dict | None = None,
    ) -> dict:
        payload: dict = {
            "model": str(model or self.fast_model),
            "input": input_items,
            "store": False,
        }
        if tools is not None:
            payload["tools"] = tools
        if instructions:
            payload["instructions"] = instructions
        if reasoning_effort:
            payload["reasoning"] = {"effort": reasoning_effort}
        if previous_response_id:
            payload["previous_response_id"] = str(previous_response_id)
        if text_format:
            payload["text"] = {"format": text_format}
        try:
            response = requests.post(
                f"{self.base_url}/v1/responses",
                headers=self._auth_headers(),
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
            value = response.json()
        except requests.Timeout as exc:
            raise LunaProviderError("timeout", "پاسخ Luna طول کشید؛ دوباره تلاش کن.", True) from exc
        except requests.HTTPError as exc:
            raise self._map_http_error(exc) from exc
        except (requests.RequestException, ValueError) as exc:
            raise LunaProviderError("provider_error", "ارتباط Luna با OpenAI ناموفق بود.", True) from exc
        if not isinstance(value, dict):
            raise LunaProviderError("invalid_response", "پاسخ Luna معتبر نبود.", True)
        return value

    @staticmethod
    def output_text(response: dict) -> str:
        if not isinstance(response, dict):
            return ""
        direct = response.get("output_text")
        if isinstance(direct, str) and direct.strip():
            return direct.strip()
        chunks: list[str] = []
        for item in response.get("output") or []:
            if not isinstance(item, dict) or item.get("type") != "message":
                continue
            for part in item.get("content") or []:
                if not isinstance(part, dict):
                    continue
                if part.get("type") in {"output_text", "text"} and isinstance(part.get("text"), str):
                    chunks.append(part["text"])
        return "\n".join(chunk.strip() for chunk in chunks if chunk.strip()).strip()

    @staticmethod
    def function_calls(response: dict) -> list[dict]:
        calls: list[dict] = []
        if not isinstance(response, dict):
            return calls
        for item in response.get("output") or []:
            if not isinstance(item, dict) or item.get("type") != "function_call":
                continue
            raw_args = item.get("arguments")
            try:
                arguments = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args or {})
            except (ValueError, TypeError):
                arguments = {}
            calls.append(
                {
                    "call_id": str(item.get("call_id") or ""),
                    "name": str(item.get("name") or ""),
                    "arguments": arguments if isinstance(arguments, dict) else {},
                }
            )
        return calls

    @staticmethod
    def usage(response: dict) -> dict:
        raw = response.get("usage") if isinstance(response, dict) else {}
        raw = raw if isinstance(raw, dict) else {}
        details = raw.get("input_tokens_details") if isinstance(raw.get("input_tokens_details"), dict) else {}
        return {
            "input_tokens": int(raw.get("input_tokens") or 0),
            "output_tokens": int(raw.get("output_tokens") or 0),
            "cached_input_tokens": int(details.get("cached_tokens") or 0),
        }

    def transcribe(self, content: bytes, *, filename: str, mimetype: str) -> dict:
        if not isinstance(content, (bytes, bytearray)) or not content:
            raise LunaProviderError("empty_audio", "فایل صوتی خالی است.")
        try:
            response = requests.post(
                f"{self.base_url}/v1/audio/transcriptions",
                headers=self._auth_headers(json_content=False),
                data={"model": self.transcribe_model, "response_format": "json"},
                files={"file": (filename, bytes(content), mimetype)},
                timeout=max(self.timeout, 60),
            )
            response.raise_for_status()
            value = response.json()
        except requests.Timeout as exc:
            raise LunaProviderError("timeout", "تبدیل ویس به متن طول کشید؛ دوباره تلاش کن.", True) from exc
        except requests.HTTPError as exc:
            raise self._map_http_error(exc) from exc
        except (requests.RequestException, ValueError) as exc:
            raise LunaProviderError("provider_error", "تبدیل ویس به متن ناموفق بود.", True) from exc
        if not isinstance(value, dict) or not str(value.get("text") or "").strip():
            raise LunaProviderError("invalid_transcription", "متنی از این ویس دریافت نشد.", True)
        return value


def get_luna_client() -> OpenAILunaClient:
    return OpenAILunaClient()
