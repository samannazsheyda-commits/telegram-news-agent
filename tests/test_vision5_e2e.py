from __future__ import annotations

import json

import pytest


class Store:
    def __init__(self):
        self.story = None
        self.events = []

    def upsert_source(self, source):
        return {"id": "source-1", **source}

    def ingest_story(self, story):
        self.story = {**story, "id": "story-1", "status": "NEW"}
        return self.story, True

    def transition_story(self, story_id, target, *, actor, detail=None):
        self.story["status"] = target
        self.events.append(target)
        return self.story

    def record_translation(self, story_id, *, provider, title, body, actor):
        self.story.update({"google_title": title, "google_body": body, "status": "GOOGLE_TRANSLATED"})
        return self.story

    def save_review(self, story_id, *, title, body, copy_mode, actor, approve):
        self.story.update({"final_title": title, "final_body": body, "status": "APPROVED"})
        return self.story


class Translator:
    def translate_google(self, story):
        return {"title": "تیتر تست نهایی", "body": "متن تست نهایی", "provider": "google"}


class Publisher:
    def __init__(self):
        self.calls = []

    def publish(self, story_id, *, actor):
        self.calls.append((story_id, actor))
        return {"id": story_id, "status": "PUBLISHED", "telegram_message_id": 700}


def test_e2e_harness_requires_exact_live_target_confirmation_and_writes_evidence(tmp_path):
    from bikhabar_v5.e2e import E2ERunner, LiveTargetConfirmationError

    runner = E2ERunner(
        store=Store(),
        translator=Translator(),
        publisher=Publisher(),
        telegram_chat_id="@approved",
        evidence_root=tmp_path,
    )
    with pytest.raises(LiveTargetConfirmationError):
        runner.run(
            confirm_chat_id="@wrong",
            source_title="English test",
            source_body="Body",
            source_url="https://example.com/e2e",
        )

    report = runner.run(
        confirm_chat_id="@approved",
        source_title="English test",
        source_body="Body",
        source_url="https://example.com/e2e",
    )

    assert report["ok"] is True
    assert report["telegram_message_id"] == 700
    evidence = json.loads((tmp_path / report["evidence_file"]).read_text(encoding="utf-8"))
    assert evidence["steps"] == ["COLLECTED", "GOOGLE_TRANSLATED", "READY_FOR_REVIEW", "APPROVED", "PUBLISHED"]


def test_cutover_and_rollback_scripts_have_explicit_confirmation_backup_and_legacy_restore():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "deploy" / "vision5"
    cutover = (root / "cutover.sh").read_text(encoding="utf-8")
    rollback = (root / "rollback.sh").read_text(encoding="utf-8")

    assert "--confirm-cutover" in cutover
    assert "cp --preserve" in cutover
    assert "nginx -t" in cutover
    assert "--confirm-rollback" in rollback
    assert "systemctl stop bikhabar-v5" in rollback
    assert "systemctl start" in rollback
