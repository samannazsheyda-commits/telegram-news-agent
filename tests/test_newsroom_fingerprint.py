from src.newsroom_fingerprint import build_fingerprint, fingerprint_similarity
from src.newsroom_models import RawNewsItem
from src.newsroom_normalize import normalize_item


def make(title: str, source: str = "Reuters"):
    return normalize_item(RawNewsItem(
        source=source,
        source_url="https://example.com/story",
        source_item_id=source + title[:8],
        published_at="2026-09-07T12:00:00+00:00",
        fetched_at="2026-09-07T12:01:00+00:00",
        title=title,
    ))


def test_three_tanker_reports_share_structural_core():
    ap = build_fingerprint(make("U.S. military struck three Iranian oil tankers after attacks on Navy warships", "AP"))
    cnn = build_fingerprint(make("US forces strike 3 Iranian crude oil tankers after Iran targets two Navy ships", "CNN"))
    nyt = build_fingerprint(make("The U.S. struck three Iranian tankers in retaliation for attacks on two warships", "NYT"))
    assert fingerprint_similarity(ap, cnn) >= 0.75
    assert fingerprint_similarity(ap, nyt) >= 0.75


def test_hormuz_control_restriction_and_centcom_counts_are_distinct():
    control = build_fingerprint(make("White House says United States has total control of Strait of Hormuz"))
    restriction = build_fingerprint(make("Mohsen Rezaei announces new restricted zone outside Strait of Hormuz"))
    counts = build_fingerprint(make("CENTCOM redirected 92 commercial vessels, disabled 3 and boarded 2 in Strait of Hormuz"))
    assert fingerprint_similarity(control, restriction) < 0.75
    assert fingerprint_similarity(control, counts) < 0.75
    assert fingerprint_similarity(restriction, counts) < 0.75


def test_airspace_close_and_reopen_are_distinct():
    close = build_fingerprint(make("Spain closes airspace to US warplanes involved in Iran war"))
    reopen = build_fingerprint(make("Iran partially reopens airspace to international flights"))
    assert fingerprint_similarity(close, reopen) < 0.75


def test_jordan_interception_and_spain_airspace_closure_are_distinct():
    intercept = build_fingerprint(make("Jordan intercepts Iranian missiles over its airspace"))
    close = build_fingerprint(make("Spain closes airspace to US warplanes involved in Iran war"))
    assert fingerprint_similarity(intercept, close) < 0.75
