from __future__ import annotations

import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

from .formatters import _red_story_marker, format_market, format_news, format_truth
from .services import load_state, save_state, send_telegram, translate_to_fa
from .sources import NewsItem, fetch_market_snapshot, fetch_news_items, fetch_truth_posts, is_iran_related

STATE_PATH = os.environ.get("STATE_PATH", "state.json")
MARKET_INTERVAL = timedelta(hours=2)
TEHRAN = ZoneInfo("Asia/Tehran")

ARTICLE_PATTERNS = (
    "analysis:", "opinion:", "explainer", "what to know", "what we know", "why ",
    "how can", "how could", "how might", "experts explain", "experts say", "expert says",
    "three experts", "what does", "what could", "could mean", "may mean", "might mean",
    "timeline of", "a look at", "inside the", "the case for", "commentary", "editorial",
    "in depth", "in-depth", "factbox", "fact check", "backgrounder", "guide to", "feature:",
    "تحلیل", "یادداشت", "کارشناسان", "چرا ", "چگونه ", "آنچه باید بدانید", "مروری بر",
)
VAGUE_PATTERNS = (
    "may consider", "might consider", "could consider", "is considering", "are considering",
    "reviewing options", "under review", "expected soon", "expected to", "could happen",
    "may happen", "might happen", "possible that", "possibility of", "speculation",
    "در حال بررسی", "ممکن است", "احتمال دارد", "انتظار می‌رود", "پیش‌بینی",
)
MAJOR_EVENT_TERMS = (
    "attack", "attacks", "attacked", "strike", "strikes", "struck", "missile", "missiles",
    "drone", "drones", "explosion", "blast", "bombing", "killed", "dead", "wounded",
    "intercepted", "interception", "air defense", "air defence", "sirens", "siren", "seized", "sank", "sinking", "collision", "fire", "war", "ceasefire",
    "sanction", "sanctions", "designates", "blacklists", "agreement", "deal", "signed",
    "suspend", "suspended", "resume", "resumed", "talks begin", "talks began", "negotiations begin",
    "withdraws", "expels", "orders", "announces", "confirms", "declares", "closes airspace",
    "closed airspace", "reopens airspace", "airspace closed", "airspace reopened", "notam",
    "flight ban", "flights cancelled", "evacuation", "nuclear site", "uranium", "enrichment",
    "security council", "iaea", "board of governors", "refer iran", "referral", "resolution",
    "hormuz", "tanker", "حمله", "موشک", "پهپاد", "انفجار", "بمباران", "کشته", "مجروح",
    "رهگیری", "پدافند", "آژیر", "توقیف", "غرق", "آتش‌بس", "تحریم", "توافق", "مذاکرات متوقف",
    "مذاکرات از سر گرفته", "مذاکرات آغاز", "اعلام کرد", "تأیید کرد", "دستور داد",
    "حریم هوایی بسته", "حریم هوایی باز", "نوتام", "لغو پرواز", "ممنوعیت پرواز", "تخلیه",
    "شورای امنیت", "آژانس بین‌المللی انرژی اتمی", "شورای حکام", "قطعنامه", "ارجاع پرونده",
    "هسته‌ای", "اورانیوم", "غنی‌سازی", "هرمز", "نفتکش",
)
STORY_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "to", "of", "for", "in", "on", "at", "by",
    "with", "from", "as", "is", "are", "was", "were", "be", "been", "being", "has", "have",
    "had", "says", "said", "saying", "will", "would", "could", "may", "might", "its", "their",
    "his", "her", "this", "that", "after", "before", "about", "over", "under", "new", "latest",
    "و", "در", "به", "از", "با", "برای", "که", "این", "آن", "یک", "را", "است", "شد", "می",
}
SPEAKERS = {
    "vance": ("jd vance", "j.d. vance", "vance"),
    "trump": ("donald trump", "trump"),
    "rubio": ("marco rubio", "rubio"),
    "araghchi": ("abbas araghchi", "araghchi", "عراقچی"),
    "ghalibaf": ("ghalibaf", "قالیباف"),
    "rezaei": ("mohsen rezaei", "rezaei", "محسن رضایی"),
    "bessent": ("scott bessent", "bessent"),
}
STATEMENT_TERMS = (" says ", " said ", " tells ", " told ", " interview", " remarks", " گفت", " اعلام کرد")


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def _published_dt(value: str) -> datetime | None:
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _published_today(value: str, now: datetime) -> bool:
    published = _published_dt(value)
    return bool(published and published.astimezone(TEHRAN).date() == now.astimezone(TEHRAN).date())


def _market_quiet_hours(now: datetime) -> bool:
    return 0 <= now.astimezone(TEHRAN).hour < 8


def is_important_news(title: str, summary: str) -> bool:
    title_l = re.sub(r"\s+", " ", (title or "").lower()).strip()
    summary_l = re.sub(r"\s+", " ", (summary or "").lower()).strip()
    combined = f"{title_l} {summary_l}".strip()
    if not combined or any(p in title_l for p in ARTICLE_PATTERNS) or any(p in title_l for p in VAGUE_PATTERNS):
        return False
    if ("?" in title_l or "؟" in title_l) and not any(term in title_l for term in MAJOR_EVENT_TERMS):
        return False
    return any(term in combined for term in MAJOR_EVENT_TERMS)


def _story_tokens(item: NewsItem) -> set[str]:
    tokens = re.findall(r"[a-z0-9\u0600-\u06ff]+", f"{item.title} {item.summary}".lower())
    return {t for t in tokens if len(t) > 2 and t not in STORY_STOPWORDS}


def _same_story(left: NewsItem, right: NewsItem) -> bool:
    a, b = _story_tokens(left), _story_tokens(right)
    if not a or not b:
        return False
    common = a & b
    return len(common) >= 4 and len(common) / min(len(a), len(b)) >= 0.50


def _speaker_key(item: NewsItem) -> str | None:
    text = f" {item.title.lower()} "
    for key, aliases in SPEAKERS.items():
        if any(alias in text for alias in aliases):
            return key
    return None


def _is_statement(item: NewsItem) -> bool:
    text = f" {item.title.lower()} "
    return _speaker_key(item) is not None and any(term in text for term in STATEMENT_TERMS)


def _event_priority(item: NewsItem) -> int:
    text = f"{item.title} {item.summary}".lower()
    if any(t in text for t in ("missile", "drone", "attack", "strike", "explosion", "blast", "bombing", "air defense", "air defence", "interception", "intercepted", "sirens", "siren", "موشک", "پهپاد", "حمله", "انفجار", "بمباران", "پدافند", "رهگیری", "آژیر")):
        return 100
    if any(t in text for t in ("airspace", "notam", "hormuz", "tanker", "flight ban", "حریم هوایی", "نوتام", "هرمز", "نفتکش")):
        return 90
    if any(t in text for t in ("ceasefire", "sanction", "talks", "negotiation", "agreement", "deal", "security council", "iaea", "resolution", "آتش‌بس", "تحریم", "مذاکرات", "توافق", "شورای امنیت", "شورای حکام", "قطعنامه")):
        return 80
    if any(t in text for t in ("nuclear", "uranium", "enrichment", "هسته‌ای", "اورانیوم", "غنی‌سازی")):
        return 75
    if _is_statement(item):
        return 40
    return 50


def _select_top_stories(candidates: list[NewsItem], references: list[NewsItem]) -> tuple[list[NewsItem], list[NewsItem]]:
    def sort_key(item: NewsItem):
        dt = _published_dt(item.published) or datetime.min.replace(tzinfo=timezone.utc)
        return (_event_priority(item), dt)
    ordered = sorted(candidates, key=sort_key, reverse=True)
    selected: list[NewsItem] = []
    skipped: list[NewsItem] = []
    speaker_windows: dict[str, datetime] = {}
    for item in ordered:
        if any(_same_story(item, other) for other in references + selected):
            skipped.append(item)
            continue
        if _is_statement(item):
            speaker = _speaker_key(item)
            dt = _published_dt(item.published)
            if speaker and dt and speaker in speaker_windows and abs(dt - speaker_windows[speaker]) <= timedelta(hours=2):
                skipped.append(item)
                continue
            if speaker and dt:
                speaker_windows[speaker] = dt
        selected.append(item)
    return selected, skipped


def _truth_newer(post_id: str, last_id: str) -> bool:
    try:
        return int(post_id) > int(last_id)
    except (TypeError, ValueError):
        return post_id != last_id


def run(now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    state = load_state(STATE_PATH)
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        print("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID", file=sys.stderr)
        return 2
    changed = False

    try:
        posts = fetch_truth_posts()
        if posts:
            last_id = state.get("truth_last_id")
            if not last_id:
                state["truth_last_id"] = posts[0].id
                save_state(state, STATE_PATH)
                changed = True
            else:
                new_posts = [p for p in posts if _truth_newer(p.id, str(last_id))]
                for post in reversed(new_posts):
                    if not is_iran_related(post.text):
                        continue
                    translated = translate_to_fa(post.text)
                    if translated:
                        send_telegram(format_truth(post, translated), token, chat_id)
                if new_posts:
                    state["truth_last_id"] = new_posts[0].id
                    save_state(state, STATE_PATH)
                    changed = True
    except Exception as exc:
        print(f"Truth error: {exc}", file=sys.stderr)

    try:
        items = fetch_news_items()
        seen = list(state.get("news_seen") or [])
        seen_set = set(seen)
        if not seen:
            state["news_seen"] = [item.key for item in items[:300]]
            save_state(state, STATE_PATH)
            changed = bool(items) or changed
        else:
            rejected = [item for item in items if item.key not in seen_set and (not _published_today(item.published, now) or not is_important_news(item.title, item.summary))]
            for item in rejected:
                seen.insert(0, item.key)
                seen_set.add(item.key)
            references = [item for item in items if item.key in seen_set]
            candidates = [item for item in items if item.key not in seen_set and _published_today(item.published, now) and is_important_news(item.title, item.summary)]
            selected, duplicates = _select_top_stories(candidates, references)
            for item in duplicates:
                seen.insert(0, item.key)
                seen_set.add(item.key)
            if rejected or duplicates:
                state["news_seen"] = seen[:500]
                save_state(state, STATE_PATH)
                changed = True
            next_color = state.get("next_news_color", "red")
            for item in reversed(selected):
                title_fa = translate_to_fa(item.title)
                if not title_fa:
                    continue
                summary_fa = translate_to_fa(item.summary[:1200]) if item.summary else ""
                marker = _red_story_marker(item) if next_color == "red" else "⚪️"
                send_telegram(format_news(item, title_fa, summary_fa, marker_override=marker), token, chat_id)
                next_color = "white" if next_color == "red" else "red"
                state["next_news_color"] = next_color
                seen.insert(0, item.key)
                seen_set.add(item.key)
                state["news_seen"] = seen[:500]
                save_state(state, STATE_PATH)
                changed = True
    except Exception as exc:
        print(f"News error: {exc}", file=sys.stderr)

    last_market = _parse_iso(state.get("market_last_sent_at"))
    market_due = last_market is None or now - last_market >= MARKET_INTERVAL
    if market_due and not _market_quiet_hours(now):
        try:
            snapshot = fetch_market_snapshot()
            send_telegram(format_market(snapshot, now), token, chat_id)
            state["market_last_sent_at"] = now.isoformat()
            save_state(state, STATE_PATH)
            changed = True
        except Exception as exc:
            print(f"Market error: {exc}", file=sys.stderr)
    if changed:
        save_state(state, STATE_PATH)
    return 0


def monitor_loop(poll_seconds: int = 60, session_seconds: int = 240) -> int:
    """Run repeated polling cycles for a bounded GitHub Actions session."""
    poll_seconds = max(1, int(poll_seconds))
    session_seconds = max(poll_seconds, int(session_seconds))
    started = time.monotonic()
    while True:
        cycle_started = time.monotonic()
        rc = run()
        if rc != 0:
            return rc
        elapsed = time.monotonic() - started
        if elapsed + poll_seconds > session_seconds:
            return 0
        cycle_elapsed = time.monotonic() - cycle_started
        time.sleep(max(0.0, poll_seconds - cycle_elapsed))


def _cli() -> int:
    if "--monitor" in sys.argv[1:]:
        poll_seconds = int(os.environ.get("POLL_SECONDS", "60"))
        session_seconds = int(os.environ.get("SESSION_SECONDS", "240"))
        return monitor_loop(poll_seconds=poll_seconds, session_seconds=session_seconds)
    return run()


if __name__ == "__main__":
    raise SystemExit(_cli())
