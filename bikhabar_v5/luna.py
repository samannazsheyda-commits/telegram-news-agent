from __future__ import annotations

import json
from typing import Any

from .translation import TranslationPipeline


LUNA_TOOLS = [
    {
        "type": "function",
        "name": "request_alternate_translation",
        "description": "Request an alternate Persian translation for the selected story. Requires human execution.",
        "parameters": {
            "type": "object",
            "properties": {"story_id": {"type": "string"}},
            "required": ["story_id"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "propose_builder_change",
        "description": "Propose a code change. Deployment always requires explicit human confirmation.",
        "parameters": {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "patch": {"type": "string"},
            },
            "required": ["summary", "patch"],
            "additionalProperties": False,
        },
        "strict": True,
    },
]


class LunaOperator:
    def __init__(self, *, store: Any, model: Any) -> None:
        self.store = store
        self.model = model

    def chat(self, *, user_id: str, message: str, story_id: str | None = None) -> dict[str, Any]:
        prompt = str(message or "").strip()
        if not prompt:
            raise ValueError("Luna message is required")
        conversation = self.store.get_luna_conversation(user_id) or {"messages": [], "context": {}}
        memory = list(conversation.get("messages") or [])[-20:]
        story = self.store.get_story(story_id) if story_id else None
        rules = self.store.list_newsroom_rules()
        context = {"selected_story": story, "newsroom_rules": rules}
        input_items = [
            {
                "role": "user",
                "content": (
                    "Newsroom context:\n"
                    + json.dumps(context, ensure_ascii=False, default=str)
                    + "\nConversation memory:\n"
                    + json.dumps(memory, ensure_ascii=False, default=str)
                    + "\nOperator request:\n"
                    + prompt
                ),
            }
        ]
        result = self.model.respond(
            instructions=(
                "You are Luna, the Persian newsroom operator for Bikhabar Vision 5. "
                "Be factual, concise and preserve source attribution. Never claim that a mutating "
                "action happened unless a tool result confirms it. Publishing and deployment require "
                "explicit human confirmation."
            ),
            input_items=input_items,
            tools=LUNA_TOOLS,
        )
        assistant_text = str(result.get("text") or "").strip()
        messages = [*memory, {"role": "user", "content": prompt}]
        if assistant_text:
            messages.append({"role": "assistant", "content": assistant_text})
        self.store.save_luna_conversation(
            user_id,
            messages=messages[-50:],
            context={"story_id": story_id, "response_id": result.get("response_id")},
        )
        self.store.record_operator_audit(
            actor=user_id,
            action="luna_chat",
            entity_type="story" if story_id else "conversation",
            entity_id=story_id or user_id,
            status="succeeded",
            detail={"usage": result.get("usage") or {}, "tool_calls": result.get("tool_calls") or []},
        )
        return result

    def alternate_translation(self, *, story_id: str, actor: str) -> dict[str, Any]:
        story = self.store.get_story(story_id)
        if story is None:
            raise LookupError(f"story not found: {story_id}")
        translated = TranslationPipeline(google=self.model, luna=self.model).translate_luna(story)
        result = self.store.record_translation(
            story_id,
            provider="luna",
            title=translated["title"],
            body=translated["body"],
            actor=actor,
        )
        self.store.record_operator_audit(
            actor=actor,
            action="luna_alternate_translation",
            entity_type="story",
            entity_id=story_id,
            status="succeeded",
            detail={},
        )
        return result
