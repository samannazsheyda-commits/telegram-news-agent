from __future__ import annotations

import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

from .cars import fetch_car_prices, format_car_prices
from .formatters import _red_story_marker, format_market, format_market_daily_summary, format_news, format_truth
from .services import load_state, save_state, send_telegram, translate_to_fa
from .sources import NewsItem, fetch_market_snapshot, fetch_news_detail, fetch_news_items, fetch_truth_posts, is_iran_related
from .weather import fetch_weather_report, format_night_weather, format_noon_weather

STATE_PATH = os.environ.get("STATE_PATH", "state.json")
MARKET_INTERVAL = timedelta(hours=2)
TEHRAN = ZoneInfo("Asia/Tehran")
MIDNIGHT_GRACE = timedelta(hours=3)

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
TRUSTED_NEWS_SOURCES = {
    "Axios", "Al Jazeera", "Al Arabiya", "Channel 14", "KAN 11", "N12", "Channel 13",
    "Reuters", "Associated Press", "BBC News", "CNN", "Fox News", "NBC News", "CBS News",
    "ABC News", "Sky News", "Bloomberg", "CNBC", "Financial Times", "The New York Times",
    "France 24", "DW", "Times of Israel", "Haaretz", "Donald Trump / Truth Social",
    "Barak Ravid / X", "Abbas Araghchi / X", "Mohsen Rezaei / X", "Sepah News / X",
    "TankerTrackers", "NOTAM / Airspace", "Marco Rubio", "Mohammad Bagher Ghalibaf",
    "Scott Bessent", "J.D. Vance", "Donald Trump",
}
STORY_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "to", "of", "for", "in", "on", "at", "by",
    "with", "from", "as", "is", "are", "was", "were", "be", "been", "being", "has", "have",
    "had", "says", "said", "saying", "will", "would", "could", "may", "might", "its", "their",
    "his", "her", "this", "that", "after", "before", "about", "over", "under", "new", "latest",
    "official", "officials", "confirm", "confirmed", "event", "number", "report", "reported",
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
    if not published:
        return False
    published_local = published.astimezone(TEHRAN)
    now_local = now.astimezone(TEHRAN)
    if published_local.date() == now_local.date():
        return True
    age = now.astimezone(timezone.utc) - published
    return now_local.hour < 3 and timedelta(0) <= age <= MIDNIGHT_GRACE


def _market_quiet_hours(now: datetime) -> bool:
    return 0 <= now.astimezone(TEHRAN).hour < 8


def _tehran_date(now: datetime) -> str:
    return now.astimezone(TEHRAN).date().isoformat()


def _weather_noon_due(state: dict, now: datetime) -> bool:
    local = now.astimezone(TEHRAN)
    return 12 <= local.hour < 22 and state.get("weather_noon_last_sent_date") != local.date().isoformat()


def _weather_night_due(state: dict, now: datetime) -> bool:
    local = now.astimezone(TEHRAN)
    return local.hour >= 22 and state.get("weather_night_last_sent_date") != local.date().isoformat()


def _car_due(state: dict, now: datetime) -> bool:
    local = now.astimezone(TEHRAN)
    return local.hour >= 11 and state.get("car_last_sent_date") != local.date().isoformat()


def _market_summary_day(state: dict, now: datetime) -> str | None:
    local = now.astimezone(TEHRAN)
    if local.hour != 0:
        return None
    previous_date = (local.date() - timedelta(days=1)).isoformat()
    data = state.get("market_day_prices") or {}
    if data.get("date") != previous_date:
        return None
    if state.get("market_daily_summary_last_date") == previous_date:
        return None
    required = ("first_usd", "last_usd", "first_gold", "last_gold")
    return previous_date if all(data.get(k) is not None for k in required) else None


def _record_market_snapshot(state: dict, snapshot, now: datetime) -> None:
    day = _tehran_date(now)
    current = state.get("market_day_prices") or {}
    if current.get("date") != day:
        state["market_day_prices"] = {
            "date": day,
            "first_usd": snapshot.usd_toman,
            "last_usd": snapshot.usd_toman,
            "first_gold": snapshot.gold18_toman,
            "last_gold": snapshot.gold18_toman,
        }
        return
    current["last_usd"] = snapshot.usd_toman
    current["last_gold"] = snapshot.gold18_toman
    state["market_day_prices"] = current


def is_important_news(title: str, summary: str) -> bool:
    title_l = re.sub(r"\s+", " ", (title or "").lower()).strip()
    summary_l = re.sub(r"\s+", " ", (summary or "").lower()).strip()
    combined = f"{title_l} {summary_l}".strip()
    if not combined or any(p in title_l for p in ARTICLE_PATTERNS) or any(p in title_l for p in VAGUE_PATTERNS):
        return False
    if ("?" in title_l or "؟" in title_l) and not any(term in title_l for term in MAJOR_EVENT_TERMS):
        return False
    return any(term in combined for term in MAJOR_EVENT_TERMS)


def _is_trump_iran_news(item: NewsItem) -> bool:
    text = f"{item.title} {item.summary}".lower()
    return "trump" in text and is_iran_related(text)


def _looks_bundled(item: NewsItem) -> bool:
    title = re.sub(r"\s+", " ", item.title or "").strip()
    separators = len(re.findall(r"[,،;؛]", title))
    return len(title) >= 180 and separators >= 2


def _news_rejection_reason(item: NewsItem, now: datetime) -> str | None:
    title_l = re.sub(r"\s+", " ", (item.title or "").lower()).strip()
    combined = f"{item.title} {item.summary}".strip()
    if _published_dt(item.published) is None:
        return "invalid_publish_time"
    if not _published_today(item.published, now):
        return "not_today_tehran"
    if _looks_bundled(item):
        return "bundled_or_multi_headline"
    if any(pattern in title_l for pattern in ARTICLE_PATTERNS):
        return "article_or_commentary"
    if ("?" in title_l or "؟" in title_l) and not any(term in title_l for term in MAJOR_EVENT_TERMS):
        return "question_or_explainer"
    if _is_trump_iran_news(item):
        return None
    if item.source in TRUSTED_NEWS_SOURCES and is_iran_related(combined):
        return None
    if any(pattern in title_l for pattern in VAGUE_PATTERNS):
        return "vague_or_speculative"
    if is_important_news(item.title, item.summary):
        return None
    return "low_signal_or_unapproved_source"


def _audit_news(state: dict, item: NewsItem, reason: str, now: datetime) -> None:
    records = list(state.get("news_rejections") or [])
    records.insert(0, {
        "key": item.key,
        "source": item.source,
        "title": item.title,
        "reason": reason,
        "published": item.published,
        "link": item.link,
        "checked_at": now.astimezone(timezone.utc).isoformat(),
    })
    deduped = []
    used = set()
    for record in records:
        identity = (record.get("key"), record.get("reason"))
        if identity in used:
            continue
        used.add(identity)
        deduped.append(record)
    state["news_rejections"] = deduped[:200]
    print(f"NEWS_REJECTED reason={reason} source={item.source!r} title={item.title!r}")


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
    if _is_trump_iran_news(item):
        return 70
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
            if speaker == "trump":
                selected.append(item)
                continue
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
        new_items = [item for item in items if item.key not in seen_set]
        rejected: list[tuple[NewsItem, str]] = []
        candidates: list[NewsItem] = []
        retryable_rejections = {"invalid_publish_time", "missing_direct_source_link"}

        for item in new_items:
            reason = _news_rejection_reason(item, now)
            if reason is None:
                candidates.append(item)
            else:
                rejected.append((item, reason))

        for item, reason in rejected:
            _audit_news(state, item, reason, now)
            if reason not in retryable_rejections:
                seen.insert(0, item.key)
                seen_set.add(item.key)
            changed = True

        # Only previously accepted/currently eligible stories can suppress a new factual report.
        references = [
            item for item in items
            if item.key in seen_set and _news_rejection_reason(item, now) is None
        ]
        selected, duplicates = _select_top_stories(candidates, references)
        for item in duplicates:
            _audit_news(state, item, "duplicate_or_redundant", now)
            seen.insert(0, item.key)
            seen_set.add(item.key)
            changed = True

        if rejected or duplicates:
            state["news_seen"] = seen[:500]
            save_state(state, STATE_PATH)

        next_color = state.get("next_news_color", "red")
        for item in reversed(selected):
            try:
                title_fa = translate_to_fa(item.title)
            except Exception as exc:
                print(f"NEWS_ITEM_RETRY key={item.key!r} stage=title_translation error={exc}", file=sys.stderr)
                _audit_news(state, item, "translation_failed_retry_later", now)
                changed = True
                continue
            if not title_fa:
                _audit_news(state, item, "translation_failed_retry_later", now)
                changed = True
                continue

            detail = ""
            try:
                detail = fetch_news_detail(item)
            except Exception as exc:
                # Detail is enrichment only; a headline must still be publishable without it.
                print(f"NEWS_DETAIL_FALLBACK key={item.key!r} error={exc}", file=sys.stderr)

            summary_fa = ""
            if detail:
                try:
                    summary_fa = translate_to_fa(detail[:1200]) or ""
                except Exception as exc:
                    print(f"NEWS_SUMMARY_FALLBACK key={item.key!r} error={exc}", file=sys.stderr)

            marker = _red_story_marker(item) if next_color == "red" else "⚪️"
            try:
                message = format_news(item, title_fa, summary_fa, marker_override=marker)
            except Exception as exc:
                print(f"NEWS_ITEM_RETRY key={item.key!r} stage=format error={exc}", file=sys.stderr)
                _audit_news(state, item, "format_failed_retry_later", now)
                changed = True
                continue
            if not (message or "").strip():
                _audit_news(state, item, "format_failed_retry_later", now)
                changed = True
                continue

            try:
                send_telegram(message, token, chat_id)
            except Exception as exc:
                print(f"NEWS_ITEM_RETRY key={item.key!r} stage=send error={exc}", file=sys.stderr)
                _audit_news(state, item, "send_failed_retry_later", now)
                changed = True
                continue

            next_color = "white" if next_color == "red" else "red"
            state["next_news_color"] = next_color
            seen.insert(0, item.key)
            seen_set.add(item.key)
            state["news_seen"] = seen[:500]
            save_state(state, STATE_PATH)
            changed = True

        if changed:
            state["news_seen"] = seen[:500]
            save_state(state, STATE_PATH)
    except Exception as exc:
        print(f"News error: {exc}", file=sys.stderr)

    if _car_due(state, now):
        try:
            prices = fetch_car_prices()
            previous = state.get("car_last_prices") or {}
            send_telegram(format_car_prices(prices, previous), token, chat_id)
            state["car_last_prices"] = {p.name: p.market_toman for p in prices}
            state["car_last_sent_date"] = _tehran_date(now)
            save_state(state, STATE_PATH)
            changed = True
        except Exception as exc:
            print(f"Car price error: {exc}", file=sys.stderr)

    if _weather_noon_due(state, now):
        try:
            report = fetch_weather_report()
            send_telegram(format_noon_weather(report), token, chat_id)
            state["weather_noon_last_sent_date"] = _tehran_date(now)
            save_state(state, STATE_PATH)
            changed = True
        except Exception as exc:
            print(f"Weather noon error: {exc}", file=sys.stderr)

    if _weather_night_due(state, now):
        try:
            report = fetch_weather_report()
            send_telegram(format_night_weather(report), token, chat_id)
            state["weather_night_last_sent_date"] = _tehran_date(now)
            save_state(state, STATE_PATH)
            changed = True
        except Exception as exc:
            print(f"Weather night error: {exc}", file=sys.stderr)

    summary_day = _market_summary_day(state, now)
    if summary_day:
        data = state.get("market_day_prices") or {}
        try:
            send_telegram(
                format_market_daily_summary(
                    int(data["first_usd"]), int(data["last_usd"]),
                    int(data["first_gold"]), int(data["last_gold"]), now,
                ),
                token,
                chat_id,
            )
            state["market_daily_summary_last_date"] = summary_day
            save_state(state, STATE_PATH)
            changed = True
        except Exception as exc:
            print(f"Market daily summary error: {exc}", file=sys.stderr)

    last_market = _parse_iso(state.get("market_last_sent_at"))
    market_due = last_market is None or now - last_market >= MARKET_INTERVAL
    if market_due and not _market_quiet_hours(now):
        try:
            snapshot = fetch_market_snapshot()
            send_telegram(format_market(snapshot, now), token, chat_id)
            state["market_last_sent_at"] = now.isoformat()
            _record_market_snapshot(state, snapshot, now)
            save_state(state, STATE_PATH)
            changed = True
        except Exception as exc:
            print(f"Market error: {exc}", file=sys.stderr)
    if changed:
        save_state(state, STATE_PATH)
    return 0


def monitor_loop(poll_seconds: int = 60, session_seconds: int = 240) -> int:
    poll_seconds = max(1, int(poll_seconds))
    session_seconds = max(poll_seconds, int(session_seconds))
    started = time.monotonic()
    while True:
        cycle_started = time.monotonic()
        if cycle_started - started >= session_seconds:
            return 0
        rc = run()
        if rc != 0:
            return rc
        cycle_finished = time.monotonic()
        if cycle_finished - started + poll_seconds > session_seconds:
            return 0
        time.sleep(max(0.0, poll_seconds - (cycle_finished - cycle_started)))


def _cli() -> int:
    if "--monitor" in sys.argv[1:]:
        poll_seconds = int(os.environ.get("POLL_SECONDS", "60"))
        session_seconds = int(os.environ.get("SESSION_SECONDS", "240"))
        return monitor_loop(poll_seconds=poll_seconds, session_seconds=session_seconds)
    return run()


if __name__ == "__main__":
    raise SystemExit(_cli())
