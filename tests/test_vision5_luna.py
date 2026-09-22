from __future__ import annotations

import json

import pytest


class LunaStore:
    def __init__(self):
        self.saved = []
        self.audits = []
        self.translations = []

    def get_story(self, story_id):
        return {
            "id": story_id,
            "source": "Reuters",
            "original_title": "Original",
            "original_text": "Original body",
            "google_title": "تیتر گوگل",
            "google_body": "متن گوگل",
            "status": "READY_FOR_REVIEW",
        }

    def list_newsroom_rules(self):
        return [{"rule_key": "tone", "rule_json": {"value": "رسمی و روشن"}}]

    def get_luna_conversation(self, user_id):
        return {"messages": [{"role": "user", "content": "قبلی"}], "context": {}}

    def save_luna_conversation(self, user_id, *, messages, context):
        self.saved.append((user_id, messages, context))

    def record_operator_audit(self, *, actor, action, entity_type, entity_id, status, detail):
        self.audits.append((actor, action, entity_type, entity_id, status, detail))

    def record_translation(self, story_id, *, provider, title, body, actor):
        self.translations.append((story_id, provider, title, body, actor))
        return {"id": story_id, "status": "LUNA_TRANSLATED", "luna_title": title, "luna_body": body}


class Model:
    def __init__(self, response="پاسخ لونا"):
        self.response = response
        self.calls = []

    def respond(self, *, instructions, input_items, tools=None):
        self.calls.append({"instructions": instructions, "input_items": input_items, "tools": tools})
        return {"text": self.response, "response_id": "resp-1", "usage": {"total_tokens": 120}}

    def translate(self, *, title, body, target_language):
        return {"title": "تیتر لونا", "body": "متن لونا"}


def test_luna_chat_includes_story_rules_and_memory_and_persists_audit():
    from bikhabar_v5.luna import LunaOperator

    store = LunaStore()
    model = Model()
    result = LunaOperator(store=store, model=model).chat(
        user_id="editor", message="این خبر را بررسی کن", story_id="story-1"
    )

    assert result["text"] == "پاسخ لونا"
    encoded = json.dumps(model.calls[0]["input_items"], ensure_ascii=False)
    assert "تیتر گوگل" in encoded
    assert "رسمی و روشن" in encoded
    assert "قبلی" in encoded
    assert store.saved[-1][0] == "editor"
    assert store.audits[-1][1] == "luna_chat"


def test_luna_alternate_translation_is_explicit_and_audited():
    from bikhabar_v5.luna import LunaOperator

    store = LunaStore()
    result = LunaOperator(store=store, model=Model()).alternate_translation(
        story_id="story-1", actor="editor"
    )

    assert result["status"] == "LUNA_TRANSLATED"
    assert store.translations == [
        ("story-1", "luna", "تیتر لونا", "متن لونا", "editor")
    ]


def test_permission_gate_binds_confirmation_to_exact_action_and_payload():
    from bikhabar_v5.permissions import PermissionDenied, PermissionGate

    gate = PermissionGate(secret="test-secret", ttl_seconds=300, clock=lambda: 1000)
    token = gate.issue(actor="editor", action="deploy", payload={"branch": "luna/change-1"})

    assert gate.verify(
        token, actor="editor", action="deploy", payload={"branch": "luna/change-1"}
    )["action"] == "deploy"
    with pytest.raises(PermissionDenied):
        gate.verify(token, actor="editor", action="deploy", payload={"branch": "main"})


class BuilderAdapter:
    def __init__(self):
        self.calls = []

    def create_branch(self, branch):
        self.calls.append(("branch", branch))

    def apply_patch(self, branch, patch):
        self.calls.append(("patch", branch, patch))

    def run_tests(self, branch):
        self.calls.append(("tests", branch))
        return {"passed": True, "summary": "42 passed"}

    def create_preview(self, branch):
        self.calls.append(("preview", branch))
        return "https://preview.example.test/change-1"

    def deploy(self, branch):
        self.calls.append(("deploy", branch))
        return {"deployment": "dep-1"}


def test_builder_runs_branch_patch_tests_preview_then_requires_confirmed_deploy():
    from bikhabar_v5.builder import BuilderWorkflow
    from bikhabar_v5.permissions import PermissionGate

    adapter = BuilderAdapter()
    gate = PermissionGate(secret="test-secret", ttl_seconds=300, clock=lambda: 1000)
    workflow = BuilderWorkflow(adapter=adapter, permission_gate=gate)
    prepared = workflow.prepare(
        change_id="change-1", patch="diff --git a/a b/a", actor="editor"
    )

    assert prepared["phase"] == "preview_ready"
    assert prepared["tests"]["passed"] is True
    assert prepared["preview_url"].startswith("https://preview")
    assert all(call[0] != "deploy" for call in adapter.calls)

    deployed = workflow.deploy(
        branch=prepared["branch"], actor="editor", confirmation_token=prepared["confirmation_token"]
    )
    assert deployed["phase"] == "deployed"
    assert adapter.calls[-1] == ("deploy", prepared["branch"])


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload
        self.status_code = 200

    def json(self):
        return self.payload

    def raise_for_status(self):
        return None


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def post(self, url, *, headers, json, timeout):
        self.calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return self.response


def test_openai_responses_client_uses_official_responses_contract_and_extracts_text():
    from bikhabar_v5.openai_client import OpenAIResponsesClient

    session = FakeSession(
        FakeResponse(
            {
                "id": "resp-9",
                "output": [
                    {"type": "reasoning", "id": "r1"},
                    {"type": "message", "content": [{"type": "output_text", "text": "پاسخ نهایی"}]},
                ],
                "usage": {"total_tokens": 50},
            }
        )
    )
    client = OpenAIResponsesClient(api_key="key", model="gpt-test", session=session)
    result = client.respond(instructions="قواعد", input_items=[{"role": "user", "content": "سلام"}])

    assert result["text"] == "پاسخ نهایی"
    assert session.calls[0]["url"].endswith("/v1/responses")
    assert session.calls[0]["json"]["store"] is False
    assert session.calls[0]["json"]["model"] == "gpt-test"


class AudioSession:
    def __init__(self):
        self.calls = []

    def post(self, url, *, headers, files, data, timeout):
        self.calls.append(
            {"url": url, "headers": headers, "files": files, "data": data, "timeout": timeout}
        )
        return FakeResponse({"text": "این خبر را خلاصه کن"})


def test_openai_audio_transcriber_accepts_voice_bytes_without_persisting_them():
    from bikhabar_v5.openai_client import OpenAIAudioTranscriber

    session = AudioSession()
    transcript = OpenAIAudioTranscriber(api_key="key", session=session).transcribe(
        audio=b"voice-bytes", filename="voice.ogg", content_type="audio/ogg"
    )

    assert transcript == "این خبر را خلاصه کن"
    assert session.calls[0]["url"].endswith("/v1/audio/transcriptions")
    assert session.calls[0]["data"]["model"] == "gpt-4o-mini-transcribe"
