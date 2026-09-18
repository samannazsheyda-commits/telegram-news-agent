from __future__ import annotations

import json
from pathlib import Path

from panel.audit_log import append_audit, list_audit
from panel.luna_assistant import handle_control_message
from src.local_json_repository import LocalJsonRepository


def _write(root: Path, relative: str, value) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def test_quota_command_updates_real_setting_and_audits(tmp_path):
    _write(tmp_path, "data/newsroom_settings.json", {"daily_quota": 35, "special_quota": 5})
    data = LocalJsonRepository(tmp_path)

    result = handle_control_message(data, "سهمیه امروز رو از ۳۵ بکن ۴۰")

    assert result["intent"] == "update_daily_quota"
    assert result["status"] == "succeeded"
    assert result["value"] == 40
    settings, _ = data.read_json("data/newsroom_settings.json", {})
    assert settings["daily_quota"] == 40
    audit = list_audit(data, limit=1)
    assert audit[0]["actor"] == "luna"
    assert audit[0]["action"] == "update_daily_quota"
    assert audit[0]["before"]["daily_quota"] == 35
    assert audit[0]["after"]["daily_quota"] == 40


def test_diagnostic_question_reads_current_snapshot_context(tmp_path):
    _write(tmp_path, "data/newsroom_settings.json", {"daily_quota": 35, "special_quota": 5})
    _write(
        tmp_path,
        "data/newsroom_v3_production_status.json",
        {"daily_limit": 35, "daily_published": 12, "waiting": 42, "ready": 2, "reason": "no_safe_candidate"},
    )
    _write(tmp_path, "state.json", {})
    data = LocalJsonRepository(tmp_path)

    result = handle_control_message(data, "چرا امروز خبر کم منتشر شده؟")

    assert result["intent"] == "diagnose_silence"
    assert result["status"] == "succeeded"
    assert "۱۲" in result["reply_fa"] or "12" in result["reply_fa"]
    assert "۲۳" in result["reply_fa"] or "23" in result["reply_fa"]
    assert "کاندید" in result["reply_fa"] or "candidate" in result["reply_fa"].lower()


def test_unknown_message_is_read_only_luna_chat_request(tmp_path):
    data = LocalJsonRepository(tmp_path)

    result = handle_control_message(data, "از وضعیت امروز یک جمع‌بندی سردبیری بهم بده")

    assert result["intent"] == "assistant_chat"
    assert result["status"] == "needs_luna"
    assert result["requires_confirmation"] is False
    assert result["message"] == "از وضعیت امروز یک جمع‌بندی سردبیری بهم بده"


def test_audit_log_keeps_required_fields(tmp_path):
    data = LocalJsonRepository(tmp_path)
    append_audit(
        data,
        actor="user",
        action="publish_final",
        target="story-1",
        before={"status": "pending"},
        after={"status": "published_manual"},
        result="ok",
    )
    row = list_audit(data, limit=1)[0]
    assert {"timestamp", "actor", "action", "target", "before", "after", "result"} <= set(row)
