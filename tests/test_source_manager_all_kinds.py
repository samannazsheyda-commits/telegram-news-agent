from __future__ import annotations

import json
from pathlib import Path

import pytest

from panel.app import create_app
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


def test_sources_page_exposes_all_supported_source_types(client):
    response = client.get("/sources")
    text = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "X / Twitter" in text
    assert "Telegram" in text
    assert "Truth Social" in text
    assert "Website / RSS" in text


def test_add_telegram_source_persists_to_live_source_registry(client, app):
    response = client.post(
        "/sources/telegram",
        data={"tg-channel": "@rnintel", "tg-name": "RN Intel"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    record = next(r for r in _records(app) if r["kind"] == "telegram")
    assert record["channel"] == "rnintel"
    assert record["active"] is True


def test_add_truth_source_persists_to_live_source_registry(client, app):
    response = client.post(
        "/sources/truth",
        data={"truth-handle": "@realDonaldTrump", "truth-name": "Donald Trump"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    record = next(r for r in _records(app) if r["kind"] == "truth")
    assert record["handle"] == "@realDonaldTrump"
    assert record["active"] is True


def test_source_cards_render_identity_for_telegram_and_truth(client, app):
    (_root(app) / "data" / "custom_sources.json").write_text(json.dumps([
        {"id":"tg1","kind":"telegram","name":"Tabz","channel":"tabzlive","active":True,"status":"active"},
        {"id":"tr1","kind":"truth","name":"Donald Trump","handle":"@realDonaldTrump","active":True,"status":"active"},
    ]), encoding="utf-8")
    text = client.get("/sources").get_data(as_text=True)
    assert "@tabzlive" in text
    assert "@realDonaldTrump" in text
    assert "حذف" in text
    assert "خاموش" in text
