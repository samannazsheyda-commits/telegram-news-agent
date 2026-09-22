from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


_SPACE_RE = re.compile(r"\s+")
_TRACKING_KEYS = frozenset({"fbclid", "gclid", "igshid", "mc_cid", "mc_eid"})


def _text(value: str | None) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or ""))
    return _SPACE_RE.sub(" ", normalized).strip().casefold()


def _timestamp(value: str | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return raw
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def canonicalize_url(value: str | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    parsed = urlsplit(raw)
    scheme = parsed.scheme.lower()
    host = (parsed.hostname or "").lower()
    port = parsed.port
    if port and not ((scheme == "https" and port == 443) or (scheme == "http" and port == 80)):
        host = f"{host}:{port}"
    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/")
    query = sorted(
        (key, item)
        for key, item in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in _TRACKING_KEYS
    )
    return urlunsplit((scheme, host, path, urlencode(query), ""))


def story_fingerprint(
    *,
    source: str,
    source_url: str | None,
    original_title: str,
    published_at_source: str | None,
) -> str:
    payload = {
        "source": _text(source),
        "url": canonicalize_url(source_url),
        "title": _text(original_title),
        "published_at_source": _timestamp(published_at_source),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def ensure_story_identity(story: Mapping[str, Any]) -> dict[str, Any]:
    prepared = dict(story)
    prepared["source_url"] = canonicalize_url(str(prepared.get("source_url") or ""))
    fingerprint = str(prepared.get("fingerprint") or "").strip()
    if not fingerprint:
        fingerprint = story_fingerprint(
            source=str(prepared.get("source") or ""),
            source_url=str(prepared.get("source_url") or ""),
            original_title=str(prepared.get("original_title") or ""),
            published_at_source=str(prepared.get("published_at_source") or ""),
        )
    prepared["fingerprint"] = fingerprint
    return prepared
