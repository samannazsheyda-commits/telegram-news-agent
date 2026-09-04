from __future__ import annotations

import base64
import hashlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass, fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


QUEUE_PATH = Path(os.environ.get("EDITORIAL_QUEUE_PATH", "data/editorial_queue.json"))
HISTORY_PATH = Path(os.environ.get("EDITORIAL_HISTORY_PATH", "data/editorial_history.json"))


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def deterministic_review_id(news_key: str) -> str:
    return hashlib.sha1(news_key.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ReviewItem:
    id: str
    news_key: str
    source: str
    source_url: str
    original_title: str
    original_summary: str = ""
    persian_title: str = ""
    persian_body: str = ""
    published_at_source: str = ""
    discovered_at: str = ""
    rejection_reason: str = ""
    status: str = "pending"
    final_persian_title: str = ""
    final_persian_body: str = ""
    decision_at: str = ""
    updated_at: str = ""

    @classmethod
    def for_news(
        cls,
        *,
        news_key: str,
        source: str,
        source_url: str,
        original_title: str,
        original_summary: str = "",
        persian_title: str = "",
        persian_body: str = "",
        published_at_source: str = "",
        discovered_at: str = "",
        rejection_reason: str = "",
        status: str = "pending",
        final_persian_title: str = "",
        final_persian_body: str = "",
        decision_at: str = "",
        updated_at: str = "",
    ) -> "ReviewItem":
        now = updated_at or utc_now_iso()
        return cls(
            id=deterministic_review_id(news_key),
            news_key=news_key,
            source=source,
            source_url=source_url,
            original_title=original_title,
            original_summary=original_summary,
            persian_title=persian_title,
            persian_body=persian_body,
            published_at_source=published_at_source,
            discovered_at=discovered_at or now,
            rejection_reason=rejection_reason,
            status=status,
            final_persian_title=final_persian_title,
            final_persian_body=final_persian_body,
            decision_at=decision_at,
            updated_at=now,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReviewItem":
        allowed = {f.name for f in fields(cls)}
        clean = {k: data.get(k, "") for k in allowed}
        clean["status"] = clean.get("status") or "pending"
        return cls(**clean)


def merge_record_sets(remote: list[dict], incoming: list[dict]) -> list[dict]:
    by_id: dict[str, dict] = {}
    for record in remote:
        if record.get("id"):
            by_id[str(record["id"])] = dict(record)
    for record in incoming:
        record_id = str(record.get("id") or "")
        if not record_id:
            continue
        old = by_id.get(record_id)
        if old is None or str(record.get("updated_at", "")) >= str(old.get("updated_at", "")):
            by_id[record_id] = dict(record)
    return sorted(by_id.values(), key=lambda r: str(r.get("updated_at", "")), reverse=True)


def _read_json(path: Path) -> list[dict]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except (json.JSONDecodeError, OSError):
        return []
    return raw if isinstance(raw, list) else []


def _atomic_write_json(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(records, ensure_ascii=False, indent=2) + "\n"
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


class LocalEditorialStore:
    def __init__(self, queue_path: str | Path = QUEUE_PATH, history_path: str | Path = HISTORY_PATH):
        self.queue_path = Path(queue_path)
        self.history_path = Path(history_path)

    def queue(self) -> list[dict]:
        return _read_json(self.queue_path)

    def history(self) -> list[dict]:
        return _read_json(self.history_path)

    def get_pending(self, item_id: str) -> ReviewItem | None:
        for record in self.queue():
            if record.get("id") == item_id and record.get("status", "pending") == "pending":
                return ReviewItem.from_dict(record)
        return None

    def find_by_news_key(self, news_key: str) -> ReviewItem | None:
        for record in self.queue() + self.history():
            if record.get("news_key") == news_key:
                return ReviewItem.from_dict(record)
        return None

    def upsert_queue(self, item: ReviewItem) -> ReviewItem:
        records = merge_record_sets(self.queue(), [asdict(item)])
        _atomic_write_json(self.queue_path, records)
        return item

    def upsert_history(self, item: ReviewItem) -> ReviewItem:
        records = merge_record_sets(self.history(), [asdict(item)])
        _atomic_write_json(self.history_path, records)
        return item

    def move_to_history(
        self,
        item_id: str,
        *,
        status: str,
        final_persian_title: str = "",
        final_persian_body: str = "",
        decision_at: str = "",
    ) -> ReviewItem:
        queue = self.queue()
        current = next((r for r in queue if r.get("id") == item_id), None)
        if current is None:
            existing = next((r for r in self.history() if r.get("id") == item_id), None)
            if existing is not None:
                return ReviewItem.from_dict(existing)
            raise KeyError(item_id)
        now = decision_at or utc_now_iso()
        moved = dict(current)
        moved.update(
            status=status,
            final_persian_title=final_persian_title,
            final_persian_body=final_persian_body,
            decision_at=now,
            updated_at=now,
        )
        remaining = [r for r in queue if r.get("id") != item_id]
        _atomic_write_json(self.queue_path, remaining)
        _atomic_write_json(self.history_path, merge_record_sets(self.history(), [moved]))
        return ReviewItem.from_dict(moved)

    def mark_auto_published(self, news_key: str) -> ReviewItem | None:
        target = next((r for r in self.queue() if r.get("news_key") == news_key), None)
        if target is None:
            return None
        return self.move_to_history(target["id"], status="published_auto")


class GitHubEditorialStore:
    """Small GitHub Contents API backed store for the web panel.

    The panel uses this class server-side only. Writes refetch on conflict,
    merge by deterministic record id, and retry once so unrelated updates
    from the Actions agent are not silently lost.
    """

    def __init__(self, repository: str, token: str, branch: str = "main"):
        if "/" not in repository:
            raise ValueError("invalid_repository")
        self.repository = repository
        self.token = token
        self.branch = branch
        self.base_url = f"https://api.github.com/repos/{repository}/contents"

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _fetch(self, path: str) -> tuple[list[dict], str | None]:
        response = requests.get(
            f"{self.base_url}/{path}",
            headers=self.headers,
            params={"ref": self.branch},
            timeout=15,
        )
        if response.status_code == 404:
            return [], None
        response.raise_for_status()
        payload = response.json()
        content = base64.b64decode(payload.get("content", "")).decode("utf-8")
        parsed = json.loads(content or "[]")
        return (parsed if isinstance(parsed, list) else []), payload.get("sha")

    def _put(self, path: str, records: list[dict], sha: str | None, message: str) -> requests.Response:
        encoded = base64.b64encode((json.dumps(records, ensure_ascii=False, indent=2) + "\n").encode("utf-8")).decode("ascii")
        payload: dict[str, Any] = {
            "message": message,
            "content": encoded,
            "branch": self.branch,
        }
        if sha:
            payload["sha"] = sha
        return requests.put(
            f"{self.base_url}/{path}",
            headers=self.headers,
            json=payload,
            timeout=15,
        )

    def merge_write(self, path: str, incoming: list[dict], message: str) -> list[dict]:
        remote, sha = self._fetch(path)
        merged = merge_record_sets(remote, incoming)
        response = self._put(path, merged, sha, message)
        if response.status_code in {409, 422}:
            remote, sha = self._fetch(path)
            merged = merge_record_sets(remote, incoming)
            response = self._put(path, merged, sha, message)
        response.raise_for_status()
        return merged

    def read_queue(self) -> list[dict]:
        return self._fetch("data/editorial_queue.json")[0]

    def read_history(self) -> list[dict]:
        return self._fetch("data/editorial_history.json")[0]

    def read_custom_sources(self) -> list[dict]:
        return self._fetch("data/custom_sources.json")[0]

    def write_queue(self, records: list[dict]) -> list[dict]:
        return self.merge_write("data/editorial_queue.json", records, "chore: update editorial queue")

    def write_history(self, records: list[dict]) -> list[dict]:
        return self.merge_write("data/editorial_history.json", records, "chore: update editorial history")

    def write_custom_sources(self, records: list[dict]) -> list[dict]:
        return self.merge_write("data/custom_sources.json", records, "chore: update custom sources")
