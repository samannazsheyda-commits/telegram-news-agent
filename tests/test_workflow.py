from pathlib import Path


RUNTIME_COMMAND = 'python -m src.runtime_v7 --monitor'


def test_workflow_runs_bounded_monitor_and_keeps_manual_dispatch():
    text = Path('.github/workflows/agent.yml').read_text(encoding='utf-8')
    assert 'workflow_dispatch:' in text
    assert RUNTIME_COMMAND in text
    assert 'timeout-minutes:' in text
    assert 'concurrency:' in text
    assert 'cancel-in-progress: false' in text
    assert 'data/editorial_queue.json' in text
    assert 'data/editorial_history.json' in text


def test_scheduled_run_refreshes_latest_main_before_monitor():
    text = Path('.github/workflows/agent.yml').read_text(encoding='utf-8')
    assert "if: github.event_name == 'schedule'" in text
    assert 'git fetch origin main' in text
    assert 'git reset --hard origin/main' in text
    assert text.index('git reset --hard origin/main') < text.index(RUNTIME_COMMAND)
