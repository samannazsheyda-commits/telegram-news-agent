from pathlib import Path

from src.urgent_output import normalize_urgent_message


def test_urgent_message_strips_raw_source_noise_and_english_tokens():
    raw = (
        '🛑 <b>RN Intel / Telegram: 🇾🇪 🇸🇦 BREAKING: هشدار در جنوب عربستان سعودی '
        '@Middle_East_Spectator</b>\n\n'
        '📌 <a href="https://example.com/source">لینک منبع خبر</a>\n\n'
        '📡 <a href="https://t.me/bikhabaar">بی‌خبر</a> ←\nمانیتور تحولات ایران'
    )
    cleaned = normalize_urgent_message(raw)
    assert 'RN Intel' not in cleaned
    assert 'Telegram' not in cleaned
    assert 'BREAKING' not in cleaned
    assert '@Middle_East_Spectator' not in cleaned
    assert '🇾🇪' not in cleaned
    assert '🇸🇦' not in cleaned
    assert 'آر‌اِن اینتل / تلگرام' in cleaned
    assert 'فوری' in cleaned
    assert '<a href="https://example.com/source">لینک منبع خبر</a>' in cleaned
    assert '<a href="https://t.me/bikhabaar">بی‌خبر</a>' in cleaned


def test_urgent_workflow_normalizes_every_text_message_before_send():
    workflow = Path('.github/workflows/urgent-broadcast.yml').read_text(encoding='utf-8')
    assert 'from src.urgent_output import normalize_urgent_message' in workflow
    assert "send_text(normalize_urgent_message(str(text)))" in workflow
