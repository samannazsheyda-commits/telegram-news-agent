from __future__ import annotations

import json
from dataclasses import dataclass

from ..ai_newsroom import AIServiceError
from ..one_x_ai_newsroom import OneXAIConfig, OneXAINewsAI
from .store import StoryRecord


@dataclass(frozen=True)
class FinalGateDecision:
    approved: bool
    reason: str


_SYSTEM_PROMPT = """You are the final publication gate for Bikhabar, a concise factual Telegram news channel.
Approve only a concrete, current, factual event with a clear actor/action and enough information to stand alone.
Reject analysis, opinion, explainer, feature, article/report-style material, question headlines, teasers, incomplete fragments, speculation presented as fact, and materially duplicate updates already published.
Treat a different source repeating the same event as a duplicate unless it contains a genuinely new material fact.
Preserve source identity exactly; source name is evidence, not prose to rewrite.
Return JSON only with exactly these keys: {"approve": true|false, "reason": "short_machine_reason"}.
"""


class LunaFinalPublishGate:
    """Fail-closed 1xAI/Luna gate immediately before a V3 Telegram write."""

    def __init__(self, ai: OneXAINewsAI | None = None):
        self.ai = ai or OneXAINewsAI(OneXAIConfig.from_env())

    def __call__(self, story: StoryRecord, recent: list[StoryRecord]) -> FinalGateDecision:
        if not self.ai.available:
            return FinalGateDecision(False, "luna_unavailable")

        recent_payload = [
            {
                "story_id": row.story_id,
                "source": row.source,
                "title": row.title,
                "summary": row.summary,
            }
            for row in list(recent or [])[:25]
        ]
        user_payload = {
            "candidate": {
                "story_id": story.story_id,
                "source": story.source,
                "source_url": story.source_url,
                "title": story.title,
                "summary": story.summary,
                "published_at": story.published_at,
            },
            "recent_published": recent_payload,
        }
        try:
            payload = self.ai._chat_json(
                model=self.ai.config.model,
                system=_SYSTEM_PROMPT,
                user=json.dumps(user_payload, ensure_ascii=False, separators=(",", ":")),
                max_tokens=180,
            )
        except (AIServiceError, Exception):
            return FinalGateDecision(False, "luna_error")

        approved = payload.get("approve")
        reason = str(payload.get("reason") or "").strip().lower().replace(" ", "_")[:80]
        if not isinstance(approved, bool) or not reason:
            return FinalGateDecision(False, "invalid_luna_decision")
        if approved:
            return FinalGateDecision(True, reason)
        return FinalGateDecision(False, reason)
