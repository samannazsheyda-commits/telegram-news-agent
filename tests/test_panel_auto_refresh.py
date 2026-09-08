from pathlib import Path


def test_panel_auto_refresh_runs_real_scan_every_five_minutes_when_visible():
    js = Path('docs/panel-live-refresh.js').read_text(encoding='utf-8')
    assert 'AUTO_REFRESH_MS=5*60*1000' in js
    assert 'autoRefreshIfDue' in js
    assert "document.visibilityState!=='visible'" in js
    assert 'if(!token())return' in js
    assert 'await forceRefresh()' in js
    assert "document.addEventListener('visibilitychange'" in js


def test_panel_live_refresh_asset_is_cache_busted():
    html = Path('docs/panel.html').read_text(encoding='utf-8')
    assert 'panel-live-refresh.js?v=20260908-3' in html
