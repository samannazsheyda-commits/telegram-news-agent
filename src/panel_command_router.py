from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .panel_command_file import apply_command as apply_legacy_command

TERMINAL = {"succeeded", "failed", "reconciled"}
NEWSROOM_ACTIONS = {
    "clear", "settings_save",
    "weather_now", "air_traffic_now", "tanker_now", "market_now",
    "weather_preview", "air_traffic_preview", "tanker_preview", "market_preview",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default


def _atomic_write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
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


def _result_path(command_id: str) -> Path:
    return Path("panel_results") / f"{command_id}.json"


def _write_result(
    command_id: str,
    action: str,
    status: str,
    message: str,
    *,
    scope: str = "",
    ids: list[str] | None = None,
) -> dict:
    payload = {
        "command_id": command_id,
        "item_id": "",
        "action": action,
        "status": status,
        "message": message,
        "scope": scope,
        "ids": list(ids or []),
        "updated_at": _now(),
    }
    _atomic_write(_result_path(command_id), payload)
    return payload


def _consume(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def _command_payload(path: Path) -> dict[str, Any]:
    payload = _read_json(path, None)
    if not isinstance(payload, dict):
        raise ValueError("invalid_command")
    command_id = str(payload.get("command_id") or path.stem).strip()
    action = str(payload.get("action") or "").strip()
    if not command_id:
        raise ValueError("missing_command_id")
    if not action:
        raise ValueError("missing_action")
    payload["command_id"] = command_id
    payload["action"] = action
    return payload


def _validated_ids(value: Any) -> list[str]:
    if not isinstance(value, list):
        raise ValueError("ids_must_be_list")
    ids: list[str] = []
    seen: set[str] = set()
    for raw in value:
        item_id = str(raw or "").strip()
        if not item_id or item_id in seen:
            continue
        seen.add(item_id)
        ids.append(item_id)
    if len(ids) > 5000:
        raise ValueError("too_many_ids")
    return ids


def _clear_live(ids: list[str]) -> int:
    path = Path("data/panel_live_feed.json")
    targets = set(ids)
    before = _read_json(path, [])
    if not isinstance(before, list):
        before = []

    def identity(row: Any) -> str:
        if not isinstance(row, dict):
            return ""
        return str(row.get("item_id") or row.get("id") or row.get("news_key") or "")

    after = [row for row in before if identity(row) not in targets]
    removed = len(before) - len(after)
    if removed:
        _atomic_write(path, after)
    return removed


def _apply_clear(payload: dict[str, Any]) -> dict:
    command_id = payload["command_id"]
    scope = str(payload.get("scope") or "").strip()
    ids = _validated_ids(payload.get("ids"))
    if scope != "live":
        raise ValueError("invalid_clear_scope")
    count = _clear_live(ids)
    return _write_result(
        command_id,
        "clear",
        "succeeded",
        f"{count} خبر فقط از فید پنل پاک شد؛ تلگرام دست‌نخورده ماند",
        scope=scope,
        ids=ids,
    )


def _normalise_settings(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("settings_must_be_object")
    settings = dict(value)
    settings["updated_at"] = _now()
    settings["version"] = int(settings.get("version") or 1)
    settings["freshness_hours"] = max(1, min(48, int(settings.get("freshness_hours") or 3)))
    settings["earthquake_min"] = max(0.0, min(10.0, float(settings.get("earthquake_min") or 2.0)))
    settings["earthquake_breaking"] = max(
        settings["earthquake_min"], min(10.0, float(settings.get("earthquake_breaking") or 4.0))
    )
    if settings.get("dedup_mode") not in {"strict", "balanced", "loose"}:
        settings["dedup_mode"] = "strict"
    if settings.get("notam_sensitivity") not in {"high", "normal", "critical"}:
        settings["notam_sensitivity"] = "high"
    settings["emergency_lock"] = bool(settings.get("emergency_lock", False))
    settings["auto_publish"] = bool(settings.get("auto_publish", True))
    settings["quiet_mode"] = bool(settings.get("quiet_mode", False))
    priority_terms = settings.get("priority_terms")
    if not isinstance(priority_terms, list):
        settings["priority_terms"] = []
    else:
        settings["priority_terms"] = [str(term).strip() for term in priority_terms if str(term).strip()][:20]
    for key in ("market", "alerts", "ui", "sources"):
        if not isinstance(settings.get(key), dict):
            settings[key] = {}
    return settings


def _apply_settings(payload: dict[str, Any]) -> dict:
    settings = _normalise_settings(payload.get("settings"))
    _atomic_write(Path("data/newsroom_settings.json"), settings)
    return _write_result(payload["command_id"], "settings_save", "succeeded", "تنظیمات اتاق خبر ذخیره شد")


def _save_preview(name: str, preview: dict) -> None:
    if not isinstance(preview, dict):
        raise ValueError("invalid_preview")
    _atomic_write(Path("data") / f"{name}_preview.json", preview)


def _apply_module(payload: dict[str, Any]) -> dict:
    action = payload["action"]
    command_id = payload["command_id"]
    if action == "weather_preview":
        from .weather_digest import build_preview, save_preview

        preview = build_preview()
        save_preview(preview)
        _save_preview("weather", preview)
        return _write_result(command_id, action, "succeeded", "پیش‌نمایش هواشناسی به‌روز شد؛ چیزی منتشر نشد")
    if action == "air_traffic_preview":
        from .air_traffic import build_air_traffic_preview

        preview = build_air_traffic_preview()
        _save_preview("air_traffic", preview)
        return _write_result(command_id, action, "succeeded", "پیش‌نمایش ترافیک هوایی به‌روز شد؛ چیزی منتشر نشد")
    if action == "tanker_preview":
        from .panel_modules import build_hormuz_preview

        preview = build_hormuz_preview()
        _save_preview("tanker", preview)
        return _write_result(command_id, action, "succeeded", "پیش‌نمایش هرمز به‌روز شد؛ چیزی منتشر نشد")
    if action == "market_preview":
        from .panel_modules import build_market_preview

        preview = build_market_preview()
        _save_preview("market", preview)
        return _write_result(command_id, action, "succeeded", "پیش‌نمایش بازار به‌روز شد؛ چیزی منتشر نشد")
    if action == "weather_now":
        from .weather_digest import run as run_weather

        rc = int(run_weather(force=True) or 0)
        if rc != 0:
            raise RuntimeError(f"weather_failed_rc_{rc}")
        return _write_result(command_id, action, "succeeded", "هواشناسی همین حالا منتشر شد")
    if action == "air_traffic_now":
        from .air_traffic import publish_air_traffic_snapshot

        publish_air_traffic_snapshot()
        return _write_result(command_id, action, "succeeded", "نقشه ترافیک هوایی همین حالا منتشر شد")
    if action == "tanker_now":
        from .panel_modules import publish_hormuz_now

        publish_hormuz_now()
        return _write_result(command_id, action, "succeeded", "گزارش نفتکش‌ها و تنگه هرمز منتشر شد")
    if action == "market_now":
        from .panel_modules import publish_market_now

        publish_market_now()
        return _write_result(command_id, action, "succeeded", "گزارش بازار همین حالا منتشر شد")
    raise ValueError("unsupported_module_action")


def apply_command(path: str | Path) -> dict:
    command_path = Path(path)
    if not command_path.exists():
        existing = _read_json(_result_path(command_path.stem), None)
        if isinstance(existing, dict) and existing.get("status") in TERMINAL:
            return existing
        raise FileNotFoundError(command_path)

    payload = _command_payload(command_path)
    action = payload["action"]
    if action not in NEWSROOM_ACTIONS:
        return apply_legacy_command(command_path)

    existing = _read_json(_result_path(payload["command_id"]), None)
    if isinstance(existing, dict) and existing.get("status") in TERMINAL:
        _consume(command_path)
        return existing

    _write_result(payload["command_id"], action, "processing", "در حال پردازش")
    try:
        if action == "clear":
            result = _apply_clear(payload)
        elif action == "settings_save":
            result = _apply_settings(payload)
        else:
            result = _apply_module(payload)
        _consume(command_path)
        return result
    except Exception as exc:
        result = _write_result(
            payload["command_id"],
            action,
            "failed",
            str(exc),
            scope=str(payload.get("scope") or ""),
            ids=list(payload.get("ids") or []),
        )
        _consume(command_path)
        return result


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: python -m src.panel_command_router <command.json>")
    result = apply_command(sys.argv[1])
    print(json.dumps(result, ensure_ascii=False))
    if result.get("status") == "failed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
