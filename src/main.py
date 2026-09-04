from __future__ import annotations

import os
import re
import sys
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

from .formatters import format_market, format_news, format_truth
from .services import load_state, save_state, send_telegram, translate_to_fa
from .sources import fetch_market_snapshot, fetch_news_items, fetch_truth_posts, is_iran_related

STATE_PATH = os.environ.get("STATE_PATH", "state.json")
MARKET_INTERVAL = timedelta(hours=2)
MAX_NEWS_PER_RUN = 8
TEHRAN = ZoneInfo("Asia/Tehran")

ARTICLE_PATTERNS = (
    "analysis:", "opinion:", "explainer", "what to know", "what we know", "why ",
    "how can", "how could", "how might", "experts explain", "experts say", "expert says",
    "three experts", "what does", "what could", "could mean", "may mean", "might mean",
    "timeline of", "a look at", "inside the", "the case for", "commentary", "editorial",
    "in depth", "in-depth", "factbox", "fact check", "backgrounder", "guide to",
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
    "intercepted", "seized", "sank", "sinking", "collision", "fire", "war", "ceasefire",
    "sanction", "sanctions", "designates", "blacklists", "agreement", "deal", "signed",
    "talks suspended", "suspend talks", "talks resume", "resumes talks", "talks begin",
    "negotiations suspended", "negotiations resume", "withdraws", "expels", "orders",
    "announces", "confirms", "declares", "closes airspace", "closed airspace", "reopens airspace",
    "airspace closed", "airspace reopened", "notam", "flight ban", "flights cancelled",
    "evacuation", "nuclear site", "uranium", "enrichment", "hormuz", "tanker",
    "حمله", "موشک", "پهپاد", "انفجار", "بمباران", "کشته", "مجروح", "رهگیری",
    "توقیف", "غرق", "آتش‌بس", "تحریم", "توافق", "مذاکرات متوقف", "مذاکرات از سر گرفته",
    "اعلام کرد", "تأیید کرد", "دستور داد", "حریم هوایی بسته", "حریم هوایی باز",
    "نوتام", "لغو پرواز", "ممنوعیت پرواز", "تخلیه", "هسته‌ای", "اورانیوم", "غنی‌سازی",
    "هرمز", "نفتکش",
)


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


def _published_today(value: str, now: datetime) -> bool:
    if not value:
        return False
    try:
        published = parsedate_to_datetime(value)
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)
        return published.astimezone(TEHRAN).date() == now.astimezone(TEHRAN).date()
    except Exception:
        return False


def _market_quiet_hours(now: datetime) -> bool:
    local_hour = now.astimezone(TEHRAN).hour
    return 0 <= local_hour < 8


def is_important_news(title: str, summary: str) -> bool:
    title_l = re.sub(r"\s+", " ", (title or "").lower()).strip()
    summary_l = re.sub(r"\s+", " ", (summary or "").lower()).strip()
    combined = f"{title_l} {summary_l}".strip()
    if not combined:
        return False

    if any(pattern in title_l for pattern in ARTICLE_PATTERNS):
        return False
    if any(pattern in title_l for pattern in VAGUE_PATTERNS):
        return False

    # Questions are normally explainers/articles, unless the title also reports a concrete event.
    if "?" in title_l or "؟" in title_l:
        if not any(term in title_l for term in MAJOR_EVENT_TERMS):
            return False

    return any(term in combined for term in MAJOR_EVENT_TERMS)


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
                print(f"Truth bootstrap at {posts[0].id}")
            else:
                new_posts = [p for p in posts if _truth_newer(p.id, str(last_id))]
                for post in reversed(new_posts):
                    if not is_iran_related(post.text):
                        continue
                    translated = translate_to_fa(post.text)
                    if not translated:
                        print(f"Skipped untranslated Truth {post.id}")
                        continue
                    send_telegram(format_truth(post, translated), token, chat_id)
                    print(f"Sent Iran-related Truth {post.id}")
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
            print(f"News bootstrap with {len(items)} Iran-related items")
        else:
            rejected = [
                item for item in items
                if item.key not in seen_set and (
                    not _published_today(item.published, now)
                    or not is_important_news(item.title, item.summary)
                )
            ]
            for item in rejected:
                seen.insert(0, item.key)
                seen_set.add(item.key)
                reason = "stale/undated" if not _published_today(item.published, now) else "low-value/article"
                print(f"Skipped {reason} news {item.source}: {item.key}")

            new_items = [
                item for item in items
                if item.key not in seen_set
                and _published_today(item.published, now)
                and is_important_news(item.title, item.summary)
            ][:MAX_NEWS_PER_RUN]

            if rejected:
                state["news_seen"] = seen[:500]
                save_state(state, STATE_PATH)
                changed = True

            for item in reversed(new_items):
                title_fa = translate_to_fa(item.title)
                if not title_fa:
                    print(f"Skipped untranslated title {item.source}: {item.key}")
                    continue
                summary_fa = translate_to_fa(item.summary[:1200]) if item.summary else ""
                send_telegram(format_news(item, title_fa, summary_fa), token, chat_id)
                seen.insert(0, item.key)
                seen_set.add(item.key)
                state["news_seen"] = seen[:500]
                save_state(state, STATE_PATH)
                changed = True
                print(f"Sent news {item.source}: {item.key}")
    except Exception as exc:
        print(f"News error: {exc}", file=sys.stderr)

    last_market = _parse_iso(state.get("market_last_sent_at"))
    market_due = last_market is None or now - last_market >= MARKET_INTERVAL
    if market_due and not _market_quiet_hours(now):
        try:
            snapshot = fetch_market_snapshot()
            send_telegram(format_market(snapshot), token, chat_id)
            state["market_last_sent_at"] = now.isoformat()
            save_state(state, STATE_PATH)
            changed = True
            print("Sent market snapshot")
        except Exception as exc:
            print(f"Market error: {exc}", file=sys.stderr)
    elif market_due:
        print("Skipped market snapshot during Tehran quiet hours (00:00-08:00)")

    if changed:
        save_state(state, STATE_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
