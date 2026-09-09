import json
from pathlib import Path

from src.managed_sources import managed_source_rows


def test_system_telegram_channel_dedupes_matching_custom_row(tmp_path: Path):
    custom = tmp_path / 'custom.json'
    custom.write_text(json.dumps([{'id':'custom-tabz','kind':'telegram','name':'Tabz custom','channel':'tabzlive','active':True}]), encoding='utf-8')
    overrides = tmp_path / 'overrides.json'
    overrides.write_text('{}', encoding='utf-8')
    rows = managed_source_rows(custom_path=custom, overrides_path=overrides)
    assert sum(1 for row in rows if row.get('kind') == 'telegram' and str(row.get('channel')).lower() == 'tabzlive') == 1
