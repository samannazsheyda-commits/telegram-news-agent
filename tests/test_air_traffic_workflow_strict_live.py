from pathlib import Path


def test_manual_air_traffic_workflow_uses_strict_live_guard_and_luna():
    workflow = Path(".github/workflows/air-traffic.yml").read_text(encoding="utf-8")
    assert "run: python -m src.air_traffic_publish_guard --publish" in workflow
    assert "OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}" in workflow
    assert 'OPENAI_MODEL: "gpt-5.6-luna"' in workflow
    assert 'AI_NEWSROOM_MODE: "required"' in workflow
