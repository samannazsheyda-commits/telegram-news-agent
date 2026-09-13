from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Callable

from .ai_newsroom import AIServiceError, cosine_similarity
from .editorial_store import LocalEditorialStore, ReviewItem
from .event_ledger import EventLedger
from .newsroom_decision import decide_item
from .newsroom_eligibility import evaluate_eligibility
from .newsroom_fingerprint import build_fingerprint
from .newsroom_models import EventRecord, LiveFeedRecord, NormalizedNewsItem, RawNewsItem
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
_AI_MODES = {"off", "optional", "required"}
_AI_FAILURE_RETRY_COOLDOWN = timedelta(minutes=5)
_AI_RETRYABLE_REASONS = (
    "ai_semantic_unavailable:",
    "ai_editor_unavailable:",
    "ai_required_unavailable",
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


def _ai_mode(settings: dict, ai) -> str:
    raw = str(settings.get("ai_newsroom_mode") or "").strip().lower()
    if not raw and ai is not None:
        raw = str(getattr(getattr(ai, "config", None), "mode", "optional") or "optional").strip().lower()
    return raw if raw in _AI_MODES else "optional"


def _ai_available(ai, mode: str) -> bool:
    return mode != "off" and ai is not None and bool(getattr(ai, "available", True))


def _ai_retry_blocked(previous: LiveFeedRecord | None, now: datetime, *, ai_enabled: bool) -> bool:
    if previous is None or previous.panel_status not in {"waiting", "failed"}:
        return False
    reason = str(previous.decision_reason or "")
    retryable = any(reason.startswith(prefix) for prefix in _AI_RETRYABLE_REASONS)
    if reason == "publish_failed" and ai_enabled:
        retryable = True
    if not retryable:
        return False
    updated = _parse_source_time(previous.updated_at)
    if updated is None:
        return False
    now_utc = now.astimezone(timezone.utc)
    age = now_utc - updated
    return timedelta(0) <= age < _AI_FAILURE_RETRY_COOLDOWN


def _story_text(item: NormalizedNewsItem) -> str:
    return re.sub(r"\s+", " ", f"{item.raw.title} {item.raw.summary}").strip()


def _event_text(record: EventRecord) -> str:
    facts = " ".join(str(value) for value in (record.key_facts or []) if str(value).strip())
    return re.sub(r"\s+", " ", f"{record.canonical_title} {facts}").strip()


def _semantic_relation(ai, ledger: EventLedger, item: NormalizedNewsItem, now: datetime):
    """Return (closest event, relation decision, similarity) or all-None when no close event exists."""
    hours = int(getattr(ai.config, "event_memory_hours", 72) or 72)
    threshold = float(getattr(ai.config, "duplicate_threshold", 0.87) or 0.87)
    recent = [
        record for record in ledger.recent_records(now, hours=hours)
        if record.published_message_ids and item.raw.source_url not in record.source_variants
    ][:40]
    if not recent:
        return None, None, 0.0

    new_text = _story_text(item)
    prior_texts = [_event_text(record) for record in recent]
    vectors = ai.embed_texts([new_text, *prior_texts])
    if len(vectors) != len(recent) + 1:
        raise AIServiceError("semantic_embedding_count_mismatch")
    new_vector = vectors[0]
    scored = [(cosine_similarity(new_vector, vector), record, text) for vector, record, text in zip(vectors[1:], recent, prior_texts)]
    similarity, record, prior_text = max(scored, key=lambda row: row[0])
    if similarity < threshold:
        return None, None, similarity
    relation = ai.judge_relation(new_text, prior_text)
    return record, relation, similarity


def _review_ai_failure(
    *,
    summary: CycleSummary,
    editorial_store: LocalEditorialStore,
    live_feed: LiveFeedStore,
    item: NormalizedNewsItem,
    event_id: str,
    decision: str,
    duplicate_of: str,
    reason: str,
    now: datetime,
) -> None:
    summary.review_items += 1
    _queue_item(editorial_store, item, reason, now)
    live_feed.upsert(
        _feed_record(
            item,
            event_id=event_id,
            decision=decision,
            reason=reason,
            duplicate_of=duplicate_of,
            panel_status="waiting",
            message_id=None,
            now=now,
        )
    )


def run_cycle(
    fetcher,
    ledger: EventLedger,
    live_feed: LiveFeedStore,
    editorial_store: LocalEditorialStore,
    publisher: Callable[[NormalizedNewsItem], object],
    settings: dict,
    now: datetime,
    shadow: bool = False,
    ai=None,
) -> CycleSummary:
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    summary = CycleSummary()
    items, summary.sources_ok, summary.sources_failed = _collect(fetcher)
    summary.items_fetched = len(items)
    freshness_hours = int(settings.get("freshness_hours") or 2)
    ai_mode = _ai_mode(settings, ai)
    ai_enabled = _ai_available(ai, ai_mode)
    existing_feed = {row.item_id: row for row in live_feed.records()}

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
        if _ai_retry_blocked(existing_feed.get(_item_id(item)), now, ai_enabled=ai_enabled):
            continue

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
            ledger.find_candidates(fingerprint, now=now),
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

        semantic_event = None
        semantic_relation = None
        semantic_error = ""
        if ai_enabled and not retry_unpublished_duplicate:
            try:
                semantic_event, semantic_relation, _similarity = _semantic_relation(ai, ledger, item, now)
            except Exception as exc:
                semantic_error = f"ai_semantic_unavailable:{type(exc).__name__}"
                print(f"AI_SEMANTIC_FAILED source={item.raw.source!r} type={type(exc).__name__} error={exc}", flush=True)

        if semantic_event is not None and semantic_relation is not None and semantic_relation.relation == "duplicate_same_event":
            summary.same_claim_duplicates += 1
            try:
                ledger.add_variant(semantic_event.event_id, item.raw.source_url, now.isoformat())
            except KeyError:
                pass
            live_feed.upsert(
                _feed_record(
                    item,
                    event_id=semantic_event.event_id,
                    decision="duplicate_semantic",
                    reason=f"ai_duplicate_same_event:{semantic_relation.reason}",
                    duplicate_of=semantic_event.event_id,
                    panel_status="duplicate",
                    message_id=None,
                    now=now,
                )
            )
            continue

        semantic_material = semantic_event is not None and semantic_relation is not None and semantic_relation.relation == "material_update"
        if retry_unpublished_duplicate:
            event_id = decision.duplicate_of
        elif semantic_material:
            summary.material_updates += 1
            event_id = semantic_event.event_id
            ledger.update_material_facts(event_id, fingerprint.key_facts, now.isoformat())
            ledger.add_variant(event_id, item.raw.source_url, now.isoformat())
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

        effective_decision = "material_update" if semantic_material else decision.decision
        effective_duplicate = semantic_event.event_id if semantic_material else (decision.duplicate_of if retry_unpublished_duplicate else "")

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
            live_feed.upsert(_feed_record(item, event_id=event_id, decision=effective_decision, reason=eligibility.reason, duplicate_of=effective_duplicate, panel_status=panel_status, message_id=None, now=now))
            continue

        if ai_mode == "required" and not ai_enabled:
            _review_ai_failure(
                summary=summary,
                editorial_store=editorial_store,
                live_feed=live_feed,
                item=item,
                event_id=event_id,
                decision=effective_decision,
                duplicate_of=effective_duplicate,
                reason="ai_required_unavailable",
                now=now,
            )
            continue

        if semantic_error and ai_mode == "required":
            _review_ai_failure(
                summary=summary,
                editorial_store=editorial_store,
                live_feed=live_feed,
                item=item,
                event_id=event_id,
                decision=effective_decision,
                duplicate_of=effective_duplicate,
                reason=semantic_error,
                now=now,
            )
            continue

        if ai_enabled:
            try:
                editorial = ai.score_story(_story_text(item))
                threshold = int(getattr(ai.config, "importance_threshold", 70) or 70)
                if editorial.publish is not True or editorial.importance < threshold:
                    _review_ai_failure(
                        summary=summary,
                        editorial_store=editorial_store,
                        live_feed=live_feed,
                        item=item,
                        event_id=event_id,
                        decision=effective_decision,
                        duplicate_of=effective_duplicate,
                        reason=f"ai_editor_rejected:{editorial.topic}:{editorial.reason}",
                        now=now,
                    )
                    continue
            except Exception as exc:
                reason = f"ai_editor_unavailable:{type(exc).__name__}"
                print(f"AI_EDITOR_FAILED source={item.raw.source!r} type={type(exc).__name__} error={exc}", flush=True)
                if ai_mode == "required":
                    _review_ai_failure(
                        summary=summary,
                        editorial_store=editorial_store,
                        live_feed=live_feed,
                        item=item,
                        event_id=event_id,
                        decision=effective_decision,
                        duplicate_of=effective_duplicate,
                        reason=reason,
                        now=now,
                    )
                    continue

        auto_publish = settings.get("auto_publish") is not False
        needs_review = decision.decision == "needs_editorial_review" or not auto_publish
        if needs_review:
            summary.review_items += 1
            _queue_item(editorial_store, item, decision.reason if decision.decision == "needs_editorial_review" else "auto_publish_off", now)
            live_feed.upsert(_feed_record(item, event_id=event_id, decision=effective_decision, reason=decision.reason, duplicate_of=effective_duplicate, panel_status="waiting", message_id=None, now=now))
            continue

        if shadow:
            live_feed.upsert(_feed_record(item, event_id=event_id, decision=effective_decision, reason=decision.reason, duplicate_of=effective_duplicate, panel_status="new", message_id=None, now=now))
            continue

        hourly_limit = _hourly_news_limit(settings)
        recent_publications = ledger.publication_count_since(now - timedelta(hours=1))
        critical_unique = effective_decision == "new_event" and _critical_breaking_event(item)
        if recent_publications >= hourly_limit and not critical_unique:
            summary.rate_limited += 1
            summary.review_items += 1
            _queue_item(editorial_store, item, "hourly_publish_limit", now)
            live_feed.upsert(
                _feed_record(
                    item,
                    event_id=event_id,
                    decision=effective_decision,
                    reason="hourly_publish_limit",
                    duplicate_of=effective_duplicate,
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
            live_feed.upsert(_feed_record(item, event_id=event_id, decision=effective_decision, reason=decision.reason, duplicate_of=effective_duplicate, panel_status="auto_published", message_id=message_id, now=now))
        else:
            summary.publish_failed += 1
            summary.review_items += 1
            _queue_item(editorial_store, item, "publish_failed", now)
            live_feed.upsert(_feed_record(item, event_id=event_id, decision=effective_decision, reason="publish_failed", duplicate_of=effective_duplicate, panel_status="failed", message_id=None, now=now))

    max_records = int(settings.get("panel_max_records") or 500)
    live_feed.prune(now, freshness_hours=freshness_hours, max_records=max_records)
    summary.panel_feed_count = len(live_feed.records())
    return summary
