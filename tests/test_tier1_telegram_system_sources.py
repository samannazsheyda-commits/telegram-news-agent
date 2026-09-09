from pathlib import Path

from src import managed_sources


def test_tier1_telegram_sources_exist_even_when_custom_file_is_empty(tmp_path: Path):
    custom = tmp_path / 'custom_sources.json'
    custom.write_text('[]\n', encoding='utf-8')
    overrides = tmp_path / 'source_overrides.json'
    overrides.write_text('{}\n', encoding='utf-8')

    rows = managed_sources.managed_source_rows(custom_path=custom, overrides_path=overrides)
    telegram = [row for row in rows if row.get('kind') == 'telegram']
    channels = {row.get('channel') for row in telegram}

    assert {'tabzlive', 'rnintel', 'Middle_East_Spectator', 'ClashReport'} <= channels
    assert all(row.get('system') is True for row in telegram)
