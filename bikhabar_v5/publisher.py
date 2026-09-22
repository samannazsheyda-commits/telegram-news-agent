from __future__ import annotations

from typing import Any

import requests


class PublishError(RuntimeError):
    pass


class AmbiguousPublishError(PublishError):
    pass


def _final_text(story: dict[str, Any]) -> str:
    title = str(story.get("final_title") or "").strip()
    body = str(story.get("final_body") or "").strip()
    if not title:
        raise PublishError("story has no approved final title")
    return f"{title}\n\n{body}".strip()


def _is_ambiguous_transport_error(exc: Exception) -> bool:
    return isinstance(exc, (TimeoutError, requests.Timeout, requests.ConnectionError))


def _primary_media(value: Any) -> dict[str, Any]:
    media = dict(value or {}) if isinstance(value, dict) else {}
    if media.get("url"):
        return media
    for item in media.get("items") or []:
        if not isinstance(item, dict) or not item.get("url"):
            continue
        normalized_type = str(item.get("type") or "").lower()
        if normalized_type.startswith("image"):
            normalized_type = "photo"
        elif normalized_type.startswith("video"):
            normalized_type = "video"
        return {**item, "type": normalized_type or "photo"}
    return {}


class TelegramPublisher:
    def __init__(self, *, store: Any, telegram: Any) -> None:
        self.store = store
        self.telegram = telegram

    def _prepare(self, story_id: str, *, actor: str, allow_retry: bool):
        return self.store.prepare_publish(
            story_id,
            idempotency_key=f"telegram:{story_id}",
            copy_mode="final",
            payload={},
            actor=actor,
            allow_retry=allow_retry,
        )

    def publish(
        self,
        story_id: str,
        *,
        actor: str,
        allow_retry: bool = False,
    ) -> dict[str, Any]:
        story, attempt = self._prepare(story_id, actor=actor, allow_retry=allow_retry)
        if attempt.get("status") == "completed":
            return story
        if bool(attempt.get("ambiguous")) or attempt.get("status") == "ambiguous":
            raise AmbiguousPublishError(
                "publish outcome is ambiguous and requires operator reconciliation"
            )
        text = _final_text(story)
        media = _primary_media(story.get("media_json"))
        try:
            response = self.telegram.send(text=text, media=media)
            message_id = int(response["message_id"])
        except Exception as exc:
            ambiguous = _is_ambiguous_transport_error(exc)
            self.store.fail_publish(
                story_id,
                attempt["id"],
                error=str(exc),
                ambiguous=ambiguous,
                actor=actor,
            )
            if ambiguous:
                raise AmbiguousPublishError(
                    "Telegram response was ambiguous; do not retry before reconciliation"
                ) from exc
            raise PublishError(f"Telegram publish failed: {exc}") from exc
        return self.store.complete_publish(
            story_id,
            attempt["id"],
            telegram_message_id=message_id,
            actor=actor,
        )

    def reconcile(
        self,
        story_id: str,
        *,
        telegram_message_id: int,
        actor: str,
    ) -> dict[str, Any]:
        message_id = int(telegram_message_id)
        if message_id <= 0:
            raise ValueError("telegram_message_id must be positive")
        _story, attempt = self._prepare(story_id, actor=actor, allow_retry=False)
        if not bool(attempt.get("ambiguous")):
            raise PublishError("only an ambiguous publish attempt can be reconciled")
        return self.store.reconcile_publish(
            story_id,
            attempt["id"],
            telegram_message_id=message_id,
            actor=actor,
        )

    def recover_approved(self, *, limit: int = 10) -> list[dict[str, Any]]:
        recovered = []
        for story_id in self.store.story_ids_by_status("APPROVED", limit=limit):
            recovered.append(self.publish(story_id, actor="publisher-recovery"))
        return recovered
