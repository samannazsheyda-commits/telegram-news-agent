from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock


_LOCK = Lock()
_DEFAULT_PATH = "/var/lib/bikhabar/luna_usage.json"


def _path() -> Path:
    configured = str(os.environ.get("LUNA_USAGE_PATH") or "").strip()
    return Path(configured or _DEFAULT_PATH)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _read() -> dict:
    try:
        value = json.loads(_path().read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _write(value: dict) -> None:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def _bucket(value: dict, key: str) -> dict:
    bucket = value.get(key)
    if not isinstance(bucket, dict):
        bucket = {}
        value[key] = bucket
    return bucket


def _bump(bucket: dict, *, model: str, kind: str, input_tokens: int, output_tokens: int, cached_tokens: int) -> None:
    bucket["requests"] = int(bucket.get("requests") or 0) + 1
    bucket["input_tokens"] = int(bucket.get("input_tokens") or 0) + max(0, int(input_tokens or 0))
    bucket["output_tokens"] = int(bucket.get("output_tokens") or 0) + max(0, int(output_tokens or 0))
    bucket["cached_input_tokens"] = int(bucket.get("cached_input_tokens") or 0) + max(0, int(cached_tokens or 0))
    by_model = bucket.get("by_model") if isinstance(bucket.get("by_model"), dict) else {}
    bucket["by_model"] = by_model
    model_key = str(model or "unknown")
    model_row = by_model.get(model_key) if isinstance(by_model.get(model_key), dict) else {}
    by_model[model_key] = model_row
    model_row["requests"] = int(model_row.get("requests") or 0) + 1
    model_row["input_tokens"] = int(model_row.get("input_tokens") or 0) + max(0, int(input_tokens or 0))
    model_row["output_tokens"] = int(model_row.get("output_tokens") or 0) + max(0, int(output_tokens or 0))
    model_row["cached_input_tokens"] = int(model_row.get("cached_input_tokens") or 0) + max(0, int(cached_tokens or 0))
    by_kind = bucket.get("by_kind") if isinstance(bucket.get("by_kind"), dict) else {}
    bucket["by_kind"] = by_kind
    by_kind[str(kind or "response")] = int(by_kind.get(str(kind or "response")) or 0) + 1


def record_usage(*, model: str, kind: str = "response", input_tokens: int = 0, output_tokens: int = 0, cached_tokens: int = 0) -> None:
    now = _now()
    day_key = now.strftime("%Y-%m-%d")
    month_key = now.strftime("%Y-%m")
    with _LOCK:
        value = _read()
        days = _bucket(value, "days")
        months = _bucket(value, "months")
        day = days.get(day_key) if isinstance(days.get(day_key), dict) else {}
        month = months.get(month_key) if isinstance(months.get(month_key), dict) else {}
        days[day_key] = day
        months[month_key] = month
        _bump(day, model=model, kind=kind, input_tokens=input_tokens, output_tokens=output_tokens, cached_tokens=cached_tokens)
        _bump(month, model=model, kind=kind, input_tokens=input_tokens, output_tokens=output_tokens, cached_tokens=cached_tokens)
        value["updated_at"] = now.isoformat()
        # Bound history so this stays a tiny operational file.
        for container, limit in ((days, 45), (months, 18)):
            for old_key in sorted(container)[:-limit]:
                container.pop(old_key, None)
        _write(value)


def _pricing_per_million(model: str) -> tuple[float, float, float]:
    """Best-effort local estimate; override prices in env when desired.

    Values are intentionally configurable because provider pricing can change.
    """
    name = str(model or "").casefold()
    if "luna" in name:
        defaults = (0.20, 1.20, 0.02)
    elif "terra" in name:
        defaults = (2.00, 12.00, 0.20)
    else:
        defaults = (0.0, 0.0, 0.0)
    prefix = reprice_key(model)
    return (
        float(os.environ.get(f"{prefix}_INPUT_PER_M", defaults[0])),
        float(os.environ.get(f"{prefix}_OUTPUT_PER_M", defaults[1])),
        float(os.environ.get(f"{prefix}_CACHED_PER_M", defaults[2])),
    )


def reprice_key(model: str) -> str:
    safe = "".join(ch if ch.isalnum() else "_" for ch in str(model or "MODEL").upper())
    return f"LUNA_PRICE_{safe}"


def _estimate(bucket: dict) -> float:
    total = 0.0
    by_model = bucket.get("by_model") if isinstance(bucket.get("by_model"), dict) else {}
    for model, row in by_model.items():
        if not isinstance(row, dict):
            continue
        input_price, output_price, cached_price = _pricing_per_million(model)
        input_tokens = int(row.get("input_tokens") or 0)
        cached = min(input_tokens, int(row.get("cached_input_tokens") or 0))
        uncached = max(0, input_tokens - cached)
        output = int(row.get("output_tokens") or 0)
        total += (uncached / 1_000_000) * input_price
        total += (cached / 1_000_000) * cached_price
        total += (output / 1_000_000) * output_price
    return round(total, 4)


def summary() -> dict:
    now = _now()
    value = _read()
    days = value.get("days") if isinstance(value.get("days"), dict) else {}
    months = value.get("months") if isinstance(value.get("months"), dict) else {}
    today = dict(days.get(now.strftime("%Y-%m-%d")) or {})
    month = dict(months.get(now.strftime("%Y-%m")) or {})
    today["estimated_usd"] = _estimate(today)
    month["estimated_usd"] = _estimate(month)
    return {"today": today, "month": month, "updated_at": str(value.get("updated_at") or "")}
