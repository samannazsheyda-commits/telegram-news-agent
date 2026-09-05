from src.dedup_strict import is_strict_duplicate_story
from src.editorial_rules import is_low_value_company_news
from src.sources import NewsItem


def _item(key, source, title, summary=""):
    return NewsItem(key, source, title, summary, f"https://example.com/{key}", "Sat, 05 Sep 2026 17:40:00 GMT")


def test_khatam_warning_is_not_duplicate_of_us_tanker_strike():
    khatam = _item(
        "khatam",
        "تبز لایو / Telegram",
        "Iran's Khatam al-Anbiya Central HQ warns strikes on US Navy vessels will intensify and could expand if Washington continues targeting Iranian ships and enforcing the naval blockade",
    )
    tanker = _item(
        "tanker",
        "Reuters / X",
        "US military strikes three Iranian crude oil carriers after IRGC missiles at US warships",
    )
    assert not is_strict_duplicate_story(khatam, tanker)


def test_israel_katz_energy_threat_is_not_duplicate_of_us_tanker_strike():
    katz = _item(
        "katz",
        "Emanuel Fabian / X",
        "Israel Katz says if Iran attacks Israel, the military will strike all Iranian infrastructure including energy infrastructure",
    )
    tanker = _item(
        "tanker",
        "Reuters / X",
        "US military strikes three Iranian crude oil carriers after IRGC missiles at US warships",
    )
    assert not is_strict_duplicate_story(katz, tanker)


def test_new_us_sanctions_are_not_duplicate_of_tanker_strike():
    sanctions = _item(
        "sanctions",
        "State Department Spokesperson / X",
        "US announces new Treasury sanctions targeting a Turkey-based bank over Iranian financial networks",
    )
    tanker = _item(
        "tanker",
        "Reuters / X",
        "US military strikes three Iranian crude oil carriers after IRGC missiles at US warships",
    )
    assert not is_strict_duplicate_story(sanctions, tanker)


def test_easa_iran_airspace_warning_is_not_low_value_company_news():
    warning = _item(
        "easa",
        "Reuters",
        "EU aviation agency warns airlines should still avoid airspace over Iran after potential for continued military action",
        "EASA advised airlines to avoid Iranian airspace because of continuing security risks.",
    )
    assert not is_low_value_company_news(warning)


def test_updated_centcom_blockade_numbers_are_not_duplicate_of_older_numbers():
    old = _item(
        "old",
        "CENTCOM / X",
        "US Navy blockade of Iran has redirected 83 commercial vessels, disabled 3 and boarded 2 as of Aug. 30",
    )
    new = _item(
        "new",
        "CENTCOM / X",
        "US Navy blockade of Iran has redirected 86 commercial vessels, disabled 3 and boarded 2 as of Sept. 2",
    )
    assert not is_strict_duplicate_story(old, new)
