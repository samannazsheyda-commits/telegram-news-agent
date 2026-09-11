from __future__ import annotations

import json
import math
import os
import time
from dataclasses import dataclass
from typing import Any, Iterable

import requests


HF_CHAT_URL = "https://router.huggingface.co/v1/chat/completions"
HF_FEATURE_URL = "https://router.huggingface.co/hf-inference/models/{model}"
_ALLOWED_MODES = {"off", "optional", "required"}
_ALLOWED_RELATIONS = {"duplicate_same_event", "material_update", "different_event"}
_ALLOWED_PRIORITIES = {"critical", "high", "normal", "low"}
_TRANSIENT_HTTP_STATUSES = {408, 425, 429, 500, 502, 503, 504}


class AIServiceError(RuntimeError):
    """Raised when a newsroom AI backend cannot return a valid contract."""


@dataclass(frozen=True)
class AIConfig:
    token: str = ""
    mode: str = "optional"
    embedding_model: str = "BAAI/bge-m3"
    editorial_model: str = "Qwen/Qwen3-4B-Instruct-2507:fastest"
    persian_editor_model: str = "Qwen/Qwen3-4B-Instruct-2507:fastest"
    translation_model: str = "google/madlad400-3b-mt"
    madlad_endpoint: str = ""
    event_memory_hours: int = 72
    duplicate_threshold: float = 0.87
    importance_threshold: int = 70
    timeout_seconds: int = 25
    request_min_interval_ms: int = 500
    request_max_retries: int = 4

    @classmethod
    def from_env(cls) -> "AIConfig":
        mode = str(os.environ.get("AI_NEWSROOM_MODE", "optional") or "optional").strip().lower()
        if mode not in _ALLOWED_MODES:
            mode = "optional"
        return cls(
            token=str(os.environ.get("HF_TOKEN", "") or "").strip(),
            mode=mode,
            embedding_model=str(os.environ.get("HF_EMBEDDING_MODEL", "BAAI/bge-m3") or "BAAI/bge-m3").strip(),
            editorial_model=str(
                os.environ.get("HF_EDITORIAL_MODEL", "Qwen/Qwen3-4B-Instruct-2507:fastest")
                or "Qwen/Qwen3-4B-Instruct-2507:fastest"
            ).strip(),
            persian_editor_model=str(
                os.environ.get("HF_PERSIAN_EDITOR_MODEL", "Qwen/Qwen3-4B-Instruct-2507:fastest")
                or "Qwen/Qwen3-4B-Instruct-2507:fastest"
            ).strip(),
            translation_model=str(
                os.environ.get("HF_TRANSLATION_MODEL", "google/madlad400-3b-mt")
                or "google/madlad400-3b-mt"
            ).strip(),
            madlad_endpoint=str(os.environ.get("HF_MADLAD_ENDPOINT", "") or "").strip(),
            event_memory_hours=_env_int("AI_EVENT_MEMORY_HOURS", 72, minimum=1, maximum=720),
            duplicate_threshold=_env_float("AI_DUPLICATE_THRESHOLD", 0.87, minimum=0.0, maximum=1.0),
            importance_threshold=_env_int("AI_IMPORTANCE_THRESHOLD", 70, minimum=0, maximum=100),
            timeout_seconds=_env_int("AI_NEWSROOM_TIMEOUT_SECONDS", 25, minimum=5, maximum=120),
            request_min_interval_ms=_env_int("AI_REQUEST_MIN_INTERVAL_MS", 500, minimum=0, maximum=5000),
            request_max_retries=_env_int("AI_REQUEST_MAX_RETRIES", 4, minimum=0, maximum=8),
        )


@dataclass(frozen=True)
class EditorialDecision:
    importance: int
    topic: str
    publish: bool
    reason: str
    new_fact: bool
    priority_class: str


@dataclass(frozen=True)
class RelationDecision:
    relation: str
    confidence: float
    new_fact: bool
    reason: str


@dataclass(frozen=True)
class TranslationDraft:
    text: str
    backend: str
    faithful: bool = True


@dataclass(frozen=True)
class PersianEditDecision:
    text: str
    faithful: bool
    natural: bool
    reason: str


def _env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    try:
        value = int(str(os.environ.get(name, default)).strip())
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _env_float(name: str, default: float, *, minimum: float, maximum: float) -> float:
    try:
        value = float(str(os.environ.get(name, default)).strip())
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def cosine_similarity(left: Iterable[float], right: Iterable[float]) -> float:
    a = [float(value) for value in left]
    b = [float(value) for value in right]
    if not a or not b or len(a) != len(b):
        return 0.0
    left_norm = math.sqrt(sum(value * value for value in a))
    right_norm = math.sqrt(sum(value * value for value in b))
    if not left_norm or not right_norm:
        return 0.0
    return sum(x * y for x, y in zip(a, b)) / (left_norm * right_norm)


def _as_float_vector(value: Any) -> list[float]:
    if not isinstance(value, list) or not value:
        raise AIServiceError("invalid_embedding_vector")
    if all(isinstance(item, (int, float)) for item in value):
        return [float(item) for item in value]
    # Some feature-extraction providers return token embeddings. Mean-pool them.
    if all(isinstance(item, list) and item for item in value):
        rows = [_as_float_vector(item) for item in value]
        width = len(rows[0])
        if not width or any(len(row) != width for row in rows):
            raise AIServiceError("invalid_embedding_shape")
        return [sum(row[index] for row in rows) / len(rows) for index in range(width)]
    raise AIServiceError("invalid_embedding_vector")


def _clean_json_content(content: Any) -> dict[str, Any]:
    text = str(content or "").strip()
    if text.startswith("```json") and text.endswith("```"):
        text = text[7:-3].strip()
    elif text.startswith("```") and text.endswith("```"):
        text = text[3:-3].strip()
    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, TypeError) as exc:
        raise AIServiceError("invalid_ai_json") from exc
    if not isinstance(payload, dict):
        raise AIServiceError("invalid_ai_json_shape")
    return payload


class HuggingFaceNewsAI:
    """Remote Hugging Face inference facade for Bikhabar newsroom decisions."""

    def __init__(self, config: AIConfig | None = None, *, session=requests):
        self.config = config or AIConfig.from_env()
        self.session = session
        self._embedding_cache: dict[str, list[float]] = {}
        self._last_request_at = 0.0

    @property
    def available(self) -> bool:
        return bool(self.config.token) and self.config.mode != "off"

    def _headers(self) -> dict[str, str]:
        if not self.config.token:
            raise AIServiceError("missing_hf_token")
        return {
            "Authorization": f"Bearer {self.config.token}",
            "Content-Type": "application/json",
            "User-Agent": "BikhabarNewsroom/2.0",
        }

    def _throttle(self) -> None:
        minimum = max(0.0, float(self.config.request_min_interval_ms) / 1000.0)
        if minimum <= 0:
            return
        elapsed = time.monotonic() - self._last_request_at
        remaining = minimum - elapsed
        if remaining > 0:
            time.sleep(remaining)

    @staticmethod
    def _retry_after_seconds(response: Any, attempt: int) -> float:
        headers = getattr(response, "headers", {}) or {}
        raw = str(headers.get("Retry-After") or "").strip()
        if raw:
            try:
                return max(0.0, min(30.0, float(raw)))
            except ValueError:
                pass
        return min(8.0, 0.75 * (2 ** attempt))

    @staticmethod
    def _response_error_detail(response: Any) -> str:
        text = str(getattr(response, "text", "") or "").replace("\n", " ").strip()
        if not text:
            return ""
        return text[:180]

    def _post_json(self, url: str, payload: dict[str, Any], *, timeout: int | None = None) -> Any:
        retries = max(0, int(self.config.request_max_retries))
        request_timeout = timeout or self.config.timeout_seconds
        last_network_error: Exception | None = None

        for attempt in range(retries + 1):
            self._throttle()
            try:
                response = self.session.post(
                    url,
                    headers=self._headers(),
                    json=payload,
                    timeout=request_timeout,
                )
                self._last_request_at = time.monotonic()
            except AIServiceError:
                raise
            except requests.RequestException as exc:
                self._last_request_at = time.monotonic()
                last_network_error = exc
                if attempt < retries:
                    time.sleep(min(8.0, 0.75 * (2 ** attempt)))
                    continue
                raise AIServiceError(f"hf_network_error:{type(exc).__name__}") from exc
            except Exception as exc:
                self._last_request_at = time.monotonic()
                raise AIServiceError(f"hf_request_failed:{type(exc).__name__}") from exc

            status = int(getattr(response, "status_code", 200) or 200)
            if status >= 400:
                detail = self._response_error_detail(response)
                if status in _TRANSIENT_HTTP_STATUSES and attempt < retries:
                    time.sleep(self._retry_after_seconds(response, attempt))
                    continue
                suffix = f":{detail}" if detail else ""
                raise AIServiceError(f"hf_http_{status}{suffix}")

            try:
                return response.json()
            except Exception as exc:
                raise AIServiceError("hf_invalid_json_response") from exc

        if last_network_error is not None:
            raise AIServiceError(f"hf_network_error:{type(last_network_error).__name__}") from last_network_error
        raise AIServiceError("hf_request_exhausted")

    def _chat_json(self, *, model: str, system: str, user: str, max_tokens: int = 500) -> dict[str, Any]:
        payload = self._post_json(
            HF_CHAT_URL,
            {
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0,
                "max_tokens": max_tokens,
                "response_format": {"type": "json_object"},
            },
        )
        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise AIServiceError("invalid_chat_response") from exc
        return _clean_json_content(content)

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        cleaned = [str(text or "").strip() for text in texts]
        if not cleaned or any(not text for text in cleaned):
            raise AIServiceError("empty_embedding_input")

        missing = [text for text in cleaned if text not in self._embedding_cache]
        if missing:
            model = self.config.embedding_model.strip()
            url = HF_FEATURE_URL.format(model=model)
            payload = self._post_json(url, {"inputs": missing, "options": {"wait_for_model": True}})
            if not isinstance(payload, list):
                raise AIServiceError("invalid_embedding_response")

            # Batched providers normally return one vector (or token matrix) per input.
            if len(missing) == 1 and payload and all(isinstance(item, (int, float)) for item in payload):
                vectors = [_as_float_vector(payload)]
            elif len(payload) == len(missing):
                vectors = [_as_float_vector(item) for item in payload]
            else:
                raise AIServiceError("invalid_embedding_count")
            for text, vector in zip(missing, vectors):
                self._embedding_cache[text] = vector

        return [list(self._embedding_cache[text]) for text in cleaned]

    def score_story(self, source_text: str) -> EditorialDecision:
        source = str(source_text or "").strip()
        if not source:
            raise AIServiceError("empty_editorial_input")
        result = self._chat_json(
            model=self.config.editorial_model,
            system=(
                "You are the senior editor of Bikhabar, a Persian Iran-regional breaking-news monitor. "
                "Return JSON only. Score publication importance 0-100. Highest priority: missiles launched "
                "from Iran, missiles toward Iran, active direct attacks/war, operational Strait of Hormuz "
                "events, explosions, drone attacks/intercepts, warships, tankers/seizures/sinkings, nuclear "
                "operational developments, military/airspace operational changes. Routine diplomacy, phone "
                "calls, meetings, generic statements, analysis, warnings, threats, forecasts and repeated "
                "opinions are not automatic-publication material unless they contain a concrete new operational fact."
            ),
            user=(
                "Evaluate this source story. Required keys: importance (integer 0-100), topic (string), "
                "publish (boolean), reason (string), new_fact (boolean), priority_class "
                "(critical|high|normal|low).\n\nSOURCE:\n" + source
            ),
        )
        try:
            importance = int(result["importance"])
            topic = str(result["topic"]).strip()
            publish = result["publish"]
            reason = str(result["reason"]).strip()
            new_fact = result["new_fact"]
            priority_class = str(result["priority_class"]).strip().lower()
        except (KeyError, TypeError, ValueError) as exc:
            raise AIServiceError("invalid_editorial_contract") from exc
        if not isinstance(publish, bool) or not isinstance(new_fact, bool):
            raise AIServiceError("invalid_editorial_flags")
        if not 0 <= importance <= 100 or not topic or priority_class not in _ALLOWED_PRIORITIES:
            raise AIServiceError("invalid_editorial_values")
        return EditorialDecision(importance, topic, publish, reason, new_fact, priority_class)

    def judge_relation(self, new_text: str, prior_text: str) -> RelationDecision:
        new_value = str(new_text or "").strip()
        prior_value = str(prior_text or "").strip()
        if not new_value or not prior_value:
            raise AIServiceError("empty_relation_input")
        result = self._chat_json(
            model=self.config.editorial_model,
            system=(
                "You compare two news reports at event level. Return JSON only. Decide whether the new report "
                "is the same event/claim, a material update with a concrete new fact, or a different event. "
                "Do not call a new attack, launch, strike, closure, seizure, casualty change or other concrete "
                "operational development a duplicate merely because actors/locations overlap."
            ),
            user=(
                "Required keys: relation (duplicate_same_event|material_update|different_event), confidence "
                "(0-1 number), new_fact (boolean), reason (string).\n\nNEW:\n"
                + new_value
                + "\n\nPRIOR:\n"
                + prior_value
            ),
        )
        try:
            relation = str(result["relation"]).strip()
            confidence = float(result["confidence"])
            new_fact = result["new_fact"]
            reason = str(result["reason"]).strip()
        except (KeyError, TypeError, ValueError) as exc:
            raise AIServiceError("invalid_relation_contract") from exc
        if relation not in _ALLOWED_RELATIONS or not isinstance(new_fact, bool) or not 0.0 <= confidence <= 1.0:
            raise AIServiceError("invalid_relation_values")
        return RelationDecision(relation, confidence, new_fact, reason)

    def translate_to_fa(self, source_text: str) -> TranslationDraft:
        source = str(source_text or "").strip()
        if not source:
            raise AIServiceError("empty_translation_input")

        if self.config.madlad_endpoint:
            payload = self._post_json(
                self.config.madlad_endpoint,
                {
                    "inputs": f"<2fa> {source}",
                    "parameters": {"max_new_tokens": 700},
                    "options": {"wait_for_model": True},
                },
                timeout=max(self.config.timeout_seconds, 45),
            )
            text = ""
            if isinstance(payload, list) and payload and isinstance(payload[0], dict):
                text = str(payload[0].get("generated_text") or payload[0].get("translation_text") or "").strip()
            elif isinstance(payload, dict):
                text = str(payload.get("generated_text") or payload.get("translation_text") or "").strip()
            if not text:
                raise AIServiceError("invalid_madlad_response")
            return TranslationDraft(text=text, backend="madlad", faithful=True)

        result = self._chat_json(
            model=self.config.editorial_model,
            system=(
                "Translate news copy from English to natural professional Persian. Do not summarize, add, "
                "omit, speculate, editorialize or alter actors, actions, numbers, dates, places or attribution. "
                "Return JSON only."
            ),
            user=(
                "Required keys: text (Persian string), faithful (boolean). Translate exactly this source:\n\n" + source
            ),
            max_tokens=900,
        )
        text = str(result.get("text") or "").strip()
        faithful = result.get("faithful")
        if not text or faithful is not True:
            raise AIServiceError("invalid_qwen_translation")
        return TranslationDraft(text=text, backend="qwen_fallback", faithful=True)

    def edit_persian(self, source_text: str, draft_text: str) -> PersianEditDecision:
        source = str(source_text or "").strip()
        draft = str(draft_text or "").strip()
        if not source or not draft:
            raise AIServiceError("empty_persian_edit_input")
        result = self._chat_json(
            model=self.config.persian_editor_model,
            system=(
                "You are a senior Persian wire-service copy editor. Rewrite the Persian draft into concise, "
                "natural journalistic Persian while checking every fact against the original source. Never add "
                "background, change attribution, reverse who acted on whom, or change names, numbers, dates or "
                "locations. Fix literal machine translation and awkward grammar. Return JSON only."
            ),
            user=(
                "Required keys: text (string), faithful (boolean), natural (boolean), reason (string).\n\n"
                "ORIGINAL SOURCE:\n"
                + source
                + "\n\nPERSIAN DRAFT:\n"
                + draft
            ),
            max_tokens=900,
        )
        text = str(result.get("text") or "").strip()
        faithful = result.get("faithful")
        natural = result.get("natural")
        reason = str(result.get("reason") or "").strip()
        if not text or not isinstance(faithful, bool) or not isinstance(natural, bool):
            raise AIServiceError("invalid_persian_edit_contract")
        return PersianEditDecision(text=text, faithful=faithful, natural=natural, reason=reason)