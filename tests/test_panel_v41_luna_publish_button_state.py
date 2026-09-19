from pathlib import Path


def test_luna_publish_button_is_visible_but_disabled_until_luna_copy_is_ready():
    html = Path("panel/templates/dashboard.html").read_text(encoding="utf-8")
    js = Path("panel/static/newsroom-v4-dashboard.js").read_text(encoding="utf-8")

    assert 'data-v4-action="publish-luna"' in html
    assert "disabled" in html
    assert "ترجمه با Luna" in html
    assert "ترجمه دوباره" not in html

    assert "انتشار نسخه Luna" in js
    assert "publish-luna" in js
    assert "disabled = true" in js
    assert "ترجمه دوباره" not in js
