from __future__ import annotations

from typing import Any, Callable

from .newsroom_v5_jobs import enqueue_once
from .newsroom_v5_store import NewsroomV5Store
from .services import has_persian, translate_to_fa, translation_is_publishable


def _fallback_value(result: Any) -> tuple[str, str]:
    if result is None:
        return "", "ai"
    if isinstance(result, dict):
        return str(result.get("text") or "").strip(), str(result.get("backend") or "ai").strip() or "ai"
    text = str(getattr(result, "text", result) or "").strip()
    backend = str(getattr(result, "backend", "ai") or "ai").strip()
    return text, backend


def _translate_piece(source: str, lightweight: Callable[[str], str], ai_fallback: Callable[[str], Any] | None) -> tuple[str, str]:
    source = str(source or "").strip()
    if not source:
        return "", ""
    try:
        lightweight_value = str(lightweight(source) or "").strip()
    except Exception:
        lightweight_value = ""
    if lightweight_value and translation_is_publishable(source, lightweight_value):
        return lightweight_value, "lightweight"
    if ai_fallback is not None:
        try:
            value, backend = _fallback_value(ai_fallback(source))
        except Exception:
            value, backend = "", "ai"
        if value and translation_is_publishable(source, value):
            return value, backend
    return "", ""


def translate_story(
    store: NewsroomV5Store,
    story_id: str,
    *,
    lightweight: Callable[[str], str] = translate_to_fa,
    ai_fallback: Callable[[str], Any] | None = None,
) -> dict:
    story = store.get_story(story_id)
    if story is None:
        raise KeyError(story_id)
    if story.get("state") in {"published", "rejected", "duplicate", "irrelevant"}:
        return {"status": str(story["state"]), "story": story}

    source_title = str(story.get("original_title") or "").strip()
    source_body = str(story.get("original_body") or "").strip()

    title_fa, title_backend = _translate_piece(source_title, lightweight, ai_fallback)
    if not title_fa:
        store.set_translation(
            story_id,
            title_fa="",
            body_fa="",
            backend="failed",
            quality_passed=False,
            last_error="translation_failed",
        )
        enqueue_once(store, "translate_story", story_id=story_id, payload={"reason": "translation_failed"})
        return {"status": "retry", "story": store.get_story(story_id)}

    body_fa = ""
    body_backend = title_backend
    if source_body:
        candidate, candidate_backend = _translate_piece(source_body, lightweight, ai_fallback)
        if candidate:
            body_fa, body_backend = candidate, candidate_backend
        elif has_persian(source_body):
            body_fa = str(lightweight(source_body) or source_body).strip()

    backend = title_backend if title_backend == body_backend or not body_fa else f"{title_backend}+{body_backend}"
    store.set_translation(
        story_id,
        title_fa=title_fa,
        body_fa=body_fa,
        backend=backend,
        quality_passed=True,
        last_error=None,
    )
    if story.get("state") == "received":
        store.transition_story(story_id, {"received"}, "translated")
    store.append_audit(
        "story_translated",
        entity_type="story",
        entity_id=story_id,
        detail={"backend": backend},
    )
    return {"status": "translated", "story": store.get_story(story_id)}
