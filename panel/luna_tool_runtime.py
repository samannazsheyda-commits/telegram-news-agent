from __future__ import annotations

from typing import Any

from .luna_translation import translate_story_in_repository


def execute_luna_tool(
    toolbox,
    name: str,
    arguments: dict[str, Any] | None = None,
    *,
    provider_client=None,
    confirmed: bool = False,
) -> dict:
    """Execute one Luna tool while keeping shared cross-tool pipelines centralized.

    Translation is deliberately routed through the same guarded repository
    pipeline used by story cards so chat can never promote the legacy machine
    translation path to final publishable copy.
    """
    args = dict(arguments or {})
    if name == "translate_story":
        story_id = str(args.get("story_id") or "").strip()
        if not story_id:
            return {
                "ok": False,
                "error": "story_id_required",
                "message": "شناسه خبر لازم است.",
            }
        if provider_client is None:
            return {
                "ok": False,
                "error": "translation_provider_required",
                "message": "Luna برای ترجمه به اتصال OpenAI نیاز دارد.",
            }
        return translate_story_in_repository(
            toolbox.data,
            story_id,
            provider_client,
        )
    return toolbox.execute(name, args, confirmed=confirmed)
