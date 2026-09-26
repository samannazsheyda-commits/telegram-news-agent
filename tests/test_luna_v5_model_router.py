from __future__ import annotations

from types import SimpleNamespace

import pytest

from panel.luna_model_router import ModelRoute, model_for, route_turn


@pytest.mark.parametrize("message", [
    "منابع رو نشون بده",
    "وضعیت اتاق خبر؟",
    "اسم کلش رو فارسی کن",
    "همینو منتشر کن",
    "تیترشو کوتاه‌تر کن",
    "صدای آلارم رو خاموش کن",
    "سلام",
])
def test_routine_reads_and_commands_use_fast_model(message):
    assert route_turn(message).tier == "fast"


@pytest.mark.parametrize("message", [
    "این خبرها رو با هم مقایسه کن",
    "یک تحلیل از روند امروز بده",
    "این خبر ارزش انتشار داره؟",
    "جمع‌بندی همه خبرهای امروز",
    "اعتبار منبع این خبر رو بررسی کن",
    "بررسی دقیق کن چرا انتشار متوقف شد",
    "Please analyze today's coverage",
])
def test_editorial_reasoning_and_synthesis_use_complex_model(message):
    assert route_turn(message).tier == "complex"


def test_image_analysis_is_complex():
    assert route_turn("این چیه؟", has_image=True) == ModelRoute("complex", "image_analysis")


def test_long_request_is_complex():
    assert route_turn("خبر " * 150).tier == "complex"


def test_routing_is_deterministic():
    assert {route_turn("منابع رو نشون بده") for _ in range(20)} == {ModelRoute("fast", "routine")}


def test_model_for_uses_configured_models_and_falls_back_to_fast():
    both = SimpleNamespace(fast_model="fast", complex_model="deep")
    fast_only = SimpleNamespace(fast_model="fast")
    assert model_for(both, ModelRoute("fast", "routine")) == "fast"
    assert model_for(both, ModelRoute("complex", "editorial_reasoning")) == "deep"
    assert model_for(fast_only, ModelRoute("complex", "editorial_reasoning")) == "fast"


def test_model_names_are_not_part_of_the_chat_payload(monkeypatch, tmp_path):
    from tests.test_luna_v5_operator import ScriptedClient, MemoryData
    from panel.app_v5 import create_app
    from panel.luna_operator_api import bp
    from src.newsroom_v5_store import NewsroomV5Store

    app = create_app({
        "TESTING": True, "WTF_CSRF_ENABLED": False, "SECRET_KEY": "t", "PANEL_PASSWORD_HASH": "x",
        "DATA_BACKEND": MemoryData(), "NEWSROOM_V5_STORE": NewsroomV5Store(tmp_path / "v5.db"),
    })
    app.register_blueprint(bp)
    fake = ScriptedClient([{"text": "تحلیل: روند آرام است."}])
    monkeypatch.setattr("panel.luna_operator_api.get_luna_client", lambda: fake)
    client = app.test_client()
    with client.session_transaction() as session:
        session["admin"] = True
    body = client.post("/api/panel/luna/operator-chat", json={"message": "یک تحلیل از روند امروز بده"}).get_data(as_text=True)
    assert fake.requests[0]["model"] == "complex-model"
    assert "complex-model" not in body and "fast-model" not in body
