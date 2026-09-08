from pathlib import Path


def _workflow_text() -> str:
    return Path('.github/workflows/agent.yml').read_text(encoding='utf-8')


def test_workflow_keeps_manual_dispatch_and_runs_strict_ci():
    text = _workflow_text()
    assert 'workflow_dispatch:' in text
    assert 'pull_request:' in text
    assert 'python -m pytest -q' in text
    assert 'continue-on-error: true' not in text
    assert 'bash -n deploy/install-vps.sh' in text
    assert 'bash -n deploy/update-vps.sh' in text


def test_workflow_no_longer_schedules_or_runs_production_agent():
    text = _workflow_text()
    assert 'schedule:' not in text
    assert 'python -m src.newsroom_hybrid_runtime --monitor' not in text
    assert 'SESSION_SECONDS: "270"' not in text
    assert 'Persist runtime data' not in text


def test_successful_main_push_promotes_to_production_branch():
    text = _workflow_text()
    assert "github.event_name == 'push'" in text
    assert "github.ref == 'refs/heads/main'" in text
    assert 'HEAD:refs/heads/production --force' in text


def test_workflow_has_no_hardcoded_one_off_market_post():
    text = _workflow_text()
    assert 'publish_once_market' not in text
