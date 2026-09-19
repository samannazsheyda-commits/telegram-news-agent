from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_app_shell_has_four_primary_tabs_and_persistent_view_state():
    html = _read("panel/templates/app_shell.html")
    js = _read("panel/static/newsroom-v5-app.js")
    for label in ("خبرها", "Luna", "منتشرشده", "کنترل"):
        assert label in html
    assert "sessionStorage" in js
    assert "activeTab" in js
    assert "reviewScroll" in js
    assert "window.location.href" not in js


def test_review_uses_cursor_infinite_loading_without_business_cap():
    js = _read("panel/static/newsroom-v5-review.js")
    assert "IntersectionObserver" in js
    assert "next_cursor" in js
    assert "MAX_RENDERED_CARDS" in js
    assert "items.slice(0, 100)" not in js
    assert "items.slice(0,100)" not in js
    assert "عنوان فارسی در حال آماده‌سازی" not in js
    assert "window.location.href" not in js


def test_sse_is_primary_and_polling_is_fallback_not_five_second_full_reload():
    js = _read("panel/static/newsroom-v5-app.js")
    assert "EventSource" in js
    assert "startPollingFallback" in js
    assert "stopPollingFallback" in js
    assert "location.reload()" not in js
    assert "5000" not in js


def test_review_actions_have_confirmation_and_double_submit_guard():
    js = _read("panel/static/newsroom-v5-review.js")
    assert "confirmPublish" in js
    assert "confirmReject" in js
    assert "busyStoryIds" in js
    assert "Idempotency-Key" in js
