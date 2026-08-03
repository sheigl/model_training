"""API tests for the dashboard FastAPI app (with process_manager stubbed)."""

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

import app
import config


@pytest.fixture
def client():
    with TestClient(app.app) as c:
        yield c


def test_index_serves_dashboard(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "MTG Generator Dashboard" in r.text


def test_list_generators(client):
    r = client.get("/api/generators")
    assert r.status_code == 200
    data = r.json()
    assert len(data["generators"]) == 27
    slugs = {g["slug"] for g in data["generators"]}
    assert "synergy" in slugs and "combos" in slugs
    for g in data["generators"]:
        assert g["name"].startswith("Generate")
        assert g["default_model"], "snapshot should expose script model default"
        assert g["default_validation_model"]
        assert "$" not in g["default_model"], "env refs must be resolved"


def test_start_generator(monkeypatch, client):
    captured = {}

    def fake_start(spec, count, model, validation_model, validation_pct, dry_run):
        captured["slug"] = spec.slug
        captured["count"] = count
        captured["dry_run"] = dry_run
        return 4242

    monkeypatch.setattr(app.process_manager, "start", fake_start)

    r = client.post("/api/generators/synergy/start", json={"count": 5, "dry_run": True})
    assert r.status_code == 200
    assert r.json()["pid"] == 4242
    assert captured == {"slug": "synergy", "count": 5, "dry_run": True}


def test_start_resolves_default_models(monkeypatch, client):
    captured = {}

    def fake_start(spec, count, model, validation_model, validation_pct, dry_run):
        captured["model"] = model
        captured["validation_model"] = validation_model
        return 1

    monkeypatch.setattr(app.process_manager, "start", fake_start)
    client.post("/api/generators/synergy/start", json={"count": 1})
    assert captured["model"]
    assert captured["validation_model"]
    assert "$" not in captured["model"]


def test_stop_generator(monkeypatch, client):
    monkeypatch.setattr(app.process_manager, "stop", lambda spec: [1, 2, 3])
    r = client.post("/api/generators/synergy/stop")
    assert r.status_code == 200
    assert r.json()["killed"] == [1, 2, 3]


def test_unknown_generator(client):
    assert client.post("/api/generators/nope/start", json={}).status_code == 404
    assert client.post("/api/generators/nope/stop").status_code == 404
    assert client.get("/api/logs/nope").status_code == 404


def test_resolve_env_refs(monkeypatch):
    monkeypatch.setenv("FOO", "bar")
    assert app._resolve_env_refs("$FOO/${FOO}") == "bar/bar"
    assert app._resolve_env_refs("${MISSING_XYZ}") == ""


def test_events_stream_yields_snapshot():
    async def first():
        agen = app._event_stream()
        return await agen.__anext__()

    payload = json.loads(asyncio.run(first()).removeprefix("data: "))
    assert "generators" in payload
    assert len(payload["generators"]) == 27


def test_logs_stream_yields_init(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "LOGS_DIR", tmp_path)
    spec = config.GENERATOR_BY_SLUG["synergy"]

    async def first():
        agen = app._log_stream(spec)
        return await agen.__anext__()

    payload = json.loads(asyncio.run(first()).removeprefix("data: "))
    assert payload["type"] == "init"
    assert payload["lines"] == []
    assert payload["log_path"].endswith("synergy.log")
