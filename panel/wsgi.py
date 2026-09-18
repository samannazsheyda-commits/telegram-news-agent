import os

from flask import session

from src.local_json_repository import LocalJsonRepository
from src.services import translate_to_fa

from .app import create_app
from .command_center import bp as command_center_bp
from .live_api import bp as live_api_bp
from .newsroom_api import bp as newsroom_api_bp
from .newsroom_v4_api import bp as newsroom_v4_api_bp
from .source_manager import bp as source_manager_bp
from .weather_preview import bp as weather_preview_bp


cookie_secure = str(os.environ.get("PANEL_COOKIE_SECURE", "0")).strip().lower() in {"1", "true", "yes", "on"}
config = {"SESSION_COOKIE_SECURE": cookie_secure}
local_root = str(os.environ.get("PANEL_LOCAL_ROOT") or "").strip()
if local_root:
    config["DATA_BACKEND"] = LocalJsonRepository(local_root)
config["LIVE_FEED_TRANSLATOR"] = translate_to_fa

app = create_app(config)

# The owner explicitly operates this VPS panel without a password. Keep the
# behavior configurable so authentication can be restored later without a code
# change, while making the production default match the current operating mode.
auth_disabled = str(os.environ.get("PANEL_AUTH_DISABLED", "1")).strip().lower() in {"1", "true", "yes", "on"}
if auth_disabled:
    @app.before_request
    def _passwordless_operator_session():
        session["admin"] = True

app.register_blueprint(command_center_bp)
app.register_blueprint(live_api_bp)
app.register_blueprint(newsroom_api_bp)
app.register_blueprint(newsroom_v4_api_bp)
app.register_blueprint(source_manager_bp)
app.register_blueprint(weather_preview_bp)
