from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import requests


def proposal_fingerprint(value: dict) -> str:
    payload = json.dumps(value or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ProposalStore:
    PATH = "data/panel_pending_actions.json"

    def __init__(self, data, ttl_minutes: int = 15) -> None:
        self.data = data
        self.ttl_minutes = int(ttl_minutes)

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    def _mutate(self, transform, message: str):
        for attempt in range(3):
            value, sha = self.data.read_json(self.PATH, [])
            rows = [deepcopy(row) for row in value if isinstance(row, dict)] if isinstance(value, list) else []
            updated = transform(rows)
            try:
                self.data.write_json(self.PATH, updated, sha, message)
                return updated
            except requests.HTTPError as exc:
                status = getattr(getattr(exc, "response", None), "status_code", None)
                if attempt < 2 and status in {409, 422}:
                    continue
                raise
        raise RuntimeError("luna_proposal_write_conflict")

    def create(
        self,
        *,
        capability: str,
        target: dict,
        payload: dict,
        summary_fa: str,
        before: dict,
        after: dict,
        target_fingerprint: str,
    ) -> dict:
        now = self._now()
        record = {
            "id": uuid4().hex,
            "capability": str(capability or "").strip(),
            "target": deepcopy(dict(target or {})),
            "payload": deepcopy(dict(payload or {})),
            "summary_fa": str(summary_fa or "این عملیات اجرا شود؟").strip(),
            "before": deepcopy(dict(before or {})),
            "after": deepcopy(dict(after or {})),
            "target_fingerprint": str(target_fingerprint or ""),
            "status": "pending",
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(minutes=self.ttl_minutes)).isoformat(),
        }
        self._mutate(lambda rows: ([deepcopy(record)] + rows)[:200], "panel v4.2: create Luna proposal")
        return deepcopy(record)

    def _read_one(self, action_id: str) -> dict | None:
        value, _ = self.data.read_json(self.PATH, [])
        for row in value if isinstance(value, list) else []:
            if isinstance(row, dict) and str(row.get("id") or "") == str(action_id or ""):
                return deepcopy(row)
        return None

    @staticmethod
    def _parse_expiry(record: dict) -> datetime | None:
        raw = str(record.get("expires_at") or "").strip()
        if not raw:
            return None
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return datetime.min.replace(tzinfo=timezone.utc)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def get_pending(self, action_id: str) -> dict:
        record = self._read_one(action_id)
        if record is None:
            return {"id": str(action_id or ""), "status": "missing"}
        if str(record.get("status") or "") != "pending":
            return record
        expiry = self._parse_expiry(record)
        if expiry is None or expiry > self._now():
            return record

        expired_at = self._now().isoformat()

        def expire(rows: list[dict]) -> list[dict]:
            output = []
            for row in rows:
                if str(row.get("id") or "") == str(action_id or "") and str(row.get("status") or "") == "pending":
                    row["status"] = "expired"
                    row["completed_at"] = expired_at
                output.append(row)
            return output

        self._mutate(expire, "panel v4.2: expire Luna proposal")
        record["status"] = "expired"
        record["completed_at"] = expired_at
        return record

    def claim(self, action_id: str) -> bool:
        """Atomically move one pending proposal to executing; only one caller can win."""
        wanted = str(action_id or "")
        claimed_at = self._now().isoformat()
        won = {"value": False}

        def transform(rows: list[dict]) -> list[dict]:
            won["value"] = False
            output = []
            for row in rows:
                if str(row.get("id") or "") == wanted and str(row.get("status") or "") == "pending":
                    row["status"] = "executing"
                    row["claimed_at"] = claimed_at
                    won["value"] = True
                output.append(row)
            return output

        self._mutate(transform, "panel v5: claim Luna proposal")
        return won["value"]

    def complete(self, action_id: str, status: str, result: dict) -> None:
        completed_at = self._now().isoformat()
        wanted = str(action_id or "")
        final_status = str(status or "failed")
        safe_result = deepcopy(dict(result or {}))

        def transform(rows: list[dict]) -> list[dict]:
            output = []
            for row in rows:
                if str(row.get("id") or "") == wanted and str(row.get("status") or "") in {"pending", "executing"}:
                    row["status"] = final_status
                    row["result"] = deepcopy(safe_result)
                    row["completed_at"] = completed_at
                output.append(row)
            return output

        self._mutate(transform, "panel v4.2: complete Luna proposal")
