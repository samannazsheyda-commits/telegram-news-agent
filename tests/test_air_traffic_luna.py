from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from src.air_traffic_live import LiveAirTrafficSnapshot
from src.air_traffic_luna import LunaAirTrafficReporter


class _FakeAI:
    def __init__(self, payload=None, *, available=True, error=None):
        self.available = available
        self.payload = payload
        self.error = error
        self.config = SimpleNamespace(model="gpt-5.6-luna")
        self.calls = []

    def _chat_json(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.payload


def _snapshot():
    return LiveAirTrafficSnapshot(
        aircraft=[
            {"hex": "iran1", "lat": 35.7, "lon": 51.4, "seen_pos": 2, "track": 90},
            {"hex": "gulf1", "lat": 25.2, "lon": 55.3, "seen_pos": 4, "track": 180},
        ],
        source_counts={"opensky": 2, "point_network": 1},
        healthy_centers=20,
        total_centers=21,
        captured_at=datetime(2026, 9, 16, 9, 30, tzinfo=timezone.utc),
    )


def test_luna_report_uses_only_structured_live_facts():
    ai = _FakeAI({"summary": "ترافیک هوایی در خلیج فارس متراکم‌تر از بخش مرکزی ایران دیده می‌شود."})
    reporter = LunaAirTrafficReporter(ai)
    text = reporter.build_summary(_snapshot())

    assert "خلیج فارس" in text
    assert ai.calls[0]["model"] == "gpt-5.6-luna"
    user = ai.calls[0]["user"]
    assert '"aircraft_count":2' in user
    assert '"healthy_centers":20' in user
    assert '"total_centers":21' in user
    assert '"max_position_age_seconds":4.0' in user


def test_luna_report_fails_closed_when_unavailable_invalid_or_error():
    with pytest.raises(RuntimeError, match="luna_air_traffic_unavailable"):
        LunaAirTrafficReporter(_FakeAI(available=False)).build_summary(_snapshot())

    with pytest.raises(RuntimeError, match="invalid_luna_air_traffic_summary"):
        LunaAirTrafficReporter(_FakeAI({"summary": ""})).build_summary(_snapshot())

    with pytest.raises(RuntimeError, match="luna_air_traffic_error"):
        LunaAirTrafficReporter(_FakeAI(error=RuntimeError("timeout"))).build_summary(_snapshot())


def test_luna_prompt_forbids_inventing_routes_closures_or_incidents():
    ai = _FakeAI({"summary": "وضعیت بر پایه داده زنده دریافت‌شده گزارش شده است."})
    LunaAirTrafficReporter(ai).build_summary(_snapshot())
    system = ai.calls[0]["system"].lower()
    assert "do not invent" in system
    assert "route" in system
    assert "closure" in system
    assert "incident" in system
