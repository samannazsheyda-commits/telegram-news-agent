from __future__ import annotations

from unittest.mock import patch

from src.panel_command_router import NEWSROOM_ACTIONS, _apply_module


def test_preview_actions_are_supported_without_publishing():
    for action in ("weather_preview", "air_traffic_preview", "tanker_preview", "market_preview"):
        assert action in NEWSROOM_ACTIONS


def test_weather_preview_builds_and_saves_without_send(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    preview = {"message": "🌤️ پیش‌نمایش هوا", "generated_at": "now"}
    with patch("src.weather_digest.build_preview", return_value=preview) as build, patch("src.weather_digest.save_preview") as save:
        result = _apply_module({"action": "weather_preview", "command_id": "wp"})
    assert result["status"] == "succeeded"
    build.assert_called_once_with()
    assert save.call_count == 1


def test_air_tanker_and_market_preview_commands_do_not_publish(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cases = (
        ("air_traffic_preview", "src.air_traffic.build_air_traffic_preview"),
        ("tanker_preview", "src.panel_modules.build_hormuz_preview"),
        ("market_preview", "src.panel_modules.build_market_preview"),
    )
    for action, target in cases:
        with patch(target, return_value={"message": "پیش‌نمایش"}) as builder:
            result = _apply_module({"action": action, "command_id": action})
        assert result["status"] == "succeeded"
        builder.assert_called_once_with()
