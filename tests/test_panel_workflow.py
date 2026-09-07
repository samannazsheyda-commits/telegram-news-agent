from pathlib import Path

WORKFLOW = Path(".github/workflows/panel-file-command.yml")


def test_panel_workflow_is_isolated_and_targeted():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert 'panel_commands/**.json' in text or 'panel_commands/*.json' in text
    assert "browser-panel-command" in text
    assert "telegram-news-agent" not in text.split("concurrency:", 1)[1].split("jobs:", 1)[0]
    assert "pytest -q" not in text
    assert "src.panel_command_file" in text


def test_panel_workflow_persists_results_and_runtime_data():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "panel_results" in text
    assert "editorial_queue.json" in text
    assert "editorial_history.json" in text
    assert "state.json" in text


def test_panel_workflow_does_not_wait_for_monitor_and_uses_minimal_install():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "browser-panel-command" in text
    assert "cancel-in-progress: false" in text
    assert "requirements.txt" in text
    assert "requirements-dev.txt" not in text
    assert "python -m pytest" not in text
