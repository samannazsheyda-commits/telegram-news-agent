import os

from src.local_json_repository import LocalJsonRepository

from .app import create_app


config = {}
local_root = str(os.environ.get("PANEL_LOCAL_ROOT") or "").strip()
if local_root:
    config["DATA_BACKEND"] = LocalJsonRepository(local_root)

app = create_app(config)
