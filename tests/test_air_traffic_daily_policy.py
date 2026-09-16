from pathlib import Path


def test_air_traffic_timer_runs_only_at_midnight_tehran():
    timer = Path("deploy/bikhabar-air-traffic.timer").read_text(encoding="utf-8")
    assert "OnCalendar=*-*-* 20:30:00 UTC" in timer
    assert timer.count("OnCalendar=") == 1
    assert "16:30:00 UTC" not in timer
    assert "22:30:00 UTC" not in timer
    assert "00:00 Tehran" in timer
