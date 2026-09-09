from __future__ import annotations

import hashlib
import json
import os
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from .newsroom_models import RawNewsItem
from .sources import (
    NEWS_QUERIES,
    SPECIAL_QUERIES,
    NewsItem,
    USER_AGENT,
    _fetch_google_news_query,
    is_regional_security_alert,
    is_security_alert,
)
from .truth_social import fetch_trump_truth_items, parse_truth_status


SOURCE_OVERRIDES_PATH = Path(os.environ.get("SOURCE_OVERRIDES_PATH", "data/source_overrides.json"))
CUSTOM_SOURCES_PATH = Path(os.environ.get("CUSTOM_SOURCES_PATH", "data/custom_sources.json"))


def _source_id(prefix: str, identity: str) -> str:
    digest = hashlib.sha1(identity.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}-{digest}"


def normalize_truth_handle(value: str) -> str:
    text = (value or "").strip()
    if text.startswith("https://truthsocial.com/@"):
        text = text.split("https://truthsocial.com/@", 1)[1].split("/", 1)[0]
    text = text.lstrip("@").strip()
    if not text or len(text) > 64 or not all(ch.isalnum() or ch == "_" for ch in text):
        raise ValueError("invalid_truth_handle")
    return f"@{text}"


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default


def source_overrides(path: Path = SOURCE_OVERRIDES_PATH) -> dict[str, dict[str, Any]]:
    value = _read_json(path, {})
    return value if isinstance(value, dict) else {}


def custom_sources(path: Path = CUSTOM_SOURCES_PATH) -> list[dict[str, Any]]:
    value = _read_json(path, [])
    return value if isinstance(value, list) else []


def system_source_definitions() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for group, definitions in (("news", NEWS_QUERIES), ("special", SPECIAL_QUERIES)):
        for name, query, lang in definitions:
            identity = f"{group}:{name}:{query}:{lang}"
            rows.append({
                "id": _source_id("system", identity),
                "kind": "system_query",
                "name": name,
                "query": query,
                "lang": lang,
                "group": group,
                "system": True,
                "status": "active",
            })
    rows.append({
        "id": "system-truth-realdonaldtrump",
        "kind": "truth",
        "name": "Donald Trump",
        "handle": "@realDonaldTrump",
        "system": True,
        "status": "active",
    })
    return rows


def managed_source_rows(
    custom_path: Path = CUSTOM_SOURCES_PATH,
    overrides_path: Path = SOURCE_OVERRIDES_PATH,
) -> list[dict[str, Any]]:
    overrides = source_overrides(overrides_path)
    rows: list[dict[str, Any]] = []
    for base in system_source_definitions():
        row = dict(base)
        override = overrides.get(row["id"], {})
        if override.get("hidden"):
            continue
        row["active"] = bool(override.get("active", True))
        rows.append(row)
    for raw in custom_sources(custom_path):
        if raw.get("deleted"):
            continue
        row = dict(raw)
        row["system"] = False
        row.setdefault("active", True)
        rows.append(row)
    return rows


def _system_active(source_id: str, overrides: dict[str, dict[str, Any]]) -> bool:
    state = overrides.get(source_id, {})
    return not state.get("hidden") and bool(state.get("active", True))


def fetch_managed_base_news_items(session=requests) -> list[NewsItem]:
    merged: dict[str, NewsItem] = {}
    overrides = source_overrides()
    definitions = {row["id"]: row for row in system_source_definitions() if row["kind"] == "system_query"}
    for source_id, row in definitions.items():
        if not _system_active(source_id, overrides):
            continue
        fallback_source = str(row["name"])
        query = str(row["query"])
        lang = str(row["lang"])
        special = row.get("group") == "special"
        try:
            items = _fetch_google_news_query(session, fallback_source, query, lang, allow_special_source=special)
        except Exception:
            continue
        for item in items:
            combined = f"{item.title} {item.summary}"
            if fallback_source in {"TankerTrackers", "NOTAM / Airspace"} and not is_security_alert(combined):
                continue
            if fallback_source == "Al Arabiya" and not is_regional_security_alert(combined):
                continue
            merged.setdefault(item.key, item)
    return list(merged.values())


def _fetch_truth_account(handle: str, name: str, session=requests, limit: int = 40) -> list[RawNewsItem]:
    normalized = normalize_truth_handle(handle)
    lookup = session.get(
        "https://truthsocial.com/api/v1/accounts/lookup",
        params={"acct": normalized.lstrip("@")},
        headers={"User-Agent": USER_AGENT},
        timeout=20,
    )
    lookup.raise_for_status()
    account = lookup.json()
    account_id = str(account.get("id") or "").strip() if isinstance(account, dict) else ""
    if not account_id:
        return []
    response = session.get(
        f"https://truthsocial.com/api/v1/accounts/{account_id}/statuses",
        params={"exclude_replies": "true", "with_muted": "true", "limit": max(1, min(40, int(limit)))},
        headers={"User-Agent": USER_AGENT},
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        return []
    fetched_at = datetime.now(timezone.utc).isoformat()
    result: list[RawNewsItem] = []
    for status in payload:
        if not isinstance(status, dict):
            continue
        item = parse_truth_status(status, fetched_at=fetched_at)
        if item is not None:
            result.append(replace(item, source=f"{name} / Truth Social", source_priority="protected"))
    return result


def fetch_managed_truth_items(session=requests) -> list[RawNewsItem]:
    rows = managed_source_rows()
    result: list[RawNewsItem] = []
    for row in rows:
        if row.get("kind") != "truth" or not row.get("active", True):
            continue
        handle = str(row.get("handle") or "").strip()
        name = str(row.get("name") or handle.lstrip("@") or "Truth Social").strip()
        if row.get("system") and handle.lower() == "@realdonaldtrump":
            try:
                result.extend(fetch_trump_truth_items(session=session))
            except Exception:
                continue
            continue
        try:
            result.extend(_fetch_truth_account(handle, name, session=session))
        except Exception:
            continue
    return result
