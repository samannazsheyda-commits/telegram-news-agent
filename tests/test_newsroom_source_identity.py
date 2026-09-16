from src.newsroom_source_identity import canonical_news_source


def test_clash_report_canonical_name_is_preserved_exactly():
    assert canonical_news_source("Clash Report") == "Clash Report"
    assert canonical_news_source("clash report") == "Clash Report"
    assert canonical_news_source("CLASH REPORT") == "Clash Report"
    assert canonical_news_source("@clashreport") == "Clash Report"
