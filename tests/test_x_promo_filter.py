from src.fresh_x import parse_fxtwitter_timeline


def _payload(text: str, post_id: str = "2096249047258366124"):
    return {
        "code": 200,
        "results": [
            {
                "type": "status",
                "id": post_id,
                "created_at": "Sat Sep 05 16:00:00 +0000 2026",
                "author": {"screen_name": "FT"},
                "url": f"https://x.com/FT/status/{post_id}",
                "text": text,
            }
        ],
    }


def test_fresh_x_rejects_event_promo_about_iran():
    text = (
        "Former US Director of National Intelligence Avril Haines discusses the current geopolitical "
        "challenges and security concerns regarding Iran and the US military, in conversation with FT "
        "editor Roula Khalaf. Catch their FT Weekend Festival session:"
    )
    assert parse_fxtwitter_timeline(_payload(text), "Financial Times", "@FT") == []


def test_fresh_x_keeps_real_breaking_iran_news():
    text = "US forces struck three Iranian crude oil tankers after IRGC missiles targeted two US Navy warships, CENTCOM says."
    items = parse_fxtwitter_timeline(_payload(text, "2096249047258366125"), "Financial Times", "@FT")
    assert len(items) == 1
    assert items[0].title == text
