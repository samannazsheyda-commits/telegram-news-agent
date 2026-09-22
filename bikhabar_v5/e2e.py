from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class LiveTargetConfirmationError(RuntimeError):
    pass


class E2ERunner:
    def __init__(
        self,
        *,
        store: Any,
        translator: Any,
        publisher: Any,
        telegram_chat_id: str,
        evidence_root: str | Path,
    ) -> None:
        self.store = store
        self.translator = translator
        self.publisher = publisher
        self.telegram_chat_id = str(telegram_chat_id or "").strip()
        self.evidence_root = Path(evidence_root).resolve()

    def run(
        self,
        *,
        confirm_chat_id: str,
        source_title: str,
        source_body: str,
        source_url: str,
    ) -> dict[str, Any]:
        if not self.telegram_chat_id or str(confirm_chat_id).strip() != self.telegram_chat_id:
            raise LiveTargetConfirmationError(
                "confirmed Telegram target does not match the configured live target"
            )
        run_id = uuid.uuid4().hex
        source = self.store.upsert_source(
            {
                "kind": "manual",
                "identity": f"vision5-e2e:{run_id}",
                "display_name": "Vision 5 E2E",
                "enabled": True,
            }
        )
        story, inserted = self.store.ingest_story(
            {
                "source_id": str(source["id"]),
                "source": "Vision 5 E2E",
                "source_url": source_url,
                "original_title": source_title,
                "original_text": source_body,
                "published_at_source": datetime.now(timezone.utc).isoformat(),
                "media_json": {},
            }
        )
        if not inserted:
            raise RuntimeError("E2E source URL already exists; use a unique source URL")
        story_id = str(story["id"])
        self.store.transition_story(story_id, "GOOGLE_TRANSLATING", actor="e2e")
        translated = self.translator.translate_google(story)
        self.store.record_translation(
            story_id,
            provider="google",
            title=translated["title"],
            body=translated["body"],
            actor="e2e",
        )
        self.store.transition_story(story_id, "READY_FOR_REVIEW", actor="e2e")
        self.store.save_review(
            story_id,
            title=translated["title"],
            body=translated["body"],
            copy_mode="google",
            actor="e2e-confirmed",
            approve=True,
        )
        published = self.publisher.publish(story_id, actor="e2e-confirmed")
        if published.get("status") != "PUBLISHED":
            raise RuntimeError("E2E publisher did not reach PUBLISHED")
        evidence = {
            "ok": True,
            "run_id": run_id,
            "story_id": story_id,
            "target": self.telegram_chat_id,
            "telegram_message_id": published.get("telegram_message_id"),
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "steps": [
                "COLLECTED",
                "GOOGLE_TRANSLATED",
                "READY_FOR_REVIEW",
                "APPROVED",
                "PUBLISHED",
            ],
        }
        self.evidence_root.mkdir(parents=True, exist_ok=True, mode=0o750)
        filename = f"e2e-{run_id}.json"
        destination = self.evidence_root / filename
        temporary = destination.with_suffix(".json.partial")
        temporary.write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, destination)
        return {**evidence, "evidence_file": filename}
