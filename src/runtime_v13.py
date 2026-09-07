from __future__ import annotations

import json
import sys
import time
from datetime import datetime, time as clock_time, timedelta, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from . import runtime_v12 as v12
from .editorial_store import LocalEditorialStore
from .manual_publish import _clean_source
from .sources import USER_AGENT

base = v12.base
_OWN_CHANNEL = "bikhabaar"
_PRICE_MARKERS = {
    "car": "قیمت روز خودرو",
    "phone": "قیمت روز موبایل",
}
_NEWSROOM_SETTINGS_PATH = Path("data/newsroom_settings.json")
_upstream_fetch_news_items = None


def load_newsroom_settings(path: str | Path = _NEWSROOM_SETTINGS_PATH) -> dict:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _parse_hhmm(value: object, fallback: clock_time) -> clock_time:
    raw = str(value or "").strip()
    try:
        hour, minute = raw.split(":", 1)
        return clock_time(hour=max(0, min(23, int(hour))), minute=max(0, min(59, int(minute))))
    except (ValueError, TypeError):
        return fallback


def quiet_mode_active(settings: dict, now: datetime) -> bool:
    if not settings.get("quiet_mode"):
        return False
    local = now.astimezone(base.agent.TEHRAN).time().replace(tzinfo=None)
    start = _parse_hhmm(settings.get("quiet_start"), clock_time(0, 0))
    end = _parse_hhmm(settings.get("quiet_end"), clock_time(7, 0))
    if start == end:
        return True
    if start < end:
        return start <= local < end
    return local >= start or local < end


def newsroom_publish_paused(settings: dict, now: datetime) -> bool:
    return bool(settings.get("emergency_lock")) or settings.get("auto_publish") is False or quiet_mode_active(settings, now)


def _source_allowed(item, settings: dict) -> bool:
    prefs = settings.get("sources") if isinstance(settings.get("sources"), dict) else {}
    raw_source = str(getattr(item, "source", "") or "").strip()
    localized = _clean_source(raw_source)
    pref = prefs.get(raw_source) or prefs.get(localized) or {}
    return not isinstance(pref, dict) or pref.get("enabled") is not False


def _fresh_enough(item, settings: dict, now: datetime) -> bool:
    try:
        hours = max(1, min(48, int(settings.get("freshness_hours") or 3)))
    except (TypeError, ValueError):
        hours = 3
    published = base.agent._published_dt(str(getattr(item, "published", "") or ""))
    if published is None:
        return True
    return published >= now - timedelta(hours=hours)


def _newsroom_fetch_news_items():
    upstream = _upstream_fetch_news_items
    if upstream is None:
        return []
    items = list(upstream() or [])
    settings = load_newsroom_settings()
    now = datetime.now(timezone.utc)
    return [item for item in items if _source_allowed(item, settings) and _fresh_enough(item, settings, now)]


def _install_newsroom_fetch_policy() -> None:
    global _upstream_fetch_news_items
    current = base.agent.fetch_news_items
    if current is not _newsroom_fetch_news_items:
        _upstream_fetch_news_items = current
    base.agent.fetch_news_items = _newsroom_fetch_news_items


def channel_has_daily_price_post(html_text: str, now: datetime, kind: str) -> bool:
    marker = _PRICE_MARKERS.get(kind)
    if not marker:
        raise ValueError(f"unknown price kind: {kind}")
    target_date = now.astimezone(base.agent.TEHRAN).date()
    soup = BeautifulSoup(html_text or "", "html.parser")
    for message in soup.select(".tgme_widget_message[data-post]"):
        text_node = message.select_one(".tgme_widget_message_text")
        if text_node is None:
            continue
        text = " ".join(text_node.stripped_strings)
        if marker not in text:
            continue
        time_node = message.select_one("time[datetime]")
        if time_node is None:
            continue
        raw = str(time_node.get("datetime") or "").strip()
        if not raw:
            continue
        try:
            published = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if published.tzinfo is None:
                published = published.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if published.astimezone(base.agent.TEHRAN).date() == target_date:
            return True
    return False


def channel_has_car_post_today(html_text: str, now: datetime) -> bool:
    return channel_has_daily_price_post(html_text, now, "car")


def _channel_has_price_today(now: datetime, kind: str, session=requests) -> bool:
    response = session.get(
        f"https://t.me/s/{_OWN_CHANNEL}",
        headers={"User-Agent": USER_AGENT},
        timeout=15,
    )
    response.raise_for_status()
    return channel_has_daily_price_post(response.text, now, kind)


def _car_due_once_per_day(state: dict, now: datetime, session=requests) -> bool:
    if not v12.v11.v10.v9._original_car_due(state, now):
        return False

    local_date = now.astimezone(base.agent.TEHRAN).date().isoformat()
    try:
        if _channel_has_price_today(now, "car", session=session):
            state["car_last_sent_date"] = local_date
            base.agent.save_state(state, base.agent.STATE_PATH)
            print(f"CAR_SUPPRESSED already_published_today date={local_date}")
            return False
    except Exception as exc:
        print(f"CAR_SUPPRESSED channel_guard_error={exc}", file=sys.stderr)
        return False

    return True


def _phone_due_once_per_day(state: dict, now: datetime, session=requests) -> bool:
    if not v12.v11.v10.phone_flagships_due(state, now):
        return False

    local_date = now.astimezone(base.agent.TEHRAN).date().isoformat()
    try:
        if _channel_has_price_today(now, "phone", session=session):
            state["phone_flagships_last_sent_date"] = local_date
            base.agent.save_state(state, base.agent.STATE_PATH)
            print(f"PHONE_SUPPRESSED already_published_today date={local_date}")
            return False
    except Exception as exc:
        print(f"PHONE_SUPPRESSED channel_guard_error={exc}", file=sys.stderr)
        return False

    return True


def _publish_phone_once_per_day(now: datetime) -> None:
    state = base.agent.load_state(base.agent.STATE_PATH)
    if not _phone_due_once_per_day(state, now):
        return
    v12.v11.v10._publish_daily_flagships(now)


def expire_previous_day_queue(now: datetime, *, store: LocalEditorialStore | None = None) -> int:
    store = store or LocalEditorialStore()
    today_tehran = now.astimezone(base.agent.TEHRAN).date()
    moved = 0
    for record in list(store.queue()):
        if str(record.get("status") or "pending") != "pending":
            continue
        published = base.agent._published_dt(str(record.get("published_at_source") or ""))
        if published is None:
            continue
        if published.astimezone(base.agent.TEHRAN).date() >= today_tehran:
            continue
        item_id = str(record.get("id") or "")
        if not item_id:
            continue
        try:
            store.move_to_history(item_id, status="superseded")
            moved += 1
        except KeyError:
            continue
    if moved:
        print(f"EDITORIAL_EXPIRED previous_day={moved} date={today_tehran.isoformat()}")
    return moved


def install_production_policies() -> None:
    v12.install_production_policies()
    v12.v11.v10.v9.install_persian_only_output()
    base.agent._car_due = _car_due_once_per_day
    _install_newsroom_fetch_policy()


def _collect_only_for_panel() -> int:
    from .panel_command_file import _scan_fresh_items_into_queue

    return _scan_fresh_items_into_queue(LocalEditorialStore())


def run(now=None) -> int:
    install_production_policies()
    resolved_now = now or datetime.now(timezone.utc)
    expire_previous_day_queue(resolved_now)
    settings = load_newsroom_settings()
    if newsroom_publish_paused(settings, resolved_now):
        added = _collect_only_for_panel()
        reason = "emergency_lock" if settings.get("emergency_lock") else "auto_publish_off" if settings.get("auto_publish") is False else "quiet_mode"
        print(f"NEWSROOM_PUBLISH_PAUSED reason={reason} queued={added}")
        return 0
    v12.v11.v10._retry_todays_false_bundles(resolved_now)
    _publish_phone_once_per_day(resolved_now)
    return v12.v11.v10.v9.v8.run(resolved_now)


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
        return monitor_loop(
            poll_seconds=int(v12.v11.v10.os.environ.get("POLL_SECONDS", "60")),
            session_seconds=int(v12.v11.v10.os.environ.get("SESSION_SECONDS", "240")),
        )
    return run()


if __name__ == "__main__":
    raise SystemExit(_cli())
