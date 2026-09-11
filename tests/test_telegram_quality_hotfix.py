from datetime import datetime
from pathlib import Path

from src.newsroom_eligibility import evaluate_eligibility
from src.newsroom_models import RawNewsItem
from src.newsroom_normalize import normalize_item
from src.strict_translation import StrictTelegramNewsroomPublisher, translate_to_fa_strict


NOW = datetime.fromisoformat("2026-09-10T08:30:00+00:00")


def _raw(title: str, summary: str = "") -> RawNewsItem:
    return RawNewsItem(
        source="Middle East Spectator / Telegram",
        source_url="https://t.me/Middle_East_Spectator/12345",
        source_item_id="12345",
        published_at="2026-09-10T08:20:00+00:00",
        fetched_at="2026-09-10T08:20:02+00:00",
        title=title,
        summary=summary,
        media=[],
        source_priority="normal",
    )


def test_houthi_saudi_alert_without_iran_link_is_rejected():
    decision = evaluate_eligibility(
        normalize_item(_raw("Houthi drones target southern Saudi Arabia; air defenses intercept them")),
        NOW,
    )
    assert decision.eligible is False
    assert decision.reason == "not_iran_relevant"


def test_yemen_saudi_missile_event_without_iran_link_is_rejected():
    decision = evaluate_eligibility(
        normalize_item(_raw("Saudi Arabia intercepts missile launched from Yemen toward Jizan")),
        NOW,
    )
    assert decision.eligible is False
    assert decision.reason == "not_iran_relevant"


def test_regional_missile_explicitly_launched_from_iran_remains_eligible():
    decision = evaluate_eligibility(
        normalize_item(_raw("Saudi Arabia intercepts ballistic missile launched from Iran")),
        NOW,
    )
    assert decision.eligible is True


def test_hormuz_tanker_incident_remains_eligible():
    decision = evaluate_eligibility(
        normalize_item(_raw("Tanker reports explosion while transiting the Strait of Hormuz")),
        NOW,
    )
    assert decision.eligible is True


class _LingvaResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {"translation": "ترجمه ماشینی ضعیف ولی فارسی"}


class _LingvaSession:
    def get(self, *args, **kwargs):
        return _LingvaResponse()


def test_auto_publisher_does_not_fall_back_to_unverified_lingva_translation():
    item = normalize_item(_raw("Iran launched ballistic missiles"))
    publisher = StrictTelegramNewsroomPublisher(
        "token",
        "@bikhabaar",
        session=_LingvaSession(),
        translator=lambda _text: "",
    )
    assert publisher._message(item) == ""


def test_strict_translation_never_calls_mymemory_after_google_failures():
    calls = []

    class Response:
        text = "<html></html>"
        def raise_for_status(self):
            return None
        def json(self):
            return {"responseData": {"translatedText": "ترجمه نامعتبر"}}

    class Session:
        def get(self, url, **kwargs):
            calls.append(url)
            if "googleapis" in url:
                raise RuntimeError("google api unavailable")
            return Response()

    assert translate_to_fa_strict("Iran launched a missile", session=Session()) == ""
    assert all("mymemory" not in url for url in calls)


def test_scheduled_air_traffic_job_publishes_only_the_approved_validated_renderer():
    service = Path("deploy/bikhabar-air-traffic.service").read_text(encoding="utf-8")
    assert "-m src.air_traffic --publish" in service
    assert "iran-region-live-air-traffic.png" in service
    assert "Temporary safety gate" not in service


def test_vps_updater_keeps_two_second_news_polling():
    script = Path("deploy/update-vps.sh").read_text(encoding="utf-8")
    assert '"POLL_SECONDS=2"' in script
