from src.sources import canonical_source


def test_clash_report_canonical_name_is_preserved_exactly():
    assert canonical_source("Clash Report") == "Clash Report"
    assert canonical_source("clash report") == "Clash Report"
    assert canonical_source("CLASH REPORT") == "Clash Report"
