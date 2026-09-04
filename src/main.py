from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

from .formatters import format_market, format_news, format_truth
from .services import load_state, save_state, send_telegram, translate_to_fa
from .sources import fetch_market_snapshot, fetch_news_items, fetch_truth_posts, is_iran_related

STATE_PATH = os.environ.get("STATE_PATH", "state.json")
MARKET_INTERVAL = timedelta(hours=2)
MAX_NEWS_PER_RUN = 8


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
            new_items = [item for item in items if item.key not in seen_set][:MAX_NEWS_PER_RUN]
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
    if market_due:
        try:
            snapshot = fetch_market_snapshot()
            send_telegram(format_market(snapshot), token, chat_id)
            state["market_last_sent_at"] = now.isoformat()
            save_state(state, STATE_PATH)
            changed = True
            print("Sent market snapshot")
        except Exception as exc:
            print(f"Market error: {exc}", file=sys.stderr)

    if changed:
        save_state(state, STATE_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
