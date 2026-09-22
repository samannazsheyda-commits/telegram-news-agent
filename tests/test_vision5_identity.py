from __future__ import annotations


def test_canonical_url_removes_tracking_and_normalizes_origin():
    from bikhabar_v5.identity import canonicalize_url

    left = "HTTPS://Example.COM:443/news/42/?utm_source=x&b=2&a=1#comments"
    right = "https://example.com/news/42?a=1&b=2"

    assert canonicalize_url(left) == "https://example.com/news/42?a=1&b=2"
    assert canonicalize_url(left) == canonicalize_url(right)


def test_story_fingerprint_is_stable_for_equivalent_story_inputs():
    from bikhabar_v5.identity import story_fingerprint

    first = story_fingerprint(
        source="Clash Report",
        source_url="https://example.com/item/7?utm_medium=social",
        original_title="  Iran   announces a new measure  ",
        published_at_source="2026-09-22T10:30:00+00:00",
    )
    second = story_fingerprint(
        source="clash report",
        source_url="https://EXAMPLE.com/item/7",
        original_title="Iran announces a new measure",
        published_at_source="2026-09-22T10:30:00Z",
    )

    assert first == second
    assert len(first) == 64


def test_story_fingerprint_separates_distinct_source_items():
    from bikhabar_v5.identity import story_fingerprint

    first = story_fingerprint(
        source="Reuters",
        source_url="",
        original_title="First event",
        published_at_source="2026-09-22T10:30:00Z",
    )
    second = story_fingerprint(
        source="Reuters",
        source_url="",
        original_title="Second event",
        published_at_source="2026-09-22T10:30:00Z",
    )

    assert first != second


def test_ensure_story_identity_fills_missing_fingerprint_without_mutating_input():
    from bikhabar_v5.identity import ensure_story_identity

    original = {
        "source": "Reuters",
        "source_url": "https://example.com/a/?utm_source=x",
        "original_title": "A headline",
        "published_at_source": "2026-09-22T10:30:00Z",
    }
    prepared = ensure_story_identity(original)

    assert prepared is not original
    assert prepared["source_url"] == "https://example.com/a"
    assert len(prepared["fingerprint"]) == 64
    assert "fingerprint" not in original
