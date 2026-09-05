from src.oil import OilSnapshot, format_oil_lines
from src.sources import MarketSnapshot
import src.runtime_v2 as runtime


def _snapshot():
    snapshot = MarketSnapshot(221_060, 23_518_800)
    object.__setattr__(snapshot, "brent_usd", 96.28)
    object.__setattr__(snapshot, "wti_usd", 91.48)
    return snapshot


def test_market_output_forces_rtl_direction_on_every_visible_line():
    rendered = runtime._format_market_with_oil(_snapshot())
    visible_lines = [line for line in rendered.splitlines() if line.strip()]
    assert visible_lines
    assert all(line.startswith("\u200f") for line in visible_lines)


def test_brent_is_primary_bold_oil_benchmark_but_wti_is_secondary():
    lines = format_oil_lines(OilSnapshot(brent_usd=96.28, wti_usd=91.48))
    assert lines[0] == "🛢 <b>نفت برنت: $96.28 / بشکه</b>"
    assert lines[1] == "🛢 نفت WTI: $91.48 / بشکه"


def test_daily_oil_summary_emphasizes_brent_not_wti():
    brent = runtime._oil_daily_lines("نفت برنت", 90.0, 96.0, primary=True)
    wti = runtime._oil_daily_lines("نفت WTI", 90.0, 91.0, primary=False)
    assert all("<b>" in line for line in brent)
    assert all("<b>" not in line for line in wti)
