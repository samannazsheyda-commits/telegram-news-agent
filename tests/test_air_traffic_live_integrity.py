from __future__ import annotations

import pytest

import src.air_traffic_live as live


class _Response:
    def __init__(self, status: int, payload: dict):
        self.status_code = status
        self._payload = payload

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(f"{self.status_code} error")

    def json(self):
        return self._payload


class _Session:
    def __init__(self):
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(url)
        if "adsb.lol" in url:
            return _Response(429, {})
        if "adsb.one" in url:
            return _Response(200, {"ac": [{"hex": "abc", "lat": 35.7, "lon": 51.4, "seen_pos": 2, "track": 90}]})
        return _Response(403, {})


def test_point_query_falls_back_from_rate_limited_adsblol_to_adsbone():
    session = _Session()
    rows = live.fetch_point_with_fallback(35.7, 51.4, session=session)
    assert rows and rows[0]["hex"] == "abc"
    assert any("adsb.lol" in url for url in session.calls)
    assert any("adsb.one" in url for url in session.calls)
    assert not any("airplanes.live" in url for url in session.calls)


def test_snapshot_fails_closed_when_point_coverage_is_incomplete(monkeypatch):
    monkeypatch.setattr(live, "KEY_CENTERS", ((35.7, 51.4), (29.0, 52.0), (32.0, 48.0), (36.0, 58.0)))
    monkeypatch.setattr(live, "MIN_HEALTHY_CENTER_RATIO", 0.75)
    monkeypatch.setattr(live, "_fetch_opensky", lambda session=None: [{"hex": "open", "lat": 35.0, "lon": 52.0, "seen_pos": 1}])

    calls = {"n": 0}

    def flaky(_lat, _lon, *, session=None):
        calls["n"] += 1
        if calls["n"] <= 2:
            return [{"hex": f"p{calls['n']}", "lat": 35.0, "lon": 52.0, "seen_pos": 1}]
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(live, "fetch_point_with_fallback", flaky)
    monkeypatch.setattr(live.time, "sleep", lambda _seconds: None)

    with pytest.raises(RuntimeError, match="insufficient live provider coverage"):
        live.fetch_strict_live_snapshot(session=object())


def test_snapshot_accepts_only_fresh_positions(monkeypatch):
    monkeypatch.setattr(live, "KEY_CENTERS", ((35.7, 51.4),))
    monkeypatch.setattr(live, "MIN_HEALTHY_CENTER_RATIO", 1.0)
    monkeypatch.setattr(
        live,
        "_fetch_opensky",
        lambda session=None: [
            {"hex": "fresh-open", "lat": 35.0, "lon": 52.0, "seen_pos": 5},
            {"hex": "stale-open", "lat": 34.0, "lon": 52.0, "seen_pos": 90},
        ],
    )
    monkeypatch.setattr(
        live,
        "fetch_point_with_fallback",
        lambda _lat, _lon, session=None: [{"hex": "fresh-point", "lat": 35.7, "lon": 51.4, "seen_pos": 3}],
    )
    monkeypatch.setattr(live.time, "sleep", lambda _seconds: None)

    snapshot = live.fetch_strict_live_snapshot(session=object(), max_position_age_seconds=60)
    assert {row["hex"] for row in snapshot.aircraft} == {"fresh-open", "fresh-point"}
    assert snapshot.healthy_centers == 1
    assert snapshot.total_centers == 1
