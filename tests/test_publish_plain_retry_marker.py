from pathlib import Path


def test_publisher_has_plain_text_retry_path():
    text = Path('src/newsroom_publisher.py').read_text(encoding='utf-8')
    assert 'retry.pop("parse_mode", None)' in text
    assert '_plain_text' in text
