from __future__ import annotations

import json

from .air_traffic_live import LiveAirTrafficSnapshot
from .one_x_ai_newsroom import OneXAIConfig, OneXAINewsAI


_SYSTEM_PROMPT = """You write one short Persian sentence for Bikhabar's live air-traffic card.
Use only the structured live facts supplied by the caller.
Do not invent routes, closures, incidents, causes, military activity, airport status, destinations, or aircraft identities.
Describe only visible traffic density/distribution that is supported by the supplied counts.
Do not call an area empty unless its supplied count is zero. Do not imply the data is complete beyond the stated provider coverage.
Return only the final concise Persian sentence, with no structured wrapper, markdown, labels, or explanation.
"""


def _seen_seconds(row: dict) -> float:
    value = row.get("seen_pos")
    if value is None:
        value = row.get("seen")
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return 9999.0


def _region_counts(rows: list[dict]) -> dict[str, int]:
    counts = {
        "iran": 0,
        "persian_gulf_oman": 0,
        "iraq_levant": 0,
        "caucasus_caspian": 0,
        "arabian_peninsula": 0,
        "east_of_iran": 0,
    }
    for row in rows:
        try:
            lat = float(row.get("lat"))
            lon = float(row.get("lon"))
        except (TypeError, ValueError):
            continue
        if 25.0 <= lat <= 40.0 and 44.0 <= lon <= 63.5:
            counts["iran"] += 1
        if 20.0 <= lat < 30.5 and 47.0 <= lon <= 61.5:
            counts["persian_gulf_oman"] += 1
        if 28.0 <= lat <= 38.5 and 35.0 <= lon < 48.0:
            counts["iraq_levant"] += 1
        if 38.0 < lat <= 48.5 and 40.0 <= lon <= 58.0:
            counts["caucasus_caspian"] += 1
        if 12.0 <= lat < 28.0 and 38.0 <= lon < 52.0:
            counts["arabian_peninsula"] += 1
        if 24.0 <= lat <= 39.0 and 60.0 < lon <= 69.0:
            counts["east_of_iran"] += 1
    return counts


class LunaAirTrafficReporter:
    def __init__(self, ai: OneXAINewsAI | None = None):
        self.ai = ai or OneXAINewsAI(OneXAIConfig.from_env())

    def build_summary(self, snapshot: LiveAirTrafficSnapshot) -> str:
        if not self.ai.available:
            raise RuntimeError("luna_air_traffic_unavailable")

        ages = [_seen_seconds(row) for row in snapshot.aircraft]
        facts = {
            "aircraft_count": len(snapshot.aircraft),
            "healthy_centers": snapshot.healthy_centers,
            "total_centers": snapshot.total_centers,
            "source_counts": snapshot.source_counts,
            "max_position_age_seconds": round(max(ages) if ages else 0.0, 1),
            "region_counts": _region_counts(snapshot.aircraft),
            "captured_at_utc": snapshot.captured_at.isoformat(),
        }
        try:
            summary = self.ai._chat_text(
                model=self.ai.config.model,
                system=_SYSTEM_PROMPT,
                user=json.dumps(facts, ensure_ascii=False, separators=(",", ":")),
                max_tokens=160,
            )
        except Exception as exc:
            raise RuntimeError("luna_air_traffic_error") from exc

        summary = str(summary or "").strip()
        if not summary or len(summary) > 260:
            raise RuntimeError("invalid_luna_air_traffic_summary")
        return summary
