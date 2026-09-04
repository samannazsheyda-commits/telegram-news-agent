from pathlib import Path


def test_workflow_runs_bounded_monitor_and_keeps_manual_dispatch():
    text = Path('.github/workflows/agent.yml').read_text(encoding='utf-8')
    assert 'workflow_dispatch:' in text
    assert 'python -m src.runtime --monitor' in text
    assert 'timeout-minutes:' in text
    assert 'concurrency:' in text
    assert 'cancel-in-progress: false' in text
    assert 'data/editorial_queue.json' in text
    assert 'data/editorial_history.json' in text
