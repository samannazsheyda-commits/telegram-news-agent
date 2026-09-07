from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_static_dashboard_has_required_files_and_data_sources():
    index = ROOT / "dashboard" / "index.html"
    app_js = ROOT / "dashboard" / "app.js"
    css = ROOT / "dashboard" / "styles.css"

    assert index.exists()
    assert app_js.exists()
    assert css.exists()

    html = index.read_text(encoding="utf-8")
    js = app_js.read_text(encoding="utf-8")

    assert "بی‌خبر" in html
    assert "editorial_queue.json" in js
    assert "editorial_history.json" in js
    assert "state.json" in js
    assert "actions/workflows/agent.yml" in js
