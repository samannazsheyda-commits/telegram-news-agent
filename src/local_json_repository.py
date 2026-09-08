from __future__ import annotations

import hashlib
import json
import os
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import fcntl
import requests


class LocalWriteConflict(requests.HTTPError):
    def __init__(self):
        super().__init__("local_write_conflict")
        self.response = SimpleNamespace(status_code=409)


class LocalJsonRepository:
    def __init__(self, root: str | Path):
        self.root = Path(root)

    def _path(self, relative: str) -> Path:
        clean = str(relative or "").lstrip("/")
        path = (self.root / clean).resolve()
        if self.root.resolve() not in path.parents and path != self.root.resolve():
            raise ValueError("invalid_local_path")
        return path

    @staticmethod
    def _sha(raw: bytes) -> str:
        return hashlib.sha256(raw).hexdigest()

    @contextmanager
    def _lock(self, path: Path):
        lock = path.with_suffix(path.suffix + ".lock")
        lock.parent.mkdir(parents=True, exist_ok=True)
        with lock.open("a+") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def read_json(self, path: str, default):
        target = self._path(path)
        try:
            raw = target.read_bytes()
        except FileNotFoundError:
            return default, None
        try:
            return json.loads(raw.decode("utf-8")), self._sha(raw)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return default, self._sha(raw)

    def write_json(self, path: str, value, sha: str | None, message: str):
        del message
        target = self._path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        raw = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        with self._lock(target):
            if target.exists():
                current = target.read_bytes()
                if sha is not None and self._sha(current) != sha:
                    raise LocalWriteConflict()
            elif sha is not None:
                raise LocalWriteConflict()
            tmp = target.with_name(target.name + f".tmp.{os.getpid()}")
            tmp.write_bytes(raw)
            os.replace(tmp, target)
        return {"path": str(target), "sha": self._sha(raw)}

    def mark_news_seen(self, news_key: str) -> None:
        for _ in range(2):
            state, sha = self.read_json("state.json", {})
            if not isinstance(state, dict):
                state = {}
            seen = [key for key in list(state.get("news_seen") or []) if key != news_key]
            seen.insert(0, news_key)
            state["news_seen"] = seen[:500]
            try:
                self.write_json("state.json", state, sha, "mark news seen")
                return
            except LocalWriteConflict:
                continue
        raise LocalWriteConflict()
