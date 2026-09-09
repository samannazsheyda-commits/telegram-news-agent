import os

from src.local_json_repository import LocalJsonRepository

from .app import create_app
from .command_center import bp as command_center_bp
from .live_api import bp as live_api_bp
from .source_manager import bp as source_manager_bp
from .weather_preview import bp as weather_preview_bp


config = {
    # Never perform network translation while rendering the VPS panel. The
    # newsroom agent prepares Persian text asynchronously; the dashboard only
    # reads local runtime state so it remains responsive.
    "LIVE_FEED_TRANSLATOR": lambda text: "",
}
local_root = str(os.environ.get("PANEL_LOCAL_ROOT") or "").strip()
if local_root:
    config["DATA_BACKEND"] = LocalJsonRepository(local_root)
    config["SESSION_COOKIE_SECURE"] = str(os.environ.get("PANEL_COOKIE_SECURE", "0")).strip().lower() in {"1", "true", "yes", "on"}

app = create_app(config)
app.register_blueprint(command_center_bp)
app.register_blueprint(live_api_bp)
app.register_blueprint(source_manager_bp)
app.register_blueprint(weather_preview_bp)
