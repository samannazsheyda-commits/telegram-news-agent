from datetime import datetime, timezone

from src.newsroom_eligibility import evaluate_eligibility
from src.newsroom_models import RawNewsItem
from src.newsroom_normalize import normalize_item


def _item(title: str, summary: str = "Iran missile forces announced a concrete operational change."):
    raw = RawNewsItem(
        source="Reuters",
        source_url="https://reuters.com/world/middle-east/example",
        source_item_id=title,
        published_at=datetime.now(timezone.utc).isoformat(),
        fetched_at=datetime.now(timezone.utc).isoformat(),
        title=title,
        summary=summary,
        media=[],
        source_priority="protected",
    )
    return normalize_item(raw)


def test_obvious_report_analysis_question_and_teaser_formats_are_rejected_before_ai():
    now = datetime.now(timezone.utc)
    titles = [
        "Analysis: Why Iran's missile strategy is changing",
        "Report: What we know about Iran's missile forces",
        "Why is Iran changing its missile posture?",
        "Iran missile update — read more",
        "گزارش: آنچه درباره تحولات موشکی ایران می‌دانیم",
    ]
    for title in titles:
        result = evaluate_eligibility(_item(title), now)
        assert result.eligible is False, title
        assert result.reason in {"filtered_question_or_article", "filtered_incomplete_or_teaser"}, title
