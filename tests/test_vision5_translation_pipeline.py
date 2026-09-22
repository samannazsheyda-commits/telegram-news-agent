from __future__ import annotations

import pytest


class Translator:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def translate(self, *, title: str, body: str, target_language: str):
        self.calls.append({"title": title, "body": body, "target_language": target_language})
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _story(title="English title", body="English body"):
    return {"id": "story-1", "original_title": title, "original_text": body}


def test_persian_source_copy_skips_google_and_is_review_ready():
    from bikhabar_v5.translation import TranslationPipeline

    google = Translator([])
    result = TranslationPipeline(google=google).translate_google(
        _story("عنوان فارسی", "متن کامل فارسی")
    )

    assert google.calls == []
    assert result == {
        "provider": "source_persian",
        "title": "عنوان فارسی",
        "body": "متن کامل فارسی",
    }


def test_google_translation_retries_one_story_without_blocking_success():
    from bikhabar_v5.translation import TranslationPipeline

    google = Translator(
        [
            RuntimeError("temporary timeout"),
            {"title": "عنوان فارسی", "body": "متن فارسی خبر"},
        ]
    )
    result = TranslationPipeline(google=google, max_attempts=2).translate_google(_story())

    assert result["provider"] == "google"
    assert result["title"] == "عنوان فارسی"
    assert len(google.calls) == 2


def test_google_failure_fails_closed_and_does_not_silently_use_luna():
    from bikhabar_v5.translation import TranslationError, TranslationPipeline

    google = Translator([RuntimeError("down"), RuntimeError("still down")])
    luna = Translator([{"title": "نسخه لونا", "body": "متن لونا"}])

    with pytest.raises(TranslationError, match="Google translation failed"):
        TranslationPipeline(google=google, luna=luna, max_attempts=2).translate_google(_story())

    assert luna.calls == []


def test_luna_is_an_explicit_alternate_and_final_copy_selection_is_exact():
    from bikhabar_v5.translation import TranslationPipeline, select_final_copy

    google = Translator([{"title": "ترجمه گوگل", "body": "متن گوگل"}])
    luna = Translator([{"title": "نسخه لونا", "body": "متن لونا"}])
    pipeline = TranslationPipeline(google=google, luna=luna)
    google_copy = pipeline.translate_google(_story())
    luna_copy = pipeline.translate_luna(_story())
    stored = {
        "google_title": google_copy["title"],
        "google_body": google_copy["body"],
        "luna_title": luna_copy["title"],
        "luna_body": luna_copy["body"],
    }

    assert select_final_copy(stored, "google") == ("ترجمه گوگل", "متن گوگل")
    assert select_final_copy(stored, "luna") == ("نسخه لونا", "متن لونا")
    assert len(luna.calls) == 1


def test_non_persian_provider_output_is_rejected():
    from bikhabar_v5.translation import TranslationError, TranslationPipeline

    google = Translator([{"title": "Still English", "body": "Not Persian"}])

    with pytest.raises(TranslationError, match="usable Persian"):
        TranslationPipeline(google=google).translate_google(_story())


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, *, params, timeout, headers):
        self.calls.append(
            {"url": url, "params": params, "timeout": timeout, "headers": headers}
        )
        return FakeResponse(self.responses.pop(0))


def test_google_client_translates_title_and_body_with_explicit_timeout():
    from bikhabar_v5.google_translation import GoogleTranslateClient

    session = FakeSession(
        [
            [[["عنوان فارسی", "English title", None, None]]],
            [[["متن فارسی", "English body", None, None]]],
        ]
    )

    result = GoogleTranslateClient(session=session, timeout_seconds=7).translate(
        title="English title", body="English body", target_language="fa"
    )

    assert result == {"title": "عنوان فارسی", "body": "متن فارسی"}
    assert [call["params"]["q"] for call in session.calls] == [
        "English title",
        "English body",
    ]
    assert all(call["timeout"] == 7 for call in session.calls)
    assert all(call["params"]["tl"] == "fa" for call in session.calls)
    assert all(call["params"]["sl"] == "auto" for call in session.calls)


def test_google_client_joins_multiple_translation_segments_and_skips_empty_body():
    from bikhabar_v5.google_translation import GoogleTranslateClient

    session = FakeSession(
        [[[["سلام ", "Hello ", None, None], ["دنیا", "world", None, None]]]]
    )

    result = GoogleTranslateClient(session=session).translate(
        title="Hello world", body="", target_language="fa"
    )

    assert result == {"title": "سلام دنیا", "body": ""}
    assert len(session.calls) == 1


def test_google_client_rejects_malformed_payload():
    from bikhabar_v5.google_translation import GoogleTranslateClient

    session = FakeSession([{"unexpected": True}])

    with pytest.raises(RuntimeError, match="malformed"):
        GoogleTranslateClient(session=session).translate(
            title="English title", body="", target_language="fa"
        )
