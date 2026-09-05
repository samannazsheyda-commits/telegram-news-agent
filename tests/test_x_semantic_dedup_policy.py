from src import runtime as base
from src import runtime_v3 as v3
from src.sources import NewsItem


def _item(key, source, title, summary=""):
    return NewsItem(
        key,
        source,
        title,
        summary,
        f"https://x.com/example/status/{key}",
        "Sat, 05 Sep 2026 14:00:00 GMT",
    )


def test_x_outlets_do_not_bypass_semantic_dedup(monkeypatch):
    first = _item(
        "1",
        "Reuters / X",
        "Trump says the United States destroyed Iran nuclear sites and will strike again if rebuilt",
    )
    duplicate = _item(
        "2",
        "CNN / X",
        "Trump says US obliterated Iranian nuclear facilities and would attack again if Tehran rebuilds them",
    )

    monkeypatch.setattr(v3, "_policy_installed", False)
    monkeypatch.setattr(v3, "_original_recent_duplicate", lambda item, refs: True)
    v3.install_x_publish_all_policy()

    assert base._is_recent_duplicate(duplicate, [first]) is True
