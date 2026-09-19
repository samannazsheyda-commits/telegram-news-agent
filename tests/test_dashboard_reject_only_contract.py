from pathlib import Path


def test_dashboard_template_never_renders_translation_placeholder_or_block_action():
    template = Path("panel/templates/dashboard.html").read_text(encoding="utf-8")

    assert "عنوان فارسی در حال آماده‌سازی" not in template
    assert "رد و مسدودکردن" not in template
    assert 'data-v4-action="reject"' in template


def test_dashboard_javascript_never_creates_pending_cards_or_calls_block_endpoint():
    js = Path("panel/static/newsroom-v4-dashboard.js").read_text(encoding="utf-8")

    assert "ترجمه ماشینی در حال آماده‌سازی" not in js
    assert "رد و مسدودکردن" not in js
    assert "/api/panel/luna/block-story/" not in js
    assert "if (!isMachineReady(item)) return null;" in js
    assert "/api/newsroom/live/${encodeURIComponent(id)}/reject" in js
