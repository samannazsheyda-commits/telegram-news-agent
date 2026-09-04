from __future__ import annotations

import base64
import json
from typing import Any

import requests

from .editorial_store import merge_record_sets


class GitHubJsonRepository:
    def __init__(self, repository: str, token: str, branch: str = "main", session=requests):
        if "/" not in (repository or ""):
            raise ValueError("invalid_repository")
        if not token:
            raise ValueError("github_token_required")
        self.repository = repository
        self.token = token
        self.branch = branch
        self.session = session
        self.base_url = f"https://api.github.com/repos/{repository}/contents"

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def read_json(self, path: str, default):
        response = self.session.get(
            f"{self.base_url}/{path}",
            headers=self.headers,
            params={"ref": self.branch},
            timeout=15,
        )
        if response.status_code == 404:
            return default, None
        response.raise_for_status()
        payload = response.json()
        raw = base64.b64decode(payload.get("content", "")).decode("utf-8")
        try:
            return json.loads(raw), payload.get("sha")
        except json.JSONDecodeError:
            return default, payload.get("sha")

    def write_json(self, path: str, value, sha: str | None, message: str):
        raw = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
        payload: dict[str, Any] = {
            "message": message,
            "content": base64.b64encode(raw.encode("utf-8")).decode("ascii"),
            "branch": self.branch,
        }
        if sha:
            payload["sha"] = sha
        response = self.session.put(
            f"{self.base_url}/{path}",
            headers=self.headers,
            json=payload,
            timeout=15,
        )
        response.raise_for_status()
        return response.json()

    def merge_records(self, path: str, incoming: list[dict], message: str) -> list[dict]:
        for attempt in range(2):
            remote, sha = self.read_json(path, [])
            if not isinstance(remote, list):
                remote = []
            merged = merge_record_sets(remote, incoming)
            try:
                self.write_json(path, merged, sha, message)
                return merged
            except requests.HTTPError as exc:
                status = getattr(exc.response, "status_code", None)
                if attempt == 0 and status in {409, 422}:
                    continue
                raise
        raise RuntimeError("github_write_conflict")

    def replace_records(self, path: str, records: list[dict], message: str) -> list[dict]:
        for attempt in range(2):
            _, sha = self.read_json(path, [])
            try:
                self.write_json(path, records, sha, message)
                return records
            except requests.HTTPError as exc:
                status = getattr(exc.response, "status_code", None)
                if attempt == 0 and status in {409, 422}:
                    continue
                raise
        raise RuntimeError("github_write_conflict")

    def mark_news_seen(self, news_key: str) -> None:
        for attempt in range(2):
            state, sha = self.read_json("state.json", {})
            if not isinstance(state, dict):
                state = {}
            seen = [key for key in list(state.get("news_seen") or []) if key != news_key]
            seen.insert(0, news_key)
            state["news_seen"] = seen[:500]
            try:
                self.write_json("state.json", state, sha, "chore: mark manually published news seen")
                return
            except requests.HTTPError as exc:
                status = getattr(exc.response, "status_code", None)
                if attempt == 0 and status in {409, 422}:
                    continue
                raise
