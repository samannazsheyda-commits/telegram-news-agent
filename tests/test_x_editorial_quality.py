from src.runtime_v10 import _quality_parse_x


def _payload(text: str, post_id: str = "1", handle: str = "TankerTrackers") -> dict:
    return {
        "code": 200,
        "results": [{
            "type": "status",
            "id": post_id,
            "text": text,
            "created_at": "Sun Sep 06 05:00:00 +0000 2026",
            "author": {"screen_name": handle},
            "url": f"https://x.com/{handle}/status/{post_id}",
        }],
    }


def test_context_dependent_x_fragment_is_rejected():
    text = (
        "The countries covered by these figures are Saudi Arabia, Iraq, Iran, Kuwait, Oman, UAE and Qatar. "
        "Although most of them may recover in the coming months, Iran's 1.68 million bpd baseline exports "
        "will likely remain near zero for the foreseeable future."
    )
    items = _quality_parse_x(_payload(text), "TankerTrackers", "@TankerTrackers")
    assert items == []


def test_jason_brodsky_contextless_this_comment_is_rejected():
    text = "Looks like the IRGC made this up."
    items = _quality_parse_x(_payload(text, "2096640287695048713", "JasonMBrodsky"), "Jason Brodsky", "@JasonMBrodsky")
    assert items == []


def test_contextless_pronoun_opening_is_rejected_even_when_iran_is_named_later():
    text = "This appears to be false, despite what the IRGC claimed earlier."
    items = _quality_parse_x(_payload(text, "4", "JasonMBrodsky"), "Jason Brodsky", "@JasonMBrodsky")
    assert items == []


def test_report_feature_headline_is_rejected():
    text = "The risky mission to clear mines from the Strait of Hormuz"
    items = _quality_parse_x(_payload(text, "2", "FT"), "Financial Times", "@FT")
    assert items == []


def test_concrete_fresh_event_still_passes():
    text = "Iran says three minesweepers entered the Strait of Hormuz on Sunday morning."
    items = _quality_parse_x(_payload(text, "3"), "TankerTrackers", "@TankerTrackers")
    assert len(items) == 1


def test_explicit_this_noun_event_still_passes():
    text = "This Iranian missile attack struck a military facility near Doha, officials said."
    items = _quality_parse_x(_payload(text, "5", "Reuters"), "Reuters", "@Reuters")
    assert len(items) == 1
