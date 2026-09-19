from pathlib import Path


def test_dashboard_keeps_luna_publish_visible_but_disabled_until_luna_copy_is_ready():
    template = Path("panel/templates/dashboard.html").read_text(encoding="utf-8")
    assert '{% if final_ready %}<button class="v4-button v4-button-primary" type="button" data-v4-action="publish-luna">انتشار نسخه Luna</button>{% endif %}' not in template
    assert 'data-v4-action="publish-luna"' in template
    assert 'disabled' in template


def test_dashboard_uses_luna_translation_label_consistently():
    template = Path("panel/templates/dashboard.html").read_text(encoding="utf-8")
    script = Path("panel/static/newsroom-v4-dashboard.js").read_text(encoding="utf-8")
    assert 'ترجمه دوباره' not in template
    assert 'ترجمه دوباره' not in script
    assert 'ترجمه با Luna' in template
    assert 'ترجمه با Luna' in script
