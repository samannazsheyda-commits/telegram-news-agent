from pathlib import Path

from src.fresh_x import monitored_x_sources


def test_jason_brodsky_is_not_monitored():
    handles = {row["handle"].lstrip("@").lower() for row in monitored_x_sources()}
    names = {row["name"].lower() for row in monitored_x_sources()}
    assert "jasonmbrodsky" not in handles
    assert all("brodsky" not in name for name in names)


def test_air_traffic_timer_runs_at_noon_and_midnight_tehran():
    text = Path("deploy/bikhabar-air-traffic.timer").read_text(encoding="utf-8")
    # Iran is UTC+03:30 year-round: 12:00 -> 08:30 UTC, 00:00 -> 20:30 UTC previous day.
    assert "OnCalendar=*-*-* 08:30:00 UTC" in text
    assert "OnCalendar=*-*-* 20:30:00 UTC" in text
    assert "Persistent=true" in text
