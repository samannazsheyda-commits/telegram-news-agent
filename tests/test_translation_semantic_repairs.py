from src.services import _repair_news_idioms


def test_nuclear_deal_bomb_capability_headline_is_rewritten_for_meaning():
    source = (
        "Top US official says there may not be a nuclear deal with Iran, "
        "but ability to build bomb may be destroyed"
    )
    bad_literal = (
        "یک مقام ارشد آمریکایی می‌گوید ممکن است توافق هسته‌ای با ایران حاصل نشود، "
        "اما توانایی ساخت بمب ممکن است از بین برود"
    )

    assert _repair_news_idioms(source, bad_literal) == (
        "یک مقام ارشد آمریکایی: ممکن است توافق هسته‌ای با ایران به‌زودی حاصل نشود، "
        "اما آمریکا می‌تواند توان ایران برای ساخت سلاح هسته‌ای را از بین ببرد"
    )
