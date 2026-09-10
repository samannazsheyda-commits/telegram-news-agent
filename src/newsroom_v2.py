from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Callable

from .editorial_store import LocalEditorialStore, ReviewItem
from .event_ledger import EventLedger
from .newsroom_decision import decide_item
from .newsroom_eligibility import evaluate_eligibility
from .newsroom_fingerprint import build_fingerprint
from .newsroom_models import LiveFeedRecord, NormalizedNewsItem, RawNewsItem
from .newsroom_normalize import normalize_item
from .panel_live_feed import LiveFeedStore


WAR_ALERT_TERMS = (
    "missile", "ballistic", "cruise missile", "rocket", "launch", "intercept", "strike", "attack",
    "explosion", "blast", "bombing", "hormuz", "strait of hormuz", "tanker", "warship", "drone",
    "موشک", "بالستیک", "کروز", "شلیک", "رهگیری", "حمله", "انفجار", "بمباران", "هرمز", "نفتکش", "پهپاد",
)
IRAN_ALERT_TERMS = ("iran", "iranian", "tehran", "irgc", "ایران", "ایرانی", "تهران", "سپاه")
DEFAULT_HOURLY_NEWS_LIMIT = 3

# The hourly-cap escape hatch is deliberately narrower than WAR_ALERT_TERMS.
# It is for a real, already-happening kinetic/operational event, not a warning,
# threat, forecast or generic security story that merely mentions missiles.
_SPECULATIVE_TERMS = (
    " could ", " may ", " might ", " possible ", " potentially ", " potential ",
    " warning ", " warns ", " warned ", " warn ", " threat ", " threatens ", " threatened ",
    " expected to ", " expects to ", " plan to ", " plans to ", " preparing to ", " prepare to ",
    "ممکن", "احتمال", "احتمالی", "هشدار", "تهدید", "قصد دارد", "برنامه دارد", "آماده می‌شود",
)
_MISSILE_TERMS = ("missile", "missiles", "rocket", "rockets", "موشک", "راکت")
_LAUNCH_ACTIONS = (
    " launch", "launched", "launches", "fired", "fires", " impact", "impacted", " hit ", "hits ", "struck",
    "شلیک", "پرتاب", "اصابت", "برخورد",
)
_EXPLOSION_TERMS = ("explosion", "explosions", "blast", "blasts", "detonation", "detonations", "انفجار")
_DIRECT_ATTACK_TERMS = (
    "airstrike", "air strike", "bombing", "bombardment", "attacked", "direct attack", "strike on", "strikes on",
    "بمباران", "حمله مستقیم", "حمله هوایی", "هدف قرار داد", "هدف قرار گرفت",
)
_DRONE_TERMS = ("drone", "drones", "uav", "uavs", "پهپاد")
_DRONE_ACTIONS = (" launch", "launched", "attack", "strike", "intercepted", "shot down", "شلیک", "پرتاب", "حمله", "رهگیری", "سرنگون")
_HORMUZ_TERMS = ("strait of hormuz", "hormuz", "تنگه هرمز", "هرمز")
_HORMUZ_CRITICAL_ACTIONS = (
    "attack", "seized", "seizure", "sinking", "sank", "closed", "blockade", "blocked",
    "حمله", "توقیف", "غرق", "بسته شد", "مسدود", "محاصره",
)


@dataclass
class CycleSummary:
    sources_ok: int = 0
    sources_failed: int = 0
    items_fetched: int = 0
    new_events: int = 0
    material_updates: int = 0
    exact_duplicates: int = 0
    same_claim_duplicates: int = 0
    stale: int = 0
    filtered: int = 0
    review_items: int = 0
    published: int = 0
    publish_failed: int = 0
    rate_limited: int = 0
    critical_bypasses: int = 0
    panel_feed_count: int = 0


def _collect(fetcher) -> tuple[list[RawNewsItem], int, int]:
    if callable(fetcher):
        try:
            return list(fetcher() or []), 1, 0
        except Exception:
            return [], 0, 1

    source_fetchers = list(fetcher or [])
    if not source_fetchers:
        return [], 0, 0

    items: list[RawNewsItem] = []
    ok = 0
    failed = 0
    with ThreadPoolExecutor(max_workers=min(8, len(source_fetchers)), thread_name_prefix="bikhabar-feed") as pool:
        futures = {pool.submit(source_fetcher): source_fetcher for source_fetcher in source_fetchers}
        for future in as_completed(futures):
            try:
                items.extend(list(future.result() or []))
                ok += 1
            except Exception:
                failed += 1
    return items, ok, failed


def _parse_source_time(value: str) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        try:
            dt = parsedate_to_datetime(raw)
        except Exception:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _stale_before_ingest(raw: RawNewsItem, now: datetime, freshness_hours: int) -> bool:
    published = _parse_source_time(raw.published_at)
    if published is None:
        return False
    now_utc = now.astimezone(timezone.utc)
    age = now_utc - published
    if age < timedelta(minutes=-10):
        return True
    return age > timedelta(hours=max(1, int(freshness_hours)))


def _urgency_score(raw: RawNewsItem, priority_terms: list[str] | tuple[str, ...] | None = None) -> tuple[int, str]:
    text = f"{raw.title} {raw.summary}".lower()
    ordered_terms = [str(term or "").strip().lower() for term in (priority_terms or []) if str(term or "").strip()]
    custom_rank = 0
    for index, term in enumerate(ordered_terms[:20]):
        if term in text:
            # User-managed rules outrank fallback categories; earlier terms win.
            custom_rank = max(custom_rank, 1000 + (20 - index) * 10)

    war_hits = sum(1 for term in WAR_ALERT_TERMS if term in text)
    iran_hit = any(term in text for term in IRAN_ALERT_TERMS)
    if war_hits and iran_hit:
        fallback_rank = 300 + min(war_hits, 20)
    elif war_hits:
        fallback_rank = 200 + min(war_hits, 20)
    elif iran_hit:
        fallback_rank = 100
    else:
        fallback_rank = 0
    return max(custom_rank, fallback_rank), str(raw.published_at or raw.fetched_at or "")


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _critical_breaking_event(item: NormalizedNewsItem) -> bool:
    """Return True only for an actual high-impact event, never a forecast/warning.

    Deduplication runs before this predicate. The caller additionally requires a
    `new_event` decision, so a second source repeating the same launch/explosion
    cannot consume the emergency bypass.
    """
    text = re.sub(r"\s+", " ", f" {item.normalized_text or item.raw.title} ".lower())
    if _contains_any(text, _SPECULATIVE_TERMS):
        return False

    if _contains_any(text, _EXPLOSION_TERMS):
        return True

    if _contains_any(text, _MISSILE_TERMS) and _contains_any(text, _LAUNCH_ACTIONS):
        return True

    if _contains_any(text, _DIRECT_ATTACK_TERMS):
        return True

    if _contains_any(text, _DRONE_TERMS) and _contains_any(text, _DRONE_ACTIONS):
        return True

    if _contains_any(text, _HORMUZ_TERMS) and _contains_any(text, _HORMUZ_CRITICAL_ACTIONS):
        return True

    return False


def _hourly_news_limit(settings: dict) -> int:
    try:
        value = int(settings.get("hourly_news_limit") or DEFAULT_HOURLY_NEWS_LIMIT)
    except (TypeError, ValueError):
        value = DEFAULT_HOURLY_NEWS_LIMIT
    return max(1, min(20, value))


def _item_id(item: NormalizedNewsItem) -> str:
    return item.raw.source_item_id or item.raw.source_url


def _feed_record(
    item: NormalizedNewsItem,
    *,
    event_id: str,
    decision: str,
    reason: str,
    duplicate_of: str = "",
    panel_status: str,
    message_id: int | None,
    now: datetime,
) -> LiveFeedRecord:
    return LiveFeedRecord(
        item_id=_item_id(item),
        event_id=event_id,
        source=item.raw.source,
        source_url=item.raw.source_url,
        title=item.raw.title,
        published_at_source=item.raw.published_at,
        discovered_at=item.raw.fetched_at or now.isoformat(),
        decision=decision,
        decision_reason=reason,
        duplicate_of=duplicate_of,
        telegram_message_id=message_id,
        panel_status=panel_status,
        updated_at=now.isoformat(),
    )


def _queue_item(editorial_store: LocalEditorialStore, item: NormalizedNewsItem, reason: str, now: datetime) -> None:
    editorial_store.upsert_queue(
        ReviewItem.for_news(
            news_key=_item_id(item),
            source=item.raw.source,
            source_url=item.raw.source_url,
            original_title=item.raw.title,
            original_summary=item.raw.summary,
            published_at_source=item.raw.published_at,
            discovered_at=item.raw.fetched_at or now.isoformat(),
            rejection_reason=reason,
        )
    )


def _publisher_result(payload) -> tuple[bool, int | None]:
    if isinstance(payload, dict):
        ok = payload.get("ok") is True
        message_id = payload.get("message_id")
        if message_id is None and isinstance(payload.get("result"), dict):
            message_id = payload["result"].get("message_id")
        return ok and isinstance(message_id, int), message_id if isinstance(message_id, int) else None
    if isinstance(payload, int):
        return True, payload
    return False, None


def _merge_candidates(*groups):
    merged = []
    seen = set()
    for group in groups:
        for record in group:
            if record.event_id in seen:
                continue
            seen.add(record.event_id)
            merged.append(record)
    return merged


def run_cycle(
    fetcher,
    ledger: EventLedger,
    live_feed: LiveFeedStore,
    editorial_store: LocalEditorialStore,
    publisher: Callable[[NormalizedNewsItem], object],
    settings: dict,
    now: datetime,
    shadow: bool = False,
) -> CycleSummary:
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    summary = CycleSummary()
    items, summary.sources_ok, summary.sources_failed = _collect(fetcher)
    summary.items_fetched = len(items)
    freshness_hours = int(settings.get("freshness_hours") or 2)

    fresh_items: list[RawNewsItem] = []
    for raw in items:
        if _stale_before_ingest(raw, now, freshness_hours):
            summary.stale += 1
            continue
        fresh_items.append(raw)

    priority_terms = settings.get("priority_terms") if isinstance(settings.get("priority_terms"), (list, tuple)) else []
    fresh_items.sort(key=lambda raw: _urgency_score(raw, priority_terms), reverse=True)

    for raw in fresh_items:
        item = normalize_item(raw)

        exact_source_event = ledger.find_by_source_url(item.raw.source_url)
        if exact_source_event is not None and exact_source_event.published_message_ids:
            summary.exact_duplicates += 1
            live_feed.upsert(
                _feed_record(
                    item,
                    event_id=exact_source_event.event_id,
                    decision="duplicate_exact_url",
                    reason="source_url_already_published",
                    duplicate_of=exact_source_event.event_id,
                    panel_status="duplicate",
                    message_id=None,
                    now=now,
                )
            )
            continue

        fingerprint = build_fingerprint(item)
        candidates = _merge_candidates(
            ledger.find_candidates(fingerprint),
            ledger.find_same_source_claims(item.raw.source, item.raw.title, item.raw.published_at),
        )
        decision = decide_item(item, fingerprint, candidates)

        duplicate_event = None
        retry_unpublished_duplicate = False
        if decision.decision in {"duplicate_exact", "duplicate_same_claim"}:
            duplicate_event = ledger.get(decision.duplicate_of)
            retry_unpublished_duplicate = duplicate_event is not None and not duplicate_event.published_message_ids

        if decision.decision == "duplicate_exact":
            summary.exact_duplicates += 1
            event_id = decision.duplicate_of
            try:
                ledger.add_variant(event_id, item.raw.source_url, now.isoformat())
            except KeyError:
                pass
            if not retry_unpublished_duplicate:
                live_feed.upsert(_feed_record(item, event_id=event_id, decision=decision.decision, reason=decision.reason, duplicate_of=decision.duplicate_of, panel_status="duplicate", message_id=None, now=now))
                continue

        if decision.decision == "duplicate_same_claim":
            summary.same_claim_duplicates += 1
            event_id = decision.duplicate_of
            try:
                ledger.add_variant(event_id, item.raw.source_url, now.isoformat())
            except KeyError:
                pass
            if not retry_unpublished_duplicate:
                live_feed.upsert(_feed_record(item, event_id=event_id, decision=decision.decision, reason=decision.reason, duplicate_of=decision.duplicate_of, panel_status="duplicate", message_id=None, now=now))
                continue

        if retry_unpublished_duplicate:
            event_id = decision.duplicate_of
        elif decision.decision == "material_update":
            summary.material_updates += 1
            event_id = decision.event_id
            ledger.update_material_facts(event_id, fingerprint.key_facts, now.isoformat())
            ledger.add_variant(event_id, item.raw.source_url, now.isoformat())
        else:
            event = ledger.create_event(
                fingerprint=fingerprint,
                canonical_title=item.raw.title,
                primary_source=item.raw.source,
                source_url=item.raw.source_url,
                first_seen=item.raw.fetched_at or now.isoformat(),
                key_facts=fingerprint.key_facts,
                source_item_id=item.raw.source_item_id,
            )
            event_id = event.event_id
            if decision.decision == "new_event":
                summary.new_events += 1

        eligibility = evaluate_eligibility(item, now)
        if not eligibility.eligible:
            if eligibility.reason == "stale":
                summary.stale += 1
            elif eligibility.review:
                summary.review_items += 1
            else:
                summary.filtered += 1
            if eligibility.review:
                _queue_item(editorial_store, item, eligibility.reason, now)
                panel_status = "waiting"
            else:
                panel_status = "rejected"
            live_feed.upsert(_feed_record(item, event_id=event_id, decision=decision.decision, reason=eligibility.reason, duplicate_of=decision.duplicate_of if retry_unpublished_duplicate else "", panel_status=panel_status, message_id=None, now=now))
            continue

        auto_publish = settings.get("auto_publish") is not False
        needs_review = decision.decision == "needs_editorial_review" or not auto_publish
        if needs_review:
            summary.review_items += 1
            _queue_item(editorial_store, item, decision.reason if decision.decision == "needs_editorial_review" else "auto_publish_off", now)
            live_feed.upsert(_feed_record(item, event_id=event_id, decision=decision.decision, reason=decision.reason, duplicate_of=decision.duplicate_of if retry_unpublished_duplicate else "", panel_status="waiting", message_id=None, now=now))
            continue

        if shadow:
            live_feed.upsert(_feed_record(item, event_id=event_id, decision=decision.decision, reason=decision.reason, duplicate_of=decision.duplicate_of if retry_unpublished_duplicate else "", panel_status="new", message_id=None, now=now))
            continue

        hourly_limit = _hourly_news_limit(settings)
        recent_publications = ledger.publication_count_since(now - timedelta(hours=1))
        critical_unique = decision.decision == "new_event" and _critical_breaking_event(item)
        if recent_publications >= hourly_limit and not critical_unique:
            summary.rate_limited += 1
            summary.review_items += 1
            _queue_item(editorial_store, item, "hourly_publish_limit", now)
            live_feed.upsert(
                _feed_record(
                    item,
                    event_id=event_id,
                    decision=decision.decision,
                    reason="hourly_publish_limit",
                    duplicate_of=decision.duplicate_of if retry_unpublished_duplicate else "",
                    panel_status="waiting",
                    message_id=None,
                    now=now,
                )
            )
            continue
        if recent_publications >= hourly_limit and critical_unique:
            summary.critical_bypasses += 1

        try:
            ok, message_id = _publisher_result(publisher(item))
        except Exception as exc:
            print(f"PUBLISH_EXCEPTION source={item.raw.source!r} type={type(exc).__name__} error={exc}", flush=True)
            ok, message_id = False, None

        if ok and message_id is not None:
            ledger.mark_published(event_id, message_id, fingerprint.key_facts, now.isoformat())
            summary.published += 1
            live_feed.upsert(_feed_record(item, event_id=event_id, decision=decision.decision, reason=decision.reason, duplicate_of=decision.duplicate_of if retry_unpublished_duplicate else "", panel_status="auto_published", message_id=message_id, now=now))
        else:
            summary.publish_failed += 1
            summary.review_items += 1
            _queue_item(editorial_store, item, "publish_failed", now)
            live_feed.upsert(_feed_record(item, event_id=event_id, decision=decision.decision, reason="publish_failed", duplicate_of=decision.duplicate_of if retry_unpublished_duplicate else "", panel_status="failed", message_id=None, now=now))

    max_records = int(settings.get("panel_max_records") or 500)
    live_feed.prune(now, freshness_hours=freshness_hours, max_records=max_records)
    summary.panel_feed_count = len(live_feed.records())
    return summary
