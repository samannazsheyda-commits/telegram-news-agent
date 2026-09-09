from __future__ import annotations

import hashlib
from dataclasses import asdict
from datetime import datetime, timezone

import requests
from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for

from src.custom_sources import ThreadsSource, XSource, discover_feed_url, normalize_telegram_channel, validate_website_source
from src.managed_sources import normalize_truth_handle, system_source_definitions


bp = Blueprint("source_manager", __name__)


def _authenticated() -> bool:
    return bool(session.get("admin"))


@bp.before_request
def _require_admin():
    if not _authenticated():
        return redirect(url_for("login", next=request.path))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _data():
    return current_app.extensions["editorial_data"]


def _read(path: str, default):
    value, _ = _data().read_json(path, default)
    return value


def _mutate(path: str, default, transform, message: str):
    data = _data()
    for attempt in range(3):
        value, sha = data.read_json(path, default)
        updated = transform(value)
        try:
            data.write_json(path, updated, sha, message)
            return updated
        except requests.HTTPError as exc:
            if attempt < 2 and getattr(exc.response, "status_code", None) in {409, 422}:
                continue
            raise
    raise RuntimeError("source_manager_write_conflict")


def _custom_id(kind: str, identity: str) -> str:
    return hashlib.sha1(f"{kind}:{identity.lower()}".encode("utf-8")).hexdigest()


def _rows():
    custom = _read("data/custom_sources.json", [])
    overrides = _read("data/source_overrides.json", {})
    if not isinstance(custom, list):
        custom = []
    if not isinstance(overrides, dict):
        overrides = {}
    rows = []
    for base in system_source_definitions():
        row = dict(base)
        state = overrides.get(row["id"], {}) if isinstance(overrides.get(row["id"], {}), dict) else {}
        if state.get("hidden"):
            continue
        row["active"] = bool(state.get("active", True))
        row["identity"] = row.get("handle") or row.get("query") or ""
        rows.append(row)
    for source in custom:
        if not isinstance(source, dict) or source.get("deleted"):
            continue
        row = dict(source)
        row["system"] = False
        row.setdefault("active", True)
        if row.get("kind") == "telegram":
            row["identity"] = "@" + str(row.get("channel") or "").lstrip("@")
        elif row.get("kind") in {"x", "threads", "truth"}:
            row["identity"] = str(row.get("handle") or "")
        elif row.get("kind") == "website":
            row["identity"] = str(row.get("feed_url") or row.get("website_url") or "")
        else:
            row["identity"] = ""
        rows.append(row)
    order = {"telegram": 0, "x": 1, "threads": 2, "truth": 3, "website": 4, "system_query": 5}
    rows.sort(key=lambda row: (order.get(str(row.get("kind")), 9), str(row.get("name") or "").lower()))
    return rows


@bp.get("/source-manager")
def index():
    rows = _rows()
    counts = {}
    for row in rows:
        kind = str(row.get("kind") or "other")
        counts[kind] = counts.get(kind, 0) + 1
    return render_template("source_manager.html", sources=rows, counts=counts)


@bp.post("/source-manager/add")
def add_source():
    kind = str(request.form.get("kind") or "").strip().lower()
    name = str(request.form.get("name") or "").strip()
    identity = str(request.form.get("identity") or "").strip()
    feed_url = str(request.form.get("feed_url") or "").strip()
    try:
        if kind == "x":
            record = asdict(XSource.create(identity, name))
        elif kind == "threads":
            record = asdict(ThreadsSource.create(identity, name))
        elif kind == "telegram":
            channel = normalize_telegram_channel(identity)
            record = {"id": _custom_id("telegram", channel), "kind": "telegram", "name": name or channel, "channel": channel, "active": True, "status": "active", "last_checked_at": "", "last_error": "", "updated_at": _now()}
        elif kind == "truth":
            handle = normalize_truth_handle(identity)
            record = {"id": _custom_id("truth", handle), "kind": "truth", "name": name or handle.lstrip("@"), "handle": handle, "active": True, "status": "active", "last_checked_at": "", "last_error": "", "updated_at": _now()}
        elif kind == "website":
            record = asdict(validate_website_source(name or identity, identity, feed_url))
            if not record.get("feed_url"):
                try:
                    discovered = discover_feed_url(record["website_url"])
                except Exception as exc:
                    discovered = ""
                    record["last_error"] = str(exc)[:240]
                if discovered:
                    record["feed_url"] = discovered
                    record["status"] = "active"
        else:
            raise ValueError("unsupported_source_kind")
    except ValueError:
        flash("مشخصات منبع معتبر نیست.", "error")
        return redirect(url_for("source_manager.index"))

    def transform(value):
        records = list(value) if isinstance(value, list) else []
        records = [row for row in records if not isinstance(row, dict) or row.get("id") != record["id"]]
        records.insert(0, record)
        return records

    _mutate("data/custom_sources.json", [], transform, "panel: add managed source")
    flash("منبع اضافه شد و از اسکن بعدی وارد رصد می‌شود.", "success")
    return redirect(url_for("source_manager.index"))


@bp.post("/source-manager/<source_id>/toggle")
def toggle(source_id: str):
    system_ids = {row["id"] for row in system_source_definitions()}
    if source_id in system_ids:
        def transform(value):
            overrides = dict(value) if isinstance(value, dict) else {}
            state = dict(overrides.get(source_id) or {})
            state["active"] = not bool(state.get("active", True))
            state["updated_at"] = _now()
            overrides[source_id] = state
            return overrides
        _mutate("data/source_overrides.json", {}, transform, "panel: toggle system source")
    else:
        def transform(value):
            records = list(value) if isinstance(value, list) else []
            for row in records:
                if isinstance(row, dict) and row.get("id") == source_id:
                    row["active"] = not bool(row.get("active", True))
                    row["updated_at"] = _now()
                    break
            return records
        _mutate("data/custom_sources.json", [], transform, "panel: toggle custom source")
    return redirect(url_for("source_manager.index"))


@bp.post("/source-manager/<source_id>/delete")
def delete(source_id: str):
    system_ids = {row["id"] for row in system_source_definitions()}
    if source_id in system_ids:
        def transform(value):
            overrides = dict(value) if isinstance(value, dict) else {}
            state = dict(overrides.get(source_id) or {})
            state.update({"active": False, "hidden": True, "updated_at": _now()})
            overrides[source_id] = state
            return overrides
        _mutate("data/source_overrides.json", {}, transform, "panel: hide system source")
    else:
        def transform(value):
            records = list(value) if isinstance(value, list) else []
            return [row for row in records if not isinstance(row, dict) or row.get("id") != source_id]
        _mutate("data/custom_sources.json", [], transform, "panel: delete custom source")
    flash("منبع از رصد حذف شد.", "success")
    return redirect(url_for("source_manager.index"))
