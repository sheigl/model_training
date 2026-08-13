"""API tests for scraper start/stop/logs endpoints."""

import json

import pytest
from fastapi.testclient import TestClient

import app
import config
from conftest import run_async


@pytest.fixture
def client():
    with TestClient(app.app) as c:
        yield c


def test_snapshot_includes_scrapers(client):
    data = client.get("/api/generators").json()
    assert len(data["generators"]) == 27
    scrapers = data["scrapers"]
    assert len(scrapers) == 9
    slugs = {s["slug"] for s in scrapers}
    assert "edhrec_commanders" in slugs and "commander_spellbook" in slugs
    for s in scrapers:
        assert s["script"].endswith(".py")
        assert "slug" in s and "name" in s and "args" in s


def test_list_scrapers_endpoint(client):
    data = client.get("/api/scrapers").json()
    assert len(data["scrapers"]) == 9


def test_start_scraper(monkeypatch, client):
    captured = {}

    def fake_start(spec, extra_args):
        captured["slug"] = spec.slug
        captured["extra"] = extra_args
        return 5555

    monkeypatch.setattr(app.process_manager, "start_scraper", fake_start)

    r = client.post("/api/scrapers/edhrec_commanders/start", json={"args": "--guides --articles"})
    assert r.status_code == 200
    assert r.json()["pid"] == 5555
    assert captured == {"slug": "edhrec_commanders", "extra": ["--guides", "--articles"]}


def test_start_scraper_empty_args(monkeypatch, client):
    captured = {}

    def fake_start(spec, extra_args):
        captured["extra"] = extra_args
        return 1

    monkeypatch.setattr(app.process_manager, "start_scraper", fake_start)
    client.post("/api/scrapers/commander_spellbook/start", json={"args": ""})
    assert captured["extra"] == []


def test_stop_scraper(monkeypatch, client):
    monkeypatch.setattr(app.process_manager, "stop_scraper", lambda spec: [7])
    r = client.post("/api/scrapers/funtrivia/stop")
    assert r.status_code == 200
    assert r.json()["killed"] == [7]


def test_unknown_scraper(client):
    assert client.post("/api/scrapers/nope/start", json={}).status_code == 404
    assert client.post("/api/scrapers/nope/stop").status_code == 404
    assert client.get("/api/scraper-logs/nope").status_code == 404


def test_scraper_logs_stream_yields_init(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "LOGS_DIR", tmp_path)
    spec = config.SCRAPER_BY_SLUG["mtg_archetypes"]

    async def first():
        agen = app._scraper_log_stream(spec)
        return await agen.__anext__()

    payload = json.loads(run_async(first()).removeprefix("data: "))
    assert payload["type"] == "init"
    assert payload["lines"] == []
    assert payload["log_path"].endswith("mtg_archetypes.log")
