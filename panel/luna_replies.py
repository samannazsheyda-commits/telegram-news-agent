from __future__ import annotations

import re

CONFIRMED_ACK_FA = "چشم، انجام شد."
_NO_RESULT_FA = "نتیجه قابل تأییدی نگرفتم؛ کوتاه‌تر بگو چه کاری انجام بدهم."

_SUCCESS_CLAIM_RE = re.compile(
    r"انجام\s*شد|با\s*موفقیت|اجرا\s*شد|ذخیره\s*شد|تغییر\s*کرد|منتشر\s*شد|حذف\s*شد|اضافه\s*شد|\bdone\b",
    re.IGNORECASE,
)


def claims_success(text: str) -> bool:
    return bool(_SUCCESS_CLAIM_RE.search(str(text or "")))


def _text(value) -> str:
    return str(value or "").strip()


def _story_lines(stories: list, limit: int = 6) -> list[str]:
    lines = []
    for story in list(stories or [])[:limit]:
        if not isinstance(story, dict):
            continue
        title = _text(story.get("title") or story.get("original_title"))
        source = _text(story.get("source"))
        if title:
            lines.append(f"• {title}" + (f" ({source})" if source else ""))
    return lines


def summarize_read(name: str, result: dict) -> str:
    """Human Persian content for a successful read, used when the model gave no final text."""
    if name == "list_sources":
        sources = [row for row in result.get("sources") or [] if isinstance(row, dict)]
        if not sources:
            return "منبعی با این مشخصات پیدا نشد."
        total = max(int(result.get("count") or 0), len(sources))
        active = [_text(row.get("name")) for row in sources if row.get("active")]
        inactive = [_text(row.get("name")) for row in sources if not row.get("active")]
        parts = [f"{total} منبع پیدا شد."]
        if active:
            parts.append("فعال: " + "، ".join(active[:30]))
        if inactive:
            parts.append("غیرفعال: " + "، ".join(inactive[:15]))
        shown = min(len(active), 30) + min(len(inactive), 15)
        if total > shown:
            parts.append(f"و {total - shown} منبع دیگر.")
        return "\n".join(parts)
    if name == "get_story":
        story = result.get("story") if isinstance(result.get("story"), dict) else {}
        title = _text(story.get("title") or story.get("original_title"))
        summary = _text(story.get("summary"))
        source = _text(story.get("source"))
        head = f"«{title}»" + (f" — {source}" if source else "")
        return f"{head}\n{summary}" if summary and summary != title else head
    if name in {"search_stories", "list_recent_published"}:
        lines = _story_lines(result.get("stories") or [])
        if not lines:
            return "خبری با این مشخصات پیدا نشد."
        label = "خبرهای منتشرشده اخیر" if name == "list_recent_published" else "خبرهای پیدا‌شده"
        return f"{label}:\n" + "\n".join(lines)
    if name == "diagnose_newsroom":
        return (
            f"امروز {int(result.get('daily_published') or 0)} خبر منتشر شده"
            f"؛ آماده: {int(result.get('ready') or 0)}، در انتظار: {int(result.get('waiting') or 0)}"
            f"، خطای منبع: {int(result.get('sources_failed') or 0)}، خطای انتشار: {int(result.get('publish_failed') or 0)}."
            + (f"\n{_text(result.get('reason'))}" if _text(result.get("reason")) else "")
        )
    if name == "inspect_panel_state":
        return (
            f"صف بررسی: {int(result.get('review_count') or 0)}، زنده: {int(result.get('live_count') or 0)}"
            f"، تاریخچه: {int(result.get('history_count') or 0)}، منابع: {int(result.get('sources_count') or 0)}."
        )
    if name == "builder_ci_status":
        if result.get("ci_green"):
            return "CI سبز است."
        return _text(result.get("message")) or "CI هنوز کامل سبز نیست."
    return _text(result.get("message"))


def compose_reply(model_text: str, executed: list[tuple[str, dict]]) -> str:
    """Final conversational reply; never reports success when every execution failed."""
    reply = _text(model_text)
    successes = [(name, result) for name, result in executed if result.get("ok")]
    failures = [(name, result) for name, result in executed if not result.get("ok")]
    if failures and not successes and (not reply or claims_success(reply)):
        messages = []
        for _, result in failures:
            message = _text(result.get("message")) or "عملیات ناموفق بود."
            if message not in messages:
                messages.append(message)
        return " ".join(messages)
    if reply:
        return reply
    summaries = []
    for name, result in successes:
        summary = summarize_read(name, result)
        if summary and summary not in summaries:
            summaries.append(summary)
    if summaries:
        return "\n\n".join(summaries)
    return _NO_RESULT_FA
