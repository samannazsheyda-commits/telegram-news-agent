from src.fresh_x import parse_fxtwitter_timeline


def _payload(text: str, post_id: str = "1") -> dict:
    return {
        "code": 200,
        "results": [{
            "type": "status",
            "id": post_id,
            "text": text,
            "created_at": "Sun Sep 06 05:00:00 +0000 2026",
            "author": {"screen_name": "TankerTrackers"},
            "url": f"https://x.com/TankerTrackers/status/{post_id}",
        }],
    }


def test_context_dependent_x_fragment_is_rejected():
    text = (
        "The countries covered by these figures are Saudi Arabia, Iraq, Iran, Kuwait, Oman, UAE and Qatar. "
        "Although most of them may recover in the coming months, Iran's 1.68 million bpd baseline exports "
        "will likely remain near zero for the foreseeable future."
    )
    items = parse_fxtwitter_timeline(_payload(text), "TankerTrackers", "@TankerTrackers")
    assert items == []


def test_report_feature_headline_is_rejected():
    payload = _payload("The risky mission to clear mines from the Strait of Hormuz", "2")
    payload["results"][0]["author"]["screen_name"] = "FT"
    payload["results"][0]["url"] = "https://x.com/FT/status/2"
    items = parse_fxtwitter_timeline(payload, "Financial Times", "@FT")
    assert items == []


def test_concrete_fresh_event_still_passes():
    text = "Iran says three minesweepers entered the Strait of Hormuz on Sunday morning."
    items = parse_fxtwitter_timeline(_payload(text, "3"), "TankerTrackers", "@TankerTrackers")
    assert len(items) == 1
