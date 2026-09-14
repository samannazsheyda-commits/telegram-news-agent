from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .store import NewsroomV3Store, StoryRecord


AMBIGUOUS_ERROR_PREFIX = "ambiguous_remote_state:"


@dataclass(frozen=True)
class PublishResult:
    story_id: str
    state: str
    attempt_no: int | None = None
    error: str = ""
    telegram_message_id: int | None = None
    ambiguous: bool = False


def _publisher_result(payload) -> tuple[bool, int | None, str, bool]:
    if isinstance(payload, int):
        return True, int(payload), "", False
    if not isinstance(payload, dict):
        return False, None, "publisher_unverified_response", True

    message_id = payload.get("message_id")
    if message_id is None and isinstance(payload.get("result"), dict):
        message_id = payload["result"].get("message_id")
    if payload.get("ok") is True and isinstance(message_id, int):
        return True, message_id, "", False
    return (
        False,
        None,
        str(payload.get("error") or payload.get("description") or "publish_failed"),
        payload.get("ambiguous") is True,
    )


class NewsroomV3PublisherWorker:
    """Publish one durable V3 story without mutating its editorial decision."""

    def __init__(self, store: NewsroomV3Store, publisher: Callable[[StoryRecord], object]):
        self.store = store
        self.publisher = publisher

    def publish_story(self, story_id: str) -> PublishResult:
        story = self.store.get_story(story_id)
        if story is None:
            raise KeyError(story_id)

        if story.publish_state == "published" and story.telegram_message_id is not None:
            return PublishResult(
                story_id=story.story_id,
                state="already_published",
                telegram_message_id=story.telegram_message_id,
            )

        if story.decision_state != "ready":
            return PublishResult(story_id=story.story_id, state="not_publishable")

        if story.publish_state == "publishing":
            return PublishResult(story_id=story.story_id, state="busy")

        attempt = self.store.begin_publish(story.story_id)
        try:
            payload = self.publisher(story)
            ok, message_id, error, ambiguous = _publisher_result(payload)
        except Exception as exc:
            ok = False
            message_id = None
            error = f"{type(exc).__name__}: {exc}"
            # An exception escaping the publisher does not prove whether an
            # external write happened. Fail closed and never auto-retry it.
            ambiguous = True

        if ok and message_id is not None:
            self.store.mark_published(story.story_id, telegram_message_id=message_id)
            return PublishResult(
                story_id=story.story_id,
                state="published",
                attempt_no=attempt.attempt_no,
                telegram_message_id=message_id,
            )

        persisted_error = (
            f"{AMBIGUOUS_ERROR_PREFIX}{error}"
            if ambiguous and not str(error).startswith(AMBIGUOUS_ERROR_PREFIX)
            else error
        )
        self.store.mark_publish_failed(story.story_id, persisted_error)
        return PublishResult(
            story_id=story.story_id,
            state="failed",
            attempt_no=attempt.attempt_no,
            error=persisted_error,
            ambiguous=ambiguous,
        )
