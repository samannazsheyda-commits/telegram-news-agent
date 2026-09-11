import json

import pytest

from src.ai_newsroom import (
    AIConfig,
    AIServiceError,
    HuggingFaceNewsAI,
    cosine_similarity,
)


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")

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
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def test_config_defaults_and_env(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "hf_test")
    monkeypatch.setenv("AI_NEWSROOM_MODE", "required")
    cfg = AIConfig.from_env()
    assert cfg.token == "hf_test"
    assert cfg.mode == "required"
    assert cfg.event_memory_hours == 72
    assert cfg.duplicate_threshold == pytest.approx(0.87)
    assert cfg.importance_threshold == 70
    assert cfg.embedding_model == "BAAI/bge-m3"
    assert cfg.editorial_model.startswith("Qwen/Qwen3-4B-Instruct-2507")


def test_cosine_similarity_is_deterministic():
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)
    assert cosine_similarity([], []) == 0.0


def test_embed_texts_parses_hf_inference_vectors():
    cfg = AIConfig(token="hf_test")
    session = FakeSession([FakeResponse([[1.0, 0.0], [0.5, 0.5]])])
    ai = HuggingFaceNewsAI(cfg, session=session)
    vectors = ai.embed_texts(["alpha", "beta"])
    assert vectors == [[1.0, 0.0], [0.5, 0.5]]
    url, kwargs = session.calls[0]
    assert url == "https://router.huggingface.co/hf-inference/models/BAAI/bge-m3"
    assert kwargs["headers"]["Authorization"] == "Bearer hf_test"
    assert kwargs["json"]["inputs"] == ["alpha", "beta"]


def test_score_story_parses_json_only_chat_response():
    payload = {
        "choices": [{
            "message": {
                "content": json.dumps({
                    "importance": 91,
                    "topic": "missile_attack",
                    "publish": True,
                    "reason": "active kinetic event",
                    "new_fact": True,
                    "priority_class": "critical",
                })
            }
        }]
    }
    ai = HuggingFaceNewsAI(AIConfig(token="hf_test"), session=FakeSession([FakeResponse(payload)]))
    decision = ai.score_story("Iran launched missiles toward Israel")
    assert decision.importance == 91
    assert decision.publish is True
    assert decision.new_fact is True
    assert decision.priority_class == "critical"


def test_score_story_rejects_malformed_json():
    payload = {"choices": [{"message": {"content": "not-json"}}]}
    ai = HuggingFaceNewsAI(AIConfig(token="hf_test"), session=FakeSession([FakeResponse(payload)]))
    with pytest.raises(AIServiceError):
        ai.score_story("some story")


def test_relation_judge_contract():
    payload = {
        "choices": [{"message": {"content": json.dumps({
            "relation": "duplicate_same_event",
            "confidence": 0.95,
            "new_fact": False,
            "reason": "same event from another source",
        })}}]
    }
    ai = HuggingFaceNewsAI(AIConfig(token="hf_test"), session=FakeSession([FakeResponse(payload)]))
    result = ai.judge_relation("new paraphrase", "prior event")
    assert result.relation == "duplicate_same_event"
    assert result.confidence == pytest.approx(0.95)
    assert result.new_fact is False


def test_madlad_endpoint_is_preferred_when_configured():
    cfg = AIConfig(token="hf_test", madlad_endpoint="https://madlad.example/infer")
    session = FakeSession([FakeResponse([{"generated_text": "ترجمه دقیق"}])])
    ai = HuggingFaceNewsAI(cfg, session=session)
    draft = ai.translate_to_fa("The airport was hit by airstrikes")
    assert draft.text == "ترجمه دقیق"
    assert draft.backend == "madlad"
    url, kwargs = session.calls[0]
    assert url == "https://madlad.example/infer"
    assert kwargs["json"]["inputs"].startswith("<2fa> ")


def test_qwen_translation_is_fallback_without_madlad_endpoint():
    payload = {"choices": [{"message": {"content": json.dumps({
        "text": "فرودگاه هدف حملات هوایی قرار گرفت",
        "faithful": True,
    })}}]}
    ai = HuggingFaceNewsAI(AIConfig(token="hf_test"), session=FakeSession([FakeResponse(payload)]))
    draft = ai.translate_to_fa("The airport was hit by airstrikes")
    assert draft.backend == "qwen_fallback"
    assert "فرودگاه" in draft.text


def test_persian_editor_requires_faithful_and_natural_flags():
    payload = {"choices": [{"message": {"content": json.dumps({
        "text": "عربستان سعودی فرودگاه المخا در یمن را هدف حملات هوایی قرار داده است.",
        "faithful": True,
        "natural": True,
        "reason": "",
    })}}]}
    ai = HuggingFaceNewsAI(AIConfig(token="hf_test"), session=FakeSession([FakeResponse(payload)]))
    edit = ai.edit_persian(
        "Saudi airstrikes hit Mokha airport in Yemen.",
        "حملات هوایی عربستان فرودگاه موخا را زده است.",
    )
    assert edit.faithful is True
    assert edit.natural is True
    assert "هدف حملات هوایی" in edit.text
