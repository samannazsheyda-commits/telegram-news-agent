from __future__ import annotations

from datetime import datetime, timedelta, timezone


class Store:
    def dashboard_metrics(self):
        return {"review_ready": 2, "published_today": 3, "publish_failed": 0, "sources_total": 5}

    def list_service_health(self):
        return [
            {"service_name": "postgres", "status": "healthy"},
            {"service_name": "redis", "status": "healthy"},
        ]


def test_observation_ledger_requires_full_24_hours_of_healthy_samples(tmp_path):
    from bikhabar_v5.observation import ObservationLedger

    start = datetime(2026, 9, 22, 12, tzinfo=timezone.utc)
    now = [start]
    ledger = ObservationLedger(root=tmp_path, store=Store(), clock=lambda: now[0])
    ledger.record()
    for hour in range(1, 25):
        now[0] = start + timedelta(hours=hour)
        ledger.record()

    report = ledger.verify(hours=24)

    assert report["ok"] is True
    assert report["sample_count"] == 25
    assert report["unhealthy_samples"] == 0
    assert report["duration_hours"] >= 24
