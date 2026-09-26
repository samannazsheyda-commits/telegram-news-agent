from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, Callable

import requests

from .newsroom_v5_antiflood import AutoPublishPacer
from .newsroom_v5_events import SqliteEventLog
from .newsroom_v5_jobs import retry_job
from .newsroom_v5_pipeline import NewsroomV5Pipeline
from .newsroom_v5_publish import AmbiguousPublishError, prepare_publication, process_publication
from .newsroom_v5_store import NewsroomV5Store
from .services import translate_to_fa

_TRANSLATION_TERMINAL_AFTER = 24
_RECONCILE_TERMINAL_AFTER = 48


def _enabled(name: str, default: bool = False) -> bool:
    raw = str(os.environ.get(name, "true" if default else "false") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    try:
        return float(str(os.environ.get(name, default)).strip())
    except (TypeError, ValueError):
        return default


def _parse_time(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _value(decision: Any, name: str, default: Any = None) -> Any:
    if isinstance(decision, dict):
        return decision.get(name, default)
    return getattr(decision, name, default)


def format_telegram_message(story: dict, title_fa: str, body_fa: str) -> str:
    from .manual_publish import _message_for

    item = SimpleNamespace(
        news_key=story.get("news_key") or story.get("id"),
        source=story.get("source_name") or story.get("source_id") or "",
        original_title=story.get("original_title") or "",
        original_summary=story.get("original_body") or "",
        source_url=story.get("source_url") or "",
        published_at_source=story.get("published_at_source") or "",
    )
    return _message_for(item, title_fa, body_fa)


def telegram_message_sender(token: str, chat_id: str, *, session=requests) -> Callable[[str], Any]:
    def send(text: str) -> Any:
        try:
            response = session.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                data={"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True},
                timeout=(5, 20),
            )
        except requests.ConnectTimeout:
            raise
        except (requests.ReadTimeout, requests.ConnectionError) as exc:
            # The request may have reached Telegram; resending blindly could duplicate the post.
            raise AmbiguousPublishError(f"telegram_response_lost:{type(exc).__name__}") from exc
        response.raise_for_status()
        return response.json()["result"]["message_id"]

    return send


class NewsroomV5Worker:
    """Runs durable V5 jobs: translation → editorial routing → publication/reconciliation."""

    def __init__(
        self,
        store: NewsroomV5Store,
        *,
        worker_id: str | None = None,
        lightweight_translator: Callable[[str], str] = translate_to_fa,
        ai_translator: Callable[[str], Any] | None = None,
        decide: Callable[[dict], Any] | None = None,
        sender: Callable[[str, str], Any] | None = None,
        message_sender: Callable[[str], Any] | None = None,
        reconciler: Callable[[dict], dict | None] | None = None,
        events: Any = None,
        auto_publish_enabled: bool | None = None,
        min_publish_interval_seconds: float | None = None,
        max_auto_publish_age_hours: float | None = None,
        batch_size: int = 20,
        lease_seconds: int = 120,
    ) -> None:
        self.store = store
        self.worker_id = worker_id or f"{socket.gethostname()}:{os.getpid()}"
        self.pipeline = NewsroomV5Pipeline(
            store,
            lightweight_translator=lightweight_translator,
            ai_translator=ai_translator,
            auto_publish_enabled=auto_publish_enabled,
        )
        self.decide = decide
        self.sender = sender
        self.message_sender = message_sender
        self.reconciler = reconciler
        self.events = events
        self.auto_publish_enabled = (
            _enabled("NEWSROOM_AUTO_PUBLISH_ENABLED") if auto_publish_enabled is None else bool(auto_publish_enabled)
        )
        self.pacer = AutoPublishPacer(min_interval_seconds=int(
            _env_float("NEWSROOM_AUTO_PUBLISH_MIN_INTERVAL_SECONDS", 60)
            if min_publish_interval_seconds is None else min_publish_interval_seconds
        ))
        self.max_age = timedelta(hours=(
            _env_float("NEWSROOM_AUTO_PUBLISH_MAX_AGE_HOURS", 3)
            if max_auto_publish_age_hours is None else max_auto_publish_age_hours
        ))
        self.batch_size = max(1, int(batch_size))
        self.lease_seconds = max(10, int(lease_seconds))

    @property
    def telegram_writes(self) -> bool:
        return self.sender is not None or self.message_sender is not None

    def _emit(self, event_type: str, payload: dict) -> None:
        if self.events is not None:
            try:
                self.events.publish(event_type, payload)
            except Exception as exc:  # events are best-effort post-commit notifications
                print(f"V5_EVENT_EMIT_FAILED type={event_type} error={exc}", file=sys.stderr)

    def _claim(self, kind: str) -> list[dict]:
        return self.store.claim_jobs(kind, worker_id=self.worker_id, limit=self.batch_size, lease_seconds=self.lease_seconds)

    def run_once(self) -> dict:
        summary: Counter = Counter()
        for job in self._claim("translate_story"):
            self._run_translation(job, summary)
        for job in self._claim("editorial_story"):
            self._run_editorial(job, summary)
        if self.telegram_writes:
            for job in self._claim("publish_story"):
                self._run_publish(job, summary)
            for job in self._claim("reconcile_publication"):
                self._run_reconcile(job, summary)
        return dict(summary)

    def _run_translation(self, job: dict, summary: Counter) -> None:
        story_id = str(job.get("story_id") or "")
        try:
            result = self.pipeline.process_translation(story_id)
        except KeyError:
            self.store.finish_job(job["id"])
            return
        except Exception as exc:
            retry_job(self.store, job["id"], error=f"translation_error:{exc}", terminal_after=_TRANSLATION_TERMINAL_AFTER)
            summary["translation_retry"] += 1
            return
        if result["status"] == "retry":
            retry_job(self.store, job["id"], error="translation_failed", terminal_after=_TRANSLATION_TERMINAL_AFTER)
            summary["translation_retry"] += 1
            return
        self.store.finish_job(job["id"])
        if result["status"] == "translated":
            summary["translated"] += 1

    def _source_enabled(self, story: dict) -> bool:
        source_id = str(story.get("source_id") or "").strip()
        if not source_id:
            return False
        row = self.store.conn.execute("SELECT enabled FROM sources WHERE id=?", (source_id,)).fetchone()
        return bool(row and int(row[0]) == 1)

    def _fresh(self, story: dict) -> bool:
        published = _parse_time(story.get("published_at_source"))
        if published is None:
            return False
        return datetime.now(timezone.utc) - published <= self.max_age

    def _decision(self, story: dict) -> Any:
        if self.decide is None:
            return {"priority_class": "normal", "publish": False, "new_fact": False, "reason": "no_editorial_model"}
        try:
            return self.decide(story) or {}
        except Exception as exc:
            self.store.append_audit(
                "editorial_model_failed", entity_type="story", entity_id=story["id"], detail={"error": str(exc)[:300]},
            )
            return {"priority_class": "normal", "publish": False, "new_fact": False, "reason": "editorial_model_unavailable"}

    def _run_editorial(self, job: dict, summary: Counter) -> None:
        story_id = str(job.get("story_id") or "")
        story = self.store.get_story(story_id)
        if story is None or story.get("state") != "translated":
            self.store.finish_job(job["id"])
            return
        decision = self._decision(story)
        outcome = self.pipeline.process_editorial(
            story_id,
            decision,
            source_enabled=self._source_enabled(story),
            fresh=self._fresh(story),
            relevant=bool(_value(decision, "relevant", True)),
            duplicate=bool(_value(decision, "duplicate", False)),
        )
        self.store.finish_job(job["id"])
        summary[outcome] += 1
        if outcome == "auto_publish_candidate":
            self._auto_publish(story_id, summary)
        elif outcome == "review":
            self._announce_review(story_id)

    def _announce_review(self, story_id: str) -> None:
        self._emit("story_added", {"story_id": story_id})
        self._emit("counts_changed", {"reason": "story_added", "story_id": story_id})

    def _last_publication_at(self) -> datetime | None:
        row = self.store.conn.execute("SELECT MAX(created_at) FROM publications").fetchone()
        return _parse_time(row[0]) if row else None

    def _auto_publish(self, story_id: str, summary: Counter) -> None:
        if not self.telegram_writes:
            decision_reason = "telegram_writes_disabled"
            allowed = False
        else:
            pace = self.pacer.decide(last_publish_at=self._last_publication_at())
            allowed, decision_reason = pace.allow, pace.reason
        if allowed:
            try:
                prepare_publication(self.store, story_id, idempotency_key=f"auto:{story_id}", copy_mode="machine")
            except (KeyError, ValueError) as exc:
                allowed, decision_reason = False, f"prepare_failed:{exc}"
        if allowed:
            summary["auto_publish_prepared"] += 1
            self._emit("story_updated", {"story_id": story_id, "state": "publishing"})
            return
        self.store.transition_story(story_id, {"editorial_ready"}, "review")
        self.store.append_audit(
            "auto_publish_deferred", entity_type="story", entity_id=story_id, detail={"reason": decision_reason},
        )
        summary["review"] += 1
        self._announce_review(story_id)

    def _publication_sender(self, publication_id: str) -> Callable[[str, str], Any]:
        if self.sender is not None:
            return self.sender
        publication = self.store.get_publication(publication_id) or {}
        story = self.store.get_story(str(publication.get("story_id") or "")) or {}
        return lambda title, body: self.message_sender(format_telegram_message(story, title, body))

    def _publication_id(self, job: dict) -> str:
        try:
            return str(json.loads(job.get("payload_json") or "{}").get("publication_id") or "")
        except ValueError:
            return ""

    def _run_publish(self, job: dict, summary: Counter) -> None:
        publication_id = self._publication_id(job)
        if not publication_id or self.store.get_publication(publication_id) is None:
            self.store.finish_job(job["id"])
            return
        try:
            result = process_publication(
                self.store,
                publication_id,
                sender=self._publication_sender(publication_id),
                reconciler=self.reconciler,
                event_sink=self._emit,
            )
        except Exception as exc:
            retry_job(self.store, job["id"], error=f"publish_error:{exc}")
            summary["publish_retry"] += 1
            return
        status = result.get("status")
        if status == "retry":
            summary["publish_retry"] += 1
            return
        self.store.finish_job(job["id"])
        summary[f"publish_{status}"] += 1

    def _run_reconcile(self, job: dict, summary: Counter) -> None:
        publication_id = self._publication_id(job)
        if not publication_id or self.store.get_publication(publication_id) is None:
            self.store.finish_job(job["id"])
            return
        result = process_publication(
            self.store,
            publication_id,
            sender=self._publication_sender(publication_id),
            reconciler=self.reconciler,
            event_sink=self._emit,
        )
        if result.get("status") == "reconcile":
            retry_job(self.store, job["id"], error="reconciliation_unresolved", terminal_after=_RECONCILE_TERMINAL_AFTER)
            summary["reconcile_pending"] += 1
            return
        self.store.finish_job(job["id"])
        summary[f"reconcile_{result.get('status')}"] += 1


def ai_newsroom_decider() -> Callable[[dict], Any] | None:
    from .ai_newsroom import AIConfig, HuggingFaceNewsAI

    ai = HuggingFaceNewsAI(AIConfig.from_env())
    if not ai.available:
        return None

    def decide(story: dict):
        source = "\n".join(str(story.get(k) or "") for k in ("original_title", "original_body")).strip()
        return ai.score_story(source)

    return decide


def build_worker_from_env(store: NewsroomV5Store) -> NewsroomV5Worker:
    shadow = _enabled("NEWSROOM_V5_SHADOW_PIPELINE")
    writes = _enabled("NEWSROOM_V5_TELEGRAM_WRITES_ENABLED") and not shadow
    token = str(os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    chat_id = str(os.environ.get("TELEGRAM_CHAT_ID") or "").strip()
    message_sender = telegram_message_sender(token, chat_id) if writes and token and chat_id else None
    try:
        decide = ai_newsroom_decider()
    except Exception as exc:
        print(f"V5_WORKER_EDITORIAL_MODEL_UNAVAILABLE error={exc}", file=sys.stderr)
        decide = None
    return NewsroomV5Worker(
        store,
        decide=decide,
        message_sender=message_sender,
        events=SqliteEventLog(store),
        auto_publish_enabled=_enabled("NEWSROOM_AUTO_PUBLISH_ENABLED") and message_sender is not None,
    )


def main(argv: list[str] | None = None) -> int:
    from .newsroom_store_factory import create_runtime_store

    parser = argparse.ArgumentParser(description="Run Newsroom V5 durable background jobs")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=float, default=2.0)
    args = parser.parse_args(argv)

    store = create_runtime_store()
    if store is None:
        print("V5_WORKER_DISABLED NEWSROOM_STORE_BACKEND is not sqlite", file=sys.stderr)
        return 2
    worker = build_worker_from_env(store)
    print(f"V5_WORKER_START telegram_writes={worker.telegram_writes} auto_publish={worker.auto_publish_enabled}")
    try:
        while True:
            summary = worker.run_once()
            if summary:
                print("V5_WORKER " + " ".join(f"{k}={v}" for k, v in sorted(summary.items())), flush=True)
            if args.once:
                return 0
            time.sleep(max(0.2, args.interval))
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
