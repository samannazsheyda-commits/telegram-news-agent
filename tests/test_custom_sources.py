from __future__ import annotations

from src.custom_sources import (
    XSource,
    discover_feed_url,
    normalize_x_handle,
    parse_public_feed,
    validate_website_source,
)


class FakeResponse:
    def __init__(self, text="", content=b"", status_code=200):
        self.text = text
        self.content = content or text.encode("utf-8")
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.responses.pop(0)


def test_explicit_rss_feed_is_used_before_discovery():
    source = validate_website_source("Example", "https://example.com", "https://example.com/feed.xml")
    assert source.feed_url == "https://example.com/feed.xml"
    assert source.status == "active"


def test_feed_discovery_reads_html_link_rel_alternate():
    html = '<html><head><link rel="alternate" type="application/rss+xml" href="/rss.xml"></head></html>'
    session = FakeSession([FakeResponse(text=html)])
    assert discover_feed_url("https://example.com/news", session=session) == "https://example.com/rss.xml"


def test_invalid_website_scheme_is_rejected():
    try:
        validate_website_source("Bad", "javascript:alert(1)")
    except ValueError as exc:
        assert str(exc) == "invalid_website_url"
    else:
        raise AssertionError("expected invalid URL")


def test_x_handle_is_normalized_to_at_handle():
    assert normalize_x_handle("https://x.com/BarakRavid") == "@BarakRavid"
    assert XSource.create("BarakRavid").handle == "@BarakRavid"


def test_public_feed_filters_non_iran_items():
    xml = b'''<rss><channel>
      <item><title>Iran launches new satellite</title><description>Iranian officials announced it.</description><link>https://example.com/iran</link><pubDate>Fri, 05 Sep 2026 10:00:00 GMT</pubDate></item>
      <item><title>Local sports result</title><description>A football match.</description><link>https://example.com/sport</link><pubDate>Fri, 05 Sep 2026 10:00:00 GMT</pubDate></item>
    </channel></rss>'''
    items = parse_public_feed(xml, "Example")
    assert len(items) == 1
    assert items[0].source == "Example"
    assert "Iran" in items[0].title
