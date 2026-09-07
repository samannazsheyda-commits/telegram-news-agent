from src.newsroom_models import RawNewsItem
from src.newsroom_normalize import normalize_item


def raw(title: str, summary: str = "", source: str = "Reuters") -> RawNewsItem:
    return RawNewsItem(
        source=source,
        source_url="https://example.com/story",
        source_item_id="1",
        published_at="2026-09-07T12:00:00+00:00",
        fetched_at="2026-09-07T12:01:00+00:00",
        title=title,
        summary=summary,
    )


def test_normalizes_priority_actors():
    cases = [
        ("Donald Trump posted about Iran", "Donald Trump"),
        ("CENTCOM says 92 vessels were redirected", "CENTCOM"),
        ("White House says Strait of Hormuz is under US control", "White House"),
        ("Mohsen Rezaei announces restricted zone", "Mohsen Rezaei"),
        ("Abbas Araghchi comments on negotiations", "Abbas Araghchi"),
    ]
    for title, actor in cases:
        assert actor in normalize_item(raw(title)).actors


def test_normalizes_locations():
    item = normalize_item(raw("Iran action in Strait of Hormuz as Spain and Jordan respond"))
    assert "Iran" in item.locations
    assert "Strait of Hormuz" in item.locations
    assert "Spain" in item.locations
    assert "Jordan" in item.locations


def test_normalizes_actions_and_numbers():
    item = normalize_item(raw(
        "CENTCOM redirected 92 commercial vessels, disabled 3 and boarded 2 in Strait of Hormuz"
    ))
    assert "redirect_vessels" in item.actions
    assert item.numeric_facts == ["92", "3", "2"]


def test_distinguishes_airspace_close_and_reopen():
    closed = normalize_item(raw("Spain closes airspace to US warplanes"))
    reopened = normalize_item(raw("Iran partially reopens airspace to international flights"))
    assert "close_airspace" in closed.actions
    assert "reopen_airspace" in reopened.actions


def test_normalizes_missile_interception_and_restricted_zone():
    intercept = normalize_item(raw("Jordan intercepts Iranian missiles over its airspace"))
    restriction = normalize_item(raw("Iran announces a new restricted zone outside Strait of Hormuz"))
    assert "intercept" in intercept.actions
    assert "announce_restricted_zone" in restriction.actions


def test_normalization_never_suppresses_item():
    original = raw("A completely unfamiliar but valid Iran-related report")
    normalized = normalize_item(original)
    assert normalized is not None
    assert normalized.raw == original
    assert normalized.normalized_text
