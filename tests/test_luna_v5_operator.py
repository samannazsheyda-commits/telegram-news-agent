from __future__ import annotations

from copy import deepcopy

import pytest

from panel.app_v5 import create_app
from panel.luna_capabilities import build_capability_registry
from panel.luna_operator_api import bp as luna_operator_bp
from panel.luna_tools import LunaToolbox
from src.newsroom_v5_store import NewsroomV5Store


class MemoryData:
    def __init__(self):
        self.mapping = {
            "data/panel_pending_actions.json": [],
            "data/panel_audit_log.json": [],
            "data/panel_live_feed.json": [],
            "data/editorial_queue.json": [],
            "data/editorial_history.json": [],
            "data/custom_sources.json": [
                {"id": "src-clash", "kind": "x", "name": "ClashReports", "handle": "ClashReports", "active": True},
            ],
            "data/source_overrides.json": {},
            "data/panel_settings.json": {"newsroom_alarm_enabled": True},
            "state.json": {},
        }

    def read_json(self, path, default):
        return deepcopy(self.mapping.get(path, default)), "sha"

    def write_json(self, path, value, sha, message):
        self.mapping[path] = deepcopy(value)
        return {"sha": "next"}


class ScriptedClient:
    """Fake provider: each create_response returns the next scripted step."""

    fast_model = "fast-model"
    complex_model = "complex-model"

    def __init__(self, steps):
        self.steps = list(steps)
        self.requests = []

    def create_response(self, **kwargs):
        self.requests.append(kwargs)
        step = self.steps.pop(0) if self.steps else {"text": ""}
        return {"output": [], **step}

    def function_calls(self, response):
        return [
            {"name": name, "arguments": dict(args), "call_id": f"call-{index}"}
            for index, (name, args) in enumerate(response.get("calls") or [])
        ]

    def output_text(self, response):
        return str(response.get("text") or "")


@pytest.fixture
def env(monkeypatch, tmp_path):
    data = MemoryData()
    store = NewsroomV5Store(tmp_path / "v5.db")
    app = create_app({
        "TESTING": True, "WTF_CSRF_ENABLED": False, "SECRET_KEY": "test", "PANEL_PASSWORD_HASH": "x",
        "DATA_BACKEND": data, "NEWSROOM_V5_STORE": store,
    })
    app.register_blueprint(luna_operator_bp)
    monkeypatch.setenv("LUNA_CONVERSATION_PATH", str(tmp_path / "conversation.json"))
    client = app.test_client()
    with client.session_transaction() as session:
        session["admin"] = True

    calls = []
    original = LunaToolbox.execute

    def counting_execute(self, name, args=None, *, confirmed=False):
        calls.append((name, dict(args or {})))
        return original(self, name, args, confirmed=confirmed)

    monkeypatch.setattr(LunaToolbox, "execute", counting_execute)

    def use(steps):
        fake = ScriptedClient(steps)
        monkeypatch.setattr("panel.luna_operator_api.get_luna_client", lambda: fake)
        return fake

    return {"app": app, "client": client, "data": data, "store": store, "calls": calls, "use": use}


def _chat(env, message):
    response = env["client"].post("/api/panel/luna/operator-chat", json={"message": message})
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()


def _seed_v5_story(store, story_id="st1", title="حمله پهپادی به بندر در جنوب خلیج فارس گزارش شد"):
    store.upsert_story({
        "id": story_id, "news_key": story_id, "source_id": "reuters", "source_name": "Reuters",
        "source_url": f"https://example.test/{story_id}", "original_title": "Drone strike reported at southern Gulf port",
        "published_at_source": "2026-09-20T10:00:00+00:00", "state": "review",
    })
    store.set_translation(story_id, title_fa=title, body_fa="جزئیات بیشتر", backend="t", quality_passed=True)


def test_identical_tool_call_in_one_turn_executes_once(env):
    env["use"]([
        {"calls": [("list_sources", {})]},
        {"calls": [("list_sources", {})]},
        {"text": "یک منبع فعال داریم: ClashReports."},
    ])
    payload = _chat(env, "منابع رو نشون بده")
    assert [name for name, _ in env["calls"]].count("list_sources") == 1
    assert payload["reply_fa"] == "یک منبع فعال داریم: ClashReports."


def test_identical_calls_in_the_same_round_execute_once(env):
    env["use"]([
        {"calls": [("list_sources", {"query": "clash"}), ("list_sources", {"query": "clash"})]},
        {"text": "ClashReports پیدا شد."},
    ])
    _chat(env, "کلش رو پیدا کن")
    assert [name for name, _ in env["calls"]].count("list_sources") == 1


def test_different_arguments_execute_separately(env):
    env["use"]([
        {"calls": [("list_sources", {"query": "clash"})]},
        {"calls": [("list_sources", {"kind": "x"})]},
        {"text": "انجام شد"},
    ])
    _chat(env, "دو جست‌وجو")
    assert [args for name, args in env["calls"] if name == "list_sources"] == [{"query": "clash"}, {"kind": "x"}]


def test_repeat_in_a_new_turn_executes_again(env):
    env["use"]([{"calls": [("list_sources", {})]}, {"text": "یک منبع."}])
    _chat(env, "منابع")
    env["use"]([{"calls": [("list_sources", {})]}, {"text": "یک منبع."}])
    _chat(env, "دوباره منابع")
    assert [name for name, _ in env["calls"]].count("list_sources") == 2


def test_read_request_returns_content_even_if_model_final_text_is_empty(env):
    env["use"]([{"calls": [("list_sources", {})]}, {"text": ""}])
    payload = _chat(env, "منابع فعال کدوم‌ها هستن؟")
    assert "ClashReports" in payload["reply_fa"]
    assert payload["reply_fa"] not in {"انجام شد.", "عملیات با موفقیت اجرا شد."}


def test_normal_chat_payload_has_no_internal_tool_events(env):
    env["use"]([{"calls": [("list_sources", {})]}, {"text": "یک منبع داریم."}])
    payload = _chat(env, "منابع")
    assert "tool_events" not in payload
    assert "list_sources" not in str(payload)


def test_confirmed_mutation_answers_with_short_natural_acknowledgement(env):
    env["use"]([{"calls": [("rename_source", {"query": "ClashReports", "display_name": "کلش ریپورتز"})]}])
    proposal = _chat(env, "اسم کلش رو فارسی کن")
    assert proposal["confirmation_required"] is True
    assert env["data"].mapping["data/custom_sources.json"][0]["name"] == "ClashReports"

    confirmed = env["client"].post(f"/api/panel/luna/operator-confirm/{proposal['action_id']}")
    body = confirmed.get_json()
    assert confirmed.status_code == 200
    assert body["reply_fa"] == "چشم، انجام شد."
    assert env["data"].mapping["data/custom_sources.json"][0]["name"] == "کلش ریپورتز"


@pytest.mark.parametrize("name", [
    "publish_story", "delete_source", "rename_source", "set_newsroom_alarm", "builder_prepare",
    "reject_and_block_story", "edit_story_copy", "add_source", "disable_source",
])
def test_sensitive_mutations_require_confirmation(name):
    capability = build_capability_registry().get(name)
    assert capability.mutates and capability.requires_confirmation


@pytest.mark.parametrize("name", [
    "list_sources", "get_story", "search_stories", "diagnose_newsroom", "inspect_panel_state", "builder_ci_status",
])
def test_reads_and_analysis_do_not_require_confirmation(name):
    capability = build_capability_registry().get(name)
    assert not capability.mutates and not capability.requires_confirmation


def test_model_requested_delete_is_only_proposed_not_executed(env):
    env["use"]([{"calls": [("delete_source", {"query": "ClashReports"})]}])
    payload = _chat(env, "کلش رو حذف کن")
    assert payload["confirmation_required"] is True
    assert env["data"].mapping["data/custom_sources.json"][0]["id"] == "src-clash"


def test_executor_failure_is_never_reported_as_success(env):
    env["use"]([{"calls": [("get_story", {"story_id": "missing"})]}, {"text": "چشم، انجام شد."}])
    payload = _chat(env, "خبر رو بیار")
    assert "انجام شد" not in payload["reply_fa"]
    assert "پیدا نشد" in payload["reply_fa"]


def test_failed_confirmation_does_not_acknowledge_success(env):
    env["use"]([{"calls": [("rename_source", {"query": "ClashReports", "display_name": "کلش"})]}])
    proposal = _chat(env, "اسم کلش رو عوض کن")
    env["data"].mapping["data/custom_sources.json"][0]["name"] = "Changed meanwhile"
    confirmed = env["client"].post(f"/api/panel/luna/operator-confirm/{proposal['action_id']}")
    assert confirmed.status_code == 409
    assert "چشم" not in confirmed.get_json().get("reply_fa", "")


def test_this_story_reference_resolves_to_structured_context(env):
    _seed_v5_story(env["store"])
    env["client"].post("/api/v5/luna/context/story/st1")
    fake = env["use"]([{"calls": [("get_story", {})]}, {"text": ""}])
    payload = _chat(env, "همین خبر رو خلاصه بگو")
    assert ("get_story", {"story_id": "st1"}) in env["calls"]
    assert "حمله پهپادی" in payload["reply_fa"]
    user_turn = fake.requests[0]["input_items"][-1]
    assert user_turn["content"][0]["text"] == "همین خبر رو خلاصه بگو"


def test_context_handoff_validates_story_and_does_not_create_chat_message(env, tmp_path):
    _seed_v5_story(env["store"])
    missing = env["client"].post("/api/v5/luna/context/story/nope")
    assert missing.status_code == 404
    ok = env["client"].post("/api/v5/luna/context/story/st1")
    assert ok.status_code == 200
    assert ok.get_json()["story"]["title_fa"].startswith("حمله پهپادی")
    history = env["client"].get("/api/panel/luna/operator-history").get_json()
    assert history["messages"] == []
    assert history["context"]["story"]["id"] == "st1"


def test_shorten_headline_after_handoff_targets_selected_story(env):
    _seed_v5_story(env["store"])
    env["client"].post("/api/v5/luna/context/story/st1")
    fake = env["use"]([
        {"calls": [("get_story", {})]},
        {"calls": [("edit_story_copy", {"title_fa": "حمله پهپادی به بندر جنوبی"})]},
    ])
    proposal = _chat(env, "تیترشو کوتاه‌تر کن")
    assert "حمله پهپادی به بندر جنوبی" in proposal["summary_fa"]
    assert "Drone strike" not in fake.requests[0]["input_items"][-1]["content"][0]["text"]
    assert env["store"].get_story("st1")["title_fa"].startswith("حمله پهپادی به بندر در جنوب")

    confirmed = env["client"].post(f"/api/panel/luna/operator-confirm/{proposal['action_id']}")
    assert confirmed.status_code == 200
    assert env["store"].get_story("st1")["title_fa"] == "حمله پهپادی به بندر جنوبی"
    assert env["store"].get_story("st1")["state"] == "review"


def test_double_confirm_executes_once(env):
    _seed_v5_story(env["store"])
    env["client"].post("/api/v5/luna/context/story/st1")
    env["use"]([{"calls": [("reject_and_block_story", {})]}])
    proposal = _chat(env, "این خبر رو رد کن")
    first = env["client"].post(f"/api/panel/luna/operator-confirm/{proposal['action_id']}")
    second = env["client"].post(f"/api/panel/luna/operator-confirm/{proposal['action_id']}")
    assert first.status_code == 200
    assert second.status_code in {404, 409}
    assert env["store"].get_story("st1")["state"] == "rejected"
    rejections = env["store"].conn.execute(
        "SELECT COUNT(*) FROM audit_log WHERE action='story_rejected'").fetchone()[0]
    assert rejections == 1


def test_expired_confirmation_is_refused(env):
    env["use"]([{"calls": [("rename_source", {"query": "ClashReports", "display_name": "کلش"})]}])
    proposal = _chat(env, "اسم کلش رو عوض کن")
    rows = env["data"].mapping["data/panel_pending_actions.json"]
    rows[0]["expires_at"] = "2000-01-01T00:00:00+00:00"
    expired = env["client"].post(f"/api/panel/luna/operator-confirm/{proposal['action_id']}")
    assert expired.status_code == 410
    assert env["data"].mapping["data/custom_sources.json"][0]["name"] == "ClashReports"


def test_v5_publish_through_luna_uses_idempotent_outbox(env):
    _seed_v5_story(env["store"])
    env["client"].post("/api/v5/luna/context/story/st1")
    env["use"]([{"calls": [("publish_story", {"copy_mode": "machine"})]}])
    proposal = _chat(env, "همینو منتشر کن")
    assert proposal["confirmation_required"] is True
    assert env["store"].get_story("st1")["state"] == "review"
    confirmed = env["client"].post(f"/api/panel/luna/operator-confirm/{proposal['action_id']}")
    assert confirmed.status_code == 200
    assert env["store"].get_story("st1")["state"] == "publishing"
    assert env["store"].conn.execute("SELECT COUNT(*) FROM publications").fetchone()[0] == 1
