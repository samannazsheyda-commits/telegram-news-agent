from __future__ import annotations

import time

from panel.openai_luna import LunaProviderError
from tests.test_luna_v5_operator import ScriptedClient, _chat, _seed_v5_story, env  # noqa: F401


def test_simple_command_never_invokes_complex_model(env):
    fake = env["use"]([{"calls": [("list_sources", {})]}, {"text": "یک منبع داریم."}])
    _chat(env, "منابع رو نشون بده")
    assert {request["model"] for request in fake.requests} == {"fast-model"}


def test_duplicate_tool_calls_add_no_executor_latency(env, monkeypatch):
    from panel.luna_tools import LunaToolbox

    original = LunaToolbox.execute
    sleeps = []

    def slow_execute(self, name, args=None, *, confirmed=False):
        sleeps.append(name)
        time.sleep(0.05)
        return original(self, name, args, confirmed=confirmed)

    monkeypatch.setattr(LunaToolbox, "execute", slow_execute)
    env["use"]([
        {"calls": [("list_sources", {}), ("list_sources", {})]},
        {"calls": [("list_sources", {})]},
        {"text": "یک منبع."},
    ])
    started = time.monotonic()
    _chat(env, "منابع")
    assert sleeps == ["list_sources"]
    assert time.monotonic() - started < 0.5


def test_final_answer_after_read_uses_exactly_two_model_rounds(env):
    fake = env["use"]([{"calls": [("list_sources", {})]}, {"text": "یک منبع."}, {"text": "never used"}])
    _chat(env, "منابع")
    assert len(fake.requests) == 2


def test_direct_answer_uses_one_model_round(env):
    fake = env["use"]([{"text": "سلام!"}])
    _chat(env, "سلام")
    assert len(fake.requests) == 1


def test_confirmation_proposal_stops_without_extra_model_round(env):
    fake = env["use"]([{"calls": [("delete_source", {"query": "ClashReports"})]}, {"text": "never used"}])
    _chat(env, "کلش رو حذف کن")
    assert len(fake.requests) == 1


def test_provider_timeout_is_concise_retryable_and_keeps_context(env, monkeypatch):
    _seed_v5_story(env["store"])
    env["client"].post("/api/v5/luna/context/story/st1")

    class TimeoutClient(ScriptedClient):
        def create_response(self, **kwargs):
            raise LunaProviderError("provider_timeout", "Luna الان جواب نداد؛ دوباره بفرست.", retryable=True)

    monkeypatch.setattr("panel.luna_operator_api.get_luna_client", lambda: TimeoutClient([]))
    response = env["client"].post("/api/panel/luna/operator-chat", json={"message": "همین خبر رو خلاصه کن"})
    body = response.get_json()
    assert response.status_code == 503
    assert body["retryable"] is True
    assert body["reply_fa"] and len(body["reply_fa"]) < 120
    history = env["client"].get("/api/panel/luna/operator-history").get_json()
    assert history["context"]["story"]["id"] == "st1"

    fake = env["use"]([{"calls": [("get_story", {})]}, {"text": ""}])
    retried = _chat(env, "همین خبر رو خلاصه کن")
    assert "حمله پهپادی" in retried["reply_fa"]
    assert fake.requests[0]["input_items"][-1]["content"][0]["text"] == "همین خبر رو خلاصه کن"
