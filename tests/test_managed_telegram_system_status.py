from src.managed_sources import system_source_definitions


def test_tier1_telegram_rows_are_realtime_system_sources():
    rows=[r for r in system_source_definitions() if r.get('kind')=='telegram']
    assert rows
    assert all(r.get('status')=='realtime' and r.get('system') is True for r in rows)
