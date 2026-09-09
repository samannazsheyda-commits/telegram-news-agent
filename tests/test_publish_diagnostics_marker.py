from pathlib import Path


def test_publisher_contains_explicit_failure_marker():
    text = Path('src/newsroom_publisher.py').read_text(encoding='utf-8')
    assert 'TELEGRAM_PUBLISH_FAILED' in text
