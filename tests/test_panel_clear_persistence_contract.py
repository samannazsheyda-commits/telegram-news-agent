from pathlib import Path

WORKFLOW = Path('.github/workflows/panel-file-command.yml')


def test_pending_clear_ids_are_reapplied_after_merge():
    text = WORKFLOW.read_text(encoding='utf-8')
    assert "scope == 'pending'" in text
    assert "queue = [row for row in queue if str(row.get('id')) not in ids]" in text


def test_refresh_result_message_is_rendered_to_operator():
    js = Path('docs/newsroom-v1.js').read_text(encoding='utf-8')
    assert "result.message" in js
    assert "بروزرسانی" in js
