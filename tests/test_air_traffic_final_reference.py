from pathlib import Path

import src.air_traffic_reference as air_traffic


def test_final_reference_crop_matches_latest_user_screenshot():
    bounds = air_traffic.viewport_bounds()
    assert 38.5 <= bounds["min_lon"] <= 39.5
    assert 67.5 <= bounds["max_lon"] <= 68.5
    assert 10.5 <= bounds["min_lat"] <= 12.0
    assert 47.5 <= bounds["max_lat"] <= 49.0
    assert 53.0 <= air_traffic.CENTER_LON <= 54.0
    assert 31.0 <= air_traffic.CENTER_LAT <= 32.0


def test_final_reference_uses_bright_voyager_basemap_and_high_res_render():
    assert "basemaps.cartocdn.com" in air_traffic.BASEMAP_URL
    assert "/voyager/" in air_traffic.BASEMAP_URL
    assert air_traffic.RENDER_WIDTH > air_traffic.MAP_WIDTH
    assert air_traffic.RENDER_HEIGHT > air_traffic.MAP_HEIGHT


def test_publish_workflow_and_vps_service_use_final_reference_renderer():
    workflow = Path(".github/workflows/air-traffic.yml").read_text(encoding="utf-8")
    service = Path("deploy/bikhabar-air-traffic.service").read_text(encoding="utf-8")
    assert "python -m src.air_traffic_reference --publish" in workflow
    assert "-m src.air_traffic_reference --publish" in service
