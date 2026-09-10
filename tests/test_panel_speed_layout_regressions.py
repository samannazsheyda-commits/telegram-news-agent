from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from src.newsroom_hybrid_runtime import _record_runtime_heartbeat


def test_live_selection_survives_feed_refreshes():
    js = Path("panel/static/live.js").read_text(encoding="utf-8")
    assert "selectedNewsIds = new Set" in js
    assert "check.checked = selectedNewsIds.has(id)" in js
    assert "selectedNewsIds.add" in js
    assert "selectedNewsIds.delete" in js


def test_unchanged_live_revision_skips_expensive_dom_rebuild():
    js = Path("panel/static/live.js").read_text(encoding="utf-8")
    api = Path("panel/live_api.py").read_text(encoding="utf-8")
    assert "lastFeedRevision" in js
    assert "data.revision" in js
    assert "revision" in api
    assert "hashlib" in api


def test_live_news_is_above_operational_controls_and_modules():
    html = Path("panel/templates/dashboard.html").read_text(encoding="utf-8")
    live = html.index("ورودی زنده")
    controls = html.index("کنترل انتشار")
    modules = html.index("پیش‌نمایش و انتشار")
    assert live < controls < modules


def test_heavy_operational_sections_are_collapsible():
    html = Path("panel/templates/dashboard.html").read_text(encoding="utf-8")
    assert 'class="ops-fold"' in html
    assert "ابزارهای عملیاتی" in html
    assert "تنظیمات و سلامت" in html


def test_live_final_output_is_collapsed_by_default():
    js = Path("panel/static/live.js").read_text(encoding="utf-8")
    assert "final-output-details" in js
    assert "خروجی نهایی تلگرام" in js


def test_runtime_heartbeat_records_truthful_scan_timestamp(tmp_path):
    state_path = tmp_path / "state.json"
    now = datetime(2026, 9, 10, 21, 0, tzinfo=timezone.utc)
    _record_runtime_heartbeat(
        {"rc": 0, "published": 0, "telegram_writes": 0, "publish_failed": 0, "sources_ok": 5, "sources_failed": 0, "items_fetched": 12, "panel_commands": 0},
        now=now,
        state_path=state_path,
    )
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["last_scan_at"] == now.isoformat()
    assert state["last_cycle_at"] == now.isoformat()


def test_panel_status_uses_runtime_poll_interval_not_old_hardcoded_five_seconds():
    source = Path("panel/command_center.py").read_text(encoding="utf-8")
    assert 'os.environ.get("POLL_SECONDS", "2")' in source
    assert '"poll_seconds": 5' not in source


def test_compact_newsroom_css_exists_for_small_buttons_and_shorter_page():
    css = Path("panel/static/newsroom-compact.css").read_text(encoding="utf-8")
    assert ".newsroom-live-actions .button" in css
    assert ".ops-fold" in css
    assert "padding:6px 8px" in css.replace(" ", "") or "padding: 6px 8px" in css
