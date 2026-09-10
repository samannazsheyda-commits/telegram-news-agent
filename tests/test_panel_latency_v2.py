from __future__ import annotations

import threading
import time
from pathlib import Path
from unittest.mock import patch

from src import air_traffic


def test_vps_agent_uses_two_second_command_scan_target():
    service = Path("deploy/bikhabar-agent.service").read_text(encoding="utf-8")
    runtime = Path("src/vps_runtime.py").read_text(encoding="utf-8")
    assert "Environment=POLL_SECONDS=2" in service
    assert 'os.environ.get("POLL_SECONDS", "2")' in runtime


def test_air_traffic_point_fallback_fetches_centers_concurrently():
    thread_names: set[str] = set()

    def fake_fetch(lat, lon, *, session):
        del lat, lon, session
        thread_names.add(threading.current_thread().name)
        time.sleep(0.02)
        return []

    with patch.object(air_traffic, "_fetch_center", side_effect=fake_fetch):
        try:
            air_traffic._fetch_point_fallback(session=object())
        except RuntimeError as exc:
            assert "no live air-traffic positions" in str(exc)

    assert len(thread_names) >= 2
