from src.dedup_strict import is_strict_duplicate_story
from src.sources import NewsItem


def _item(key, source, title, summary=""):
    return NewsItem(key, source, title, summary, f"https://example.com/{key}", "Fri, 05 Sep 2026 16:00:00 GMT")


def test_same_small_potatoes_quote_across_outlets_is_duplicate():
    a = _item(
        "a", "France 24",
        "Trump says war with Iran is small potatoes for America",
        "Trump described the conflict with Iran as small potatoes for the United States.",
    )
    b = _item(
        "b", "ABC News",
        "Trump says Iran war is small potatoes and not a big thing for the US",
        "Trump called the war with Iran small potatoes for America.",
    )
    assert is_strict_duplicate_story(a, b)


def test_same_tanker_strike_across_outlets_is_duplicate():
    a = _item(
        "a", "Reuters",
        "US military strikes three Iranian oil tankers after IRGC missiles at US warships",
        "CENTCOM says American forces disabled three Iranian crude oil carriers.",
    )
    b = _item(
        "b", "ABC News",
        "U.S. forces permanently disabled two Iranian oil tankers and destroyed another after IRGC launched ballistic missiles toward Navy warships",
        "Central Command said the attacks followed Iranian missiles at U.S. ships.",
    )
    assert is_strict_duplicate_story(a, b)


def test_israel_third_strike_warning_is_not_duplicate_of_us_tanker_attack():
    warning = _item(
        "warning", "France 24",
        "Israel ready to attack Iran a third time if necessary, defence minister says",
    )
    tanker = _item(
        "tanker", "Reuters",
        "US military strikes three Iranian oil tankers after IRGC missiles at US warships",
    )
    assert not is_strict_duplicate_story(warning, tanker)


def test_iaea_referral_is_not_duplicate_of_us_tanker_attack():
    iaea = _item(
        "iaea", "The Cradle",
        "US, Europe push IAEA resolution referring Iran to UN Security Council",
    )
    tanker = _item(
        "tanker", "Reuters",
        "US military strikes three Iranian oil tankers after IRGC missiles at US warships",
    )
    assert not is_strict_duplicate_story(iaea, tanker)


def test_netanyahu_warning_is_not_duplicate_of_us_tanker_attack():
    warning = _item(
        "netanyahu", "Clash Report",
        "Netanyahu on Iran: If Iran attacks us, they will absorb such a blow that I do not want to detail it.",
    )
    tanker = _item(
        "tanker", "Reuters",
        "US military strikes three Iranian oil tankers after IRGC missiles at US warships",
    )
    assert not is_strict_duplicate_story(warning, tanker)


def test_centcom_same_maritime_progress_in_english_and_persian_is_duplicate():
    english = _item(
        "centcom-en", "CENTCOM / X",
        "A U.S. Air Force F-35A stealth fighter jet patrols over regional waters as CENTCOM forces continue to enforce the maritime blockade against Iran. As of Sept. 6, U.S. forces have redirected 92 commercial vessels, disabled 3 and boarded 2 to ensure strict compliance.",
    )
    persian = _item(
        "centcom-fa", "CENTCOM Farsi / X",
        "یک فروند جت جنگنده رادارگریز F-35A نیروی هوایی ایالات متحده در حالی که نیروهای سنتکام همچنان به اجرای محاصره دریایی علیه ایران ادامه می‌دهند، بر فراز آب‌های منطقه‌ای گشت‌زنی می‌کند. تا 15 شهریور، نیروهای آمریکایی 92 کشتی تجاری را تغییر مسیر داده، 3 کشتی را غیرفعال کرده و 2 کشتی را توقیف کرده‌اند تا از رعایت دقیق این قوانین اطمینان حاصل کنند.",
    )
    assert is_strict_duplicate_story(english, persian)


def test_centcom_changed_maritime_counter_is_a_new_update_across_languages():
    english = _item(
        "centcom-en", "CENTCOM / X",
        "CENTCOM says U.S. forces have redirected 92 commercial vessels, disabled 3 and boarded 2 while enforcing the maritime blockade against Iran.",
    )
    persian_new = _item(
        "centcom-fa-new", "CENTCOM Farsi / X",
        "سنتکام اعلام کرد نیروهای آمریکایی در اجرای محاصره دریایی علیه ایران 93 کشتی تجاری را تغییر مسیر داده، 3 کشتی را غیرفعال کرده و 2 کشتی را توقیف کرده‌اند.",
    )
    assert not is_strict_duplicate_story(english, persian_new)
