import os

from src.local_json_repository import LocalJsonRepository
from src.services import translate_to_fa

from .app import create_app
from .command_center import bp as command_center_bp
from .live_api import bp as live_api_bp
from .luna_assistant import bp as luna_assistant_bp
from .newsroom_api import bp as newsroom_api_bp
from .source_manager import bp as source_manager_bp
from .v4 import bp as panel_v4_bp
from .weather_preview import bp as weather_preview_bp


# The current VPS panel is intentionally served over plain HTTP on port 80.
# A Secure session cookie is not returned by browsers over HTTP, which breaks
# Flask-WTF CSRF validation on the login POST. Keep HTTP as the deployment
# default and allow a future HTTPS reverse proxy to opt in explicitly.
cookie_secure = str(os.environ.get("PANEL_COOKIE_SECURE", "0")).strip().lower() in {"1", "true", "yes", "on"}
config = {
    "SESSION_COOKIE_SECURE": cookie_secure,
    # Luna accepts bounded image/voice uploads. Individual endpoints enforce
    # tighter file limits before provider requests.
    "MAX_CONTENT_LENGTH": 12 * 1024 * 1024,
}
local_root = str(os.environ.get("PANEL_LOCAL_ROOT") or "").strip()
if local_root:
    config["DATA_BACKEND"] = LocalJsonRepository(local_root)
config["LIVE_FEED_TRANSLATOR"] = translate_to_fa

app = create_app(config)
app.register_blueprint(command_center_bp)
app.register_blueprint(live_api_bp)
app.register_blueprint(newsroom_api_bp)
app.register_blueprint(source_manager_bp)
app.register_blueprint(panel_v4_bp)
app.register_blueprint(luna_assistant_bp)
app.register_blueprint(weather_preview_bp)
