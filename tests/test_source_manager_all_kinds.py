from __future__ import annotations

import json
from pathlib import Path

import pytest

from panel.app import create_app
from panel.source_manager import bp as source_manager_bp
from src.local_json_repository import LocalJsonRepository


@pytest.fixture()
def app(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "custom_sources.json").write_text("[]\n", encoding="utf-8")
    monkeypatch.setenv("PANEL_SECRET_KEY", "test-secret")
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "test-secret",
        "WTF_CSRF_ENABLED": False,
        "DATA_BACKEND": LocalJsonRepository(tmp_path),
    })
    app.register_blueprint(source_manager_bp)
    return app


@pytest.fixture()
def client(app):
    client = app.test_client()
    with client.session_transaction() as session:
        session["admin"] = True
    return client


def _root(app) -> Path:
    return Path(app.extensions["editorial_data"].root)


def _records(app):
    return json.loads((_root(app) / "data" / "custom_sources.json").read_text(encoding="utf-8"))


def test_sources_page_exposes_all_supported_source_types_and_system_feeds(client):
    response = client.get("/source-manager")
    text = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "X / Twitter" in text
    assert "Telegram" in text
    assert "Truth Social" in text
    assert "Website / RSS" in text
    assert "Reuters" in text
    assert "Associated Press" in text
    assert "فیدهای خبری سیستم" in text


def test_add_telegram_source_persists_to_live_source_registry(client, app):
    response = client.post(
        "/source-manager/add",
        data={"kind": "telegram", "identity": "@rnintel", "name": "RN Intel"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    record = next(r for r in _records(app) if r["kind"] == "telegram")
    assert record["channel"] == "rnintel"
    assert record["active"] is True


def test_add_truth_source_persists_to_live_source_registry(client, app):
    response = client.post(
        "/source-manager/add",
        data={"kind": "truth", "identity": "@realDonaldTrump", "name": "Donald Trump"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    record = next(r for r in _records(app) if r["kind"] == "truth")
    assert record["handle"] == "@realDonaldTrump"
    assert record["active"] is True


def test_source_cards_render_identity_for_telegram_and_truth(client, app):
    (_root(app) / "data" / "custom_sources.json").write_text(json.dumps([
        {"id":"tg1","kind":"telegram","name":"Tabz","channel":"tabzlive","active":True,"status":"active"},
        {"id":"tr1","kind":"truth","name":"Donald Trump 2","handle":"@realDonaldTrump2","active":True,"status":"active"},
    ]), encoding="utf-8")
    text = client.get("/source-manager").get_data(as_text=True)
    assert "@tabzlive" in text
    assert "@realDonaldTrump2" in text
    assert "حذف" in text
    assert "خاموش" in text


def test_system_source_can_be_disabled_without_code_deploy(client, app):
    text = client.get("/source-manager").get_data(as_text=True)
    assert "Reuters" in text
    from src.managed_sources import system_source_definitions
    reuters = next(row for row in system_source_definitions() if row.get("name") == "Reuters")
    response = client.post(f"/source-manager/{reuters['id']}/toggle", follow_redirects=True)
    assert response.status_code == 200
    overrides = json.loads((_root(app) / "data" / "source_overrides.json").read_text(encoding="utf-8"))
    assert overrides[reuters["id"]]["active"] is False
