from pathlib import Path
import json


def test_panel_loads_publish_visibility_guard():
    html = Path('docs/panel.html').read_text(encoding='utf-8')
    assert 'panel-publish-visibility.js?v=' in html


def test_relaxed_newsroom_intake_defaults():
    settings = json.loads(Path('data/newsroom_settings.json').read_text(encoding='utf-8'))
    assert settings['freshness_hours'] >= 12
    assert settings['dedup_mode'] == 'balanced'


def test_publish_visibility_guard_persists_published_ids():
    js = Path('docs/panel-publish-visibility.js').read_text(encoding='utf-8')
    assert 'bikhabar_recent_published' in js
    assert 'data-action="publish"' in js
    assert 'MutationObserver' in js
