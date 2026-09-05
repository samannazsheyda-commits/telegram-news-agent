from pathlib import Path


RUNTIME_COMMAND = 'python -m src.runtime_v9 --monitor'


def _workflow_text() -> str:
    return Path('.github/workflows/agent.yml').read_text(encoding='utf-8')


def test_workflow_runs_bounded_monitor_and_keeps_manual_dispatch():
    text = _workflow_text()
    assert 'workflow_dispatch:' in text
    assert RUNTIME_COMMAND in text
    assert 'timeout-minutes: 7' in text
    assert 'concurrency:' in text
    assert 'cancel-in-progress: false' in text
    assert 'data/editorial_queue.json' in text
    assert 'data/editorial_history.json' in text
    assert 'POLL_SECONDS: "60"' in text
    assert 'SESSION_SECONDS: "270"' in text


def test_scheduled_run_refreshes_latest_main_before_monitor():
    text = _workflow_text()
    assert "if: github.event_name == 'schedule'" in text
    assert 'git fetch origin main' in text
    assert 'git reset --hard origin/main' in text
    assert text.index('git reset --hard origin/main') < text.index(RUNTIME_COMMAND)


def test_workflow_restores_runtime_state_after_tests_before_monitor():
    text = _workflow_text()
    restore = 'git restore --source=HEAD -- state.json data/editorial_queue.json data/editorial_history.json'
    assert restore in text
    assert text.index('Run tests') < text.index(restore) < text.index(RUNTIME_COMMAND)


def test_workflow_persists_only_if_monitor_step_was_not_skipped():
    text = _workflow_text()
    assert 'id: monitor' in text
    assert "steps.monitor.outcome != 'skipped'" in text
