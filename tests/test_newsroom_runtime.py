import json
from datetime import datetime, timezone

from src import runtime_v13


def test_load_newsroom_settings_handles_missing_and_valid_file(tmp_path):
    missing = tmp_path / "missing.json"
    assert runtime_v13.load_newsroom_settings(missing) == {}

    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"emergency_lock": True}), encoding="utf-8")
    assert runtime_v13.load_newsroom_settings(path)["emergency_lock"] is True


def test_emergency_lock_and_auto_publish_off_pause_publication():
    now = datetime(2026, 9, 7, 10, 0, tzinfo=timezone.utc)
    assert runtime_v13.newsroom_publish_paused({"emergency_lock": True, "auto_publish": True}, now) is True
    assert runtime_v13.newsroom_publish_paused({"emergency_lock": False, "auto_publish": False}, now) is True
    assert runtime_v13.newsroom_publish_paused({"emergency_lock": False, "auto_publish": True}, now) is False


def test_quiet_mode_supports_overnight_window():
    # Tehran is UTC+3:30 on the project timezone, so 22:00 UTC is 01:30 local next day.
    now = datetime(2026, 9, 7, 22, 0, tzinfo=timezone.utc)
    settings = {"quiet_mode": True, "quiet_start": "00:00", "quiet_end": "07:00"}
    assert runtime_v13.quiet_mode_active(settings, now) is True


def test_source_policy_accepts_raw_or_localized_source_key():
    class Item:
        source = "Reuters"

    assert runtime_v13._source_allowed(Item(), {"sources": {"Reuters": {"enabled": False}}}) is False
    assert runtime_v13._source_allowed(Item(), {"sources": {"رویترز": {"enabled": False}}}) is False
    assert runtime_v13._source_allowed(Item(), {"sources": {}}) is True
