from src.managed_sources import TIER1_TELEGRAM_SOURCES


def test_seven_tier1_telegram_lanes_are_configured():
    assert len(TIER1_TELEGRAM_SOURCES) == 7
