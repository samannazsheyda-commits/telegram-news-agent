from src.services import split_message


def test_split_message_respects_limit_and_preserves_content():
    text = ("abc def ghi\n" * 50).strip()
    chunks = split_message(text, max_len=40)
    assert all(len(c) <= 40 for c in chunks)
    assert "".join(chunks).replace(" ", "").replace("\n", "") == text.replace(" ", "").replace("\n", "")
