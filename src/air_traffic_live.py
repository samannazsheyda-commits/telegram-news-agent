from __future__ import annotations

import math
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

import requests

from . import air_traffic_reference as reference


POINT_PROVIDERS = (
    "https://api.adsb.lol/v2/point/{lat}/{lon}/{radius}",
    "https://api.adsb.one/v2/point/{lat}/{lon}/{radius}",
    "https://api.airplanes.live/v2/point/{lat}/{lon}/{radius}",
)
KEY_CENTERS = reference.QUERY_CENTERS
POINT_RADIUS_NM = reference.QUERY_RADIUS_NM
POINT_QUERY_INTERVAL_SECONDS = 2.05
MIN_HEALTHY_CENTER_RATIO = 0.75
MAX_POSITION_AGE_SECONDS = 60
USER_AGENT = "bikhabaar-air-traffic-live/2.0"


@dataclass(frozen=True)
class LiveAirTrafficSnapshot:
    aircraft: list[dict]
    source_counts: dict[str, int]
    healthy_centers: int
    total_centers: int
    captured_at: datetime


def _fetch_opensky(*, session=requests) -> list[dict]:
    return reference._fetch_opensky_bbox(session=session)


def fetch_point_with_fallback(lat: float, lon: float, *, session=requests) -> list[dict]:
    errors: list[str] = []
    for template in POINT_PROVIDERS:
        url = template.format(lat=lat, lon=lon, radius=POINT_RADIUS_NM)
        try:
            response = session.get(
                url,
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
                timeout=12,
            )
            response.raise_for_status()
            payload = response.json()
            rows = payload.get("ac") if isinstance(payload, dict) else None
            if not isinstance(rows, list):
                raise ValueError("aircraft list missing")
            return rows
        except Exception as exc:
            errors.append(f"{url}: {exc}")
    raise RuntimeError("; ".join(errors) or "no live point provider response")


def _merge(groups: Iterable[Iterable[dict]]) -> list[dict]:
    return reference._merge_aircraft_rows(*list(groups))


def fetch_strict_live_snapshot(
    *,
    session=requests,
    max_position_age_seconds: float = MAX_POSITION_AGE_SECONDS,
) -> LiveAirTrafficSnapshot:
    try:
        opensky_rows = _fetch_opensky(session=session)
    except Exception as exc:
        raise RuntimeError(f"opensky live coverage unavailable: {exc}") from exc

    point_groups: list[list[dict]] = []
    healthy_centers = 0
    total_centers = len(KEY_CENTERS)
    for index, (lat, lon) in enumerate(KEY_CENTERS):
        try:
            rows = fetch_point_with_fallback(lat, lon, session=session)
        except Exception as exc:
            print(f"AIR_TRAFFIC_LIVE_CENTER_FAIL center=({lat},{lon}) error={exc}", flush=True)
        else:
            healthy_centers += 1
            point_groups.append(rows)
        if index + 1 < total_centers and POINT_QUERY_INTERVAL_SECONDS > 0:
            time.sleep(POINT_QUERY_INTERVAL_SECONDS)

    minimum_healthy = max(1, math.ceil(total_centers * MIN_HEALTHY_CENTER_RATIO))
    if healthy_centers < minimum_healthy:
        raise RuntimeError(
            "insufficient live provider coverage: "
            f"healthy_centers={healthy_centers}/{total_centers} minimum={minimum_healthy}"
        )

    fresh_opensky = reference.filter_visible_aircraft(
        opensky_rows,
        max_seen_seconds=max_position_age_seconds,
    )
    fresh_points = reference.filter_visible_aircraft(
        _merge(point_groups),
        max_seen_seconds=max_position_age_seconds,
    )
    merged = reference.filter_visible_aircraft(
        reference._merge_aircraft_rows(fresh_opensky, fresh_points),
        max_seen_seconds=max_position_age_seconds,
    )
    if not merged:
        raise RuntimeError("no fresh live aircraft positions after integrity filtering")

    snapshot = LiveAirTrafficSnapshot(
        aircraft=merged,
        source_counts={
            "opensky": len(fresh_opensky),
            "point_network": len(fresh_points),
        },
        healthy_centers=healthy_centers,
        total_centers=total_centers,
        captured_at=datetime.now(timezone.utc),
    )
    print(
        "AIR_TRAFFIC_LIVE_OK "
        f"aircraft={len(snapshot.aircraft)} "
        f"healthy_centers={snapshot.healthy_centers}/{snapshot.total_centers} "
        f"opensky={snapshot.source_counts['opensky']} "
        f"point_network={snapshot.source_counts['point_network']}",
        flush=True,
    )
    return snapshot
