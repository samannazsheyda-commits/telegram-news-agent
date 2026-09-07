from pathlib import Path


def test_panel_assets_are_cache_busted():
    html = Path('docs/panel.html').read_text(encoding='utf-8')
    assert 'panel.js?v=' in html
    assert 'panel-live-refresh.js?v=' in html
    assert 'newsroom-v1.js?v=' in html
    assert 'panel.css?v=' in html
    assert 'newsroom-v1.css?v=' in html


def test_bulk_clear_syncs_authoritative_queue_before_command():
    js = Path('docs/newsroom-v1.js').read_text(encoding='utf-8')
    assert "await load(false);" in js
    assert "صف با داده واقعی همگام شد" in js


def test_refresh_result_is_persistently_visible():
    js = Path('docs/panel-live-refresh.js').read_text(encoding='utf-8')
    assert "result.message" in js
    assert "lastRefresh" in js
    assert "نتیجه اسکن" in js
