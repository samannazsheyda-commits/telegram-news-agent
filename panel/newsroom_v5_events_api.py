from __future__ import annotations

from flask import Blueprint, Response, abort, current_app, request, stream_with_context

from panel.app import login_required


bp = Blueprint("newsroom_v5_events", __name__, url_prefix="/api/v5")


@bp.get("/events")
@login_required
def events():
    broker = current_app.extensions.get("newsroom_v5_events")
    if broker is None:
        abort(503, description="Newsroom V5 event broker is not enabled")
    raw_last = request.headers.get("Last-Event-ID") or request.args.get("last_event_id") or "0"
    try:
        last_event_id = max(0, int(raw_last))
    except ValueError:
        last_event_id = 0
    response = Response(
        stream_with_context(broker.stream(last_event_id)),
        mimetype="text/event-stream",
    )
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response.headers["X-Accel-Buffering"] = "no"
    response.headers["Connection"] = "keep-alive"
    return response
