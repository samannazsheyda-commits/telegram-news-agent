from __future__ import annotations

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


def _urgency_score(raw: RawNewsItem) -> tuple[int, str]:
    text = f"{raw.title} {raw.summary}".lower()
    war_hits = sum(1 for term in WAR_ALERT_TERMS if term in text)
    iran_hit = any(term in text for term in IRAN_ALERT_TERMS)
    if war_hits and iran_hit:
        rank = 300 + min(war_hits, 20)
    elif war_hits:
        rank = 200 + min(war_hits, 20)
    elif iran_hit:
        rank = 100
    else:
        rank = 0
    return rank, str(raw.published_at or raw.fetched_at or "")


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

    # Old search-engine discoveries used to create events and fill the panel even
    # though eligibility later rejected them. Drop them before fingerprinting so
    # realtime state contains only actionable/fresh candidates.
    fresh_items: list[RawNewsItem] = []
    for raw in items:
        if _stale_before_ingest(raw, now, freshness_hours):
            summary.stale += 1
            continue
        fresh_items.append(raw)

    fresh_items.sort(key=_urgency_score, reverse=True)

    for raw in fresh_items:
        item = normalize_item(raw)
        fingerprint = build_fingerprint(item)
        candidates = ledger.find_candidates(fingerprint)
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
                live_feed.upsert(_feed_record(
                    item, event_id=event_id, decision=decision.decision, reason=decision.reason,
                    duplicate_of=decision.duplicate_of, panel_status="duplicate", message_id=None, now=now,
                ))
                continue

        if decision.decision == "duplicate_same_claim":
            summary.same_claim_duplicates += 1
            event_id = decision.duplicate_of
            try:
                ledger.add_variant(event_id, item.raw.source_url, now.isoformat())
            except KeyError:
                pass
            if not retry_unpublished_duplicate:
                live_feed.upsert(_feed_record(
                    item, event_id=event_id, decision=decision.decision, reason=decision.reason,
                    duplicate_of=decision.duplicate_of, panel_status="duplicate", message_id=None, now=now,
                ))
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

            live_feed.upsert(_feed_record(
                item,
                event_id=event_id,
                decision=decision.decision,
                reason=eligibility.reason,
                duplicate_of=decision.duplicate_of if retry_unpublished_duplicate else "",
                panel_status=panel_status,
                message_id=None,
                now=now,
            ))
            continue

        auto_publish = settings.get("auto_publish") is not False
        needs_review = decision.decision == "needs_editorial_review" or not auto_publish

        if needs_review:
            summary.review_items += 1
            _queue_item(editorial_store, item, decision.reason if decision.decision == "needs_editorial_review" else "auto_publish_off", now)
            live_feed.upsert(_feed_record(
                item,
                event_id=event_id,
                decision=decision.decision,
                reason=decision.reason,
                duplicate_of=decision.duplicate_of if retry_unpublished_duplicate else "",
                panel_status="waiting",
                message_id=None,
                now=now,
            ))
            continue

        if shadow:
            live_feed.upsert(_feed_record(
                item,
                event_id=event_id,
                decision=decision.decision,
                reason=decision.reason,
                duplicate_of=decision.duplicate_of if retry_unpublished_duplicate else "",
                panel_status="new",
                message_id=None,
                now=now,
            ))
            continue

        try:
            ok, message_id = _publisher_result(publisher(item))
        except Exception:
            ok, message_id = False, None

        if ok and message_id is not None:
            ledger.mark_published(event_id, message_id, fingerprint.key_facts, now.isoformat())
            summary.published += 1
            live_feed.upsert(_feed_record(
                item,
                event_id=event_id,
                decision=decision.decision,
                reason=decision.reason,
                duplicate_of=decision.duplicate_of if retry_unpublished_duplicate else "",
                panel_status="auto_published",
                message_id=message_id,
                now=now,
            ))
        else:
            summary.publish_failed += 1
            summary.review_items += 1
            _queue_item(editorial_store, item, "publish_failed", now)
            live_feed.upsert(_feed_record(
                item,
                event_id=event_id,
                decision=decision.decision,
                reason="publish_failed",
                duplicate_of=decision.duplicate_of if retry_unpublished_duplicate else "",
                panel_status="failed",
                message_id=None,
                now=now,
            ))

    max_records = int(settings.get("panel_max_records") or 500)
    live_feed.prune(now, freshness_hours=freshness_hours, max_records=max_records)
    summary.panel_feed_count = len(live_feed.records())
    return summary
