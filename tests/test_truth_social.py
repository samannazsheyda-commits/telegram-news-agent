from src.truth_social import parse_truth_status


def status(post_id, *, content="", description="", media_url="https://cdn.example/image.jpg"):
    attachments = []
    if media_url:
        attachments.append({"url": media_url, "description": description, "type": "image"})
    return {
        "id": post_id,
        "created_at": "2026-09-07T14:43:00.000Z",
        "content": content,
        "url": f"https://truthsocial.com/@realDonaldTrump/{post_id}",
        "media_attachments": attachments,
        "reblog": None,
    }


def test_image_only_iran_related_post_is_ingested_with_media():
    item = parse_truth_status(status("117230287806050615", description="Iran navy image"))
    assert item is not None
    assert item.source == "Truth Social"
    assert item.source_item_id == "117230287806050615"
    assert item.source_priority == "protected"
    assert item.media == ["https://cdn.example/image.jpg"]


def test_text_post_about_hormuz_is_ingested():
    item = parse_truth_status(status("117230300000000001", content="<p>Update about the Strait of Hormuz.</p>", media_url=""))
    assert item is not None
    assert "Strait of Hormuz" in item.title


def test_unrelated_post_is_ignored():
    assert parse_truth_status(status("117230300000000002", content="<p>General update.</p>", media_url="")) is None


def test_different_truth_ids_remain_different_source_items():
    first = parse_truth_status(status("117230287806050615", description="Iran navy image"))
    second = parse_truth_status(status("117230287192828119", description="Iran navy image"))
    assert first is not None and second is not None
    assert first.source_item_id != second.source_item_id
    assert first.source_url != second.source_url
