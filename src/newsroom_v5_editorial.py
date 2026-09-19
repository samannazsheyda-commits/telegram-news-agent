from __future__ import annotations

import os
from typing import Any

from .newsroom_v5_store import NewsroomV5Store


def _bool_env(name: str, default: bool = False) -> bool:
    raw = str(os.environ.get(name, "true" if default else "false") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _value(decision: Any, name: str, default: Any = None) -> Any:
    if isinstance(decision, dict):
        return decision.get(name, default)
    return getattr(decision, name, default)


def route_editorial(
    store: NewsroomV5Store,
    story_id: str,
    decision: Any,
    *,
    auto_publish_enabled: bool | None = None,
    source_enabled: bool = True,
    fresh: bool = True,
    relevant: bool = True,
    duplicate: bool = False,
) -> str:
    story = store.get_story(story_id)
    if story is None:
        raise KeyError(story_id)
    if duplicate:
        store.set_editorial_decision(
            story_id,
            importance=str(_value(decision, "importance", "")),
            priority_class=str(_value(decision, "priority_class", "low")),
            publish_recommended=False,
            new_fact=False,
            topic=str(_value(decision, "topic", "")),
            reason="duplicate",
            confidence=float(_value(decision, "confidence", 0.0) or 0.0),
            model=str(_value(decision, "model", "")),
        )
        store.transition_story(story_id, {story["state"]}, "duplicate")
        return "duplicate"
    if not relevant:
        store.set_editorial_decision(
            story_id,
            importance=str(_value(decision, "importance", "")),
            priority_class=str(_value(decision, "priority_class", "low")),
            publish_recommended=False,
            new_fact=bool(_value(decision, "new_fact", False)),
            topic=str(_value(decision, "topic", "")),
            reason="irrelevant",
            confidence=float(_value(decision, "confidence", 0.0) or 0.0),
            model=str(_value(decision, "model", "")),
        )
        store.transition_story(story_id, {story["state"]}, "irrelevant")
        return "irrelevant"

    quality_passed = bool(story.get("quality_passed")) and bool(str(story.get("title_fa") or "").strip())
    if not quality_passed:
        return "failed"

    importance_raw = _value(decision, "importance", 0)
    try:
        importance = int(importance_raw or 0)
    except (TypeError, ValueError):
        importance = 0
    priority = str(_value(decision, "priority_class", "normal") or "normal").strip().lower()
    publish_recommended = bool(_value(decision, "publish", _value(decision, "publish_recommended", False)))
    new_fact = bool(_value(decision, "new_fact", False))
    confidence_raw = _value(decision, "confidence", 1.0 if publish_recommended else 0.0)
    try:
        confidence = float(confidence_raw)
    except (TypeError, ValueError):
        confidence = 0.0

    store.set_editorial_decision(
        story_id,
        importance=str(importance),
        priority_class=priority,
        publish_recommended=publish_recommended,
        new_fact=new_fact,
        topic=str(_value(decision, "topic", "")),
        reason=str(_value(decision, "reason", "")),
        confidence=confidence,
        model=str(_value(decision, "model", "")),
    )

    enabled = _bool_env("NEWSROOM_AUTO_PUBLISH_ENABLED", False) if auto_publish_enabled is None else bool(auto_publish_enabled)
    high_enough = priority == "critical" or (priority == "high" and confidence >= float(os.environ.get("NEWSROOM_AUTO_PUBLISH_MIN_CONFIDENCE", "0.85")))
    auto_candidate = all((enabled, source_enabled, fresh, publish_recommended, new_fact, high_enough))
    target = "editorial_ready" if auto_candidate else "review"
    store.transition_story(story_id, {"translated", "editorial_ready", "review"}, target)
    store.append_audit(
        "editorial_routed",
        entity_type="story",
        entity_id=story_id,
        detail={"outcome": "auto_publish_candidate" if auto_candidate else "review", "priority": priority, "confidence": confidence},
    )
    return "auto_publish_candidate" if auto_candidate else "review"
