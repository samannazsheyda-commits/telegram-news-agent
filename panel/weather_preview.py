from __future__ import annotations

from flask import Blueprint, current_app, flash, redirect, session, url_for

from src.weather_digest import build_preview


bp = Blueprint("weather_preview", __name__)


def _data():
    return current_app.extensions["editorial_data"]


def _current_preview() -> dict:
    value, _ = _data().read_json("data/weather_preview.json", {})
    return value if isinstance(value, dict) else {}


@bp.app_context_processor
def inject_weather_preview():
    return {"weather_preview": _current_preview()}


@bp.post("/weather-preview/refresh")
def refresh():
    if not session.get("admin"):
        return redirect(url_for("login"))
    try:
        preview = build_preview()
    except Exception as exc:
        flash(f"ساخت پیش‌نمایش هواشناسی ناموفق بود: {type(exc).__name__}", "error")
        return redirect(url_for("dashboard"))

    data = _data()
    _, sha = data.read_json("data/weather_preview.json", {})
    data.write_json("data/weather_preview.json", preview, sha, "panel: refresh weather preview")
    flash("پیش‌نمایش هواشناسی به‌روز شد؛ چیزی در کانال منتشر نشد.", "success")
    return redirect(url_for("dashboard"))
