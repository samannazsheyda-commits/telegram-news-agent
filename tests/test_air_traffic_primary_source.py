from __future__ import annotations

import pytest

import src.air_traffic_live as live


def test_primary_opensky_can_publish_when_point_enrichment_is_degraded(monkeypatch):
    monkeypatch.setattr(live, "KEY_CENTERS", ((35.7, 51.4), (29.0, 52.0), (32.0, 48.0), (36.0, 58.0)))
    monkeypatch.setattr(live, "MIN_PRIMARY_AIRCRAFT", 3, raising=False)
    monkeypatch.setattr(
        live,
        "_fetch_opensky",
        lambda session=None: [
            {"hex": "open1", "lat": 35.0, "lon": 52.0, "seen_pos": 1},
            {"hex": "open2", "lat": 33.0, "lon": 50.0, "seen_pos": 2},
            {"hex": "open3", "lat": 29.0, "lon": 55.0, "seen_pos": 3},
            {"hex": "open4", "lat": 25.0, "lon": 57.0, "seen_pos": 4},
        ],
    )
    calls = {"n": 0}

    def degraded(_lat, _lon, *, session=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return [{"hex": "point1", "lat": 35.7, "lon": 51.4, "seen_pos": 1}]
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(live, "fetch_point_with_fallback", degraded)
    monkeypatch.setattr(live.time, "sleep", lambda _seconds: None)

    snapshot = live.fetch_strict_live_snapshot(session=object())

    assert {row["hex"] for row in snapshot.aircraft} == {"open1", "open2", "open3", "open4", "point1"}
    assert snapshot.healthy_centers == 1
    assert snapshot.total_centers == 4


def test_primary_opensky_still_fails_closed_when_too_sparse(monkeypatch):
    monkeypatch.setattr(live, "KEY_CENTERS", ((35.7, 51.4),))
    monkeypatch.setattr(live, "MIN_PRIMARY_AIRCRAFT", 3, raising=False)
    monkeypatch.setattr(
        live,
        "_fetch_opensky",
        lambda session=None: [
            {"hex": "open1", "lat": 35.0, "lon": 52.0, "seen_pos": 1},
            {"hex": "open2", "lat": 33.0, "lon": 50.0, "seen_pos": 2},
        ],
    )
    monkeypatch.setattr(
        live,
        "fetch_point_with_fallback",
        lambda _lat, _lon, session=None: [{"hex": "point1", "lat": 35.7, "lon": 51.4, "seen_pos": 1}],
    )
    monkeypatch.setattr(live.time, "sleep", lambda _seconds: None)

    with pytest.raises(RuntimeError, match="insufficient primary live coverage"):
        live.fetch_strict_live_snapshot(session=object())
