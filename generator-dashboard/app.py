#!/usr/bin/env python3
"""Generator dashboard — FastAPI + SSE control panel for the MTG generators.

Usage:
    uv run --project generator-dashboard app.py [--host 127.0.0.1] [--port 8080]

Serves a tabbed web UI showing each generator's status, live log output,
validation metrics, and Start/Stop controls backed by the ``run_*.sh`` scripts.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from pathlib import Path

# Allow running as a plain script (`python generator-dashboard/app.py`) and
# under pytest without a parent package (the directory name has a hyphen, so
# it cannot be imported as a package).
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from config import (
    DEFAULT_MODEL,
    DEFAULT_VALIDATION_MODEL,
    GENERATORS,
    GENERATOR_BY_SLUG,
    MONGO_PASS,
    MONGO_URI,
    MONGO_USER,
    SCRAPERS,
    SCRAPER_BY_SLUG,
    GeneratorSpec,
    ScraperSpec,
    script_model_defaults,
)
from log_tailer import LogTailer
from metrics_store import MetricsStore
import process_manager

STATIC_DIR = Path(__file__).resolve().parent / "static"
REPO_ROOT = Path(__file__).resolve().parent.parent

app = FastAPI(title="MTG Generator Dashboard")

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

metrics_store = MetricsStore(MONGO_URI, MONGO_USER, MONGO_PASS)

ENV_REF_RE = re.compile(r"\$\{(\w+)\}|\$(\w+)")


def _resolve_env_refs(value: str) -> str:
    """Substitute ``$VAR`` / ``${VAR}`` references from the environment."""

    def _sub(match: re.Match) -> str:
        name = match.group(1) or match.group(2)
        return os.environ.get(name, "")

    return ENV_REF_RE.sub(_sub, value)


def _sse(obj) -> str:
    return f"data: {json.dumps(obj, default=str)}\n\n"


def _instance_summary(insts: list[process_manager.RunningInstance]) -> list[dict]:
    return [{"pid": i.pid, "count": i.count} for i in insts]


def _snapshot() -> dict:
    running = process_manager.scan_running()
    generators = []
    for spec in GENERATORS:
        insts = running.get(spec.slug, [])
        log_path = spec.log_path
        script_model, script_validation = script_model_defaults(spec)
        generators.append(
            {
                "slug": spec.slug,
                "name": spec.class_name,
                "category": spec.category,
                "flag": spec.flag,
                "script": spec.script.name,
                "default_count": spec.default_count,
                "default_model": _resolve_env_refs(script_model or DEFAULT_MODEL),
                "default_validation_model": _resolve_env_refs(script_validation or DEFAULT_VALIDATION_MODEL),
                "running": bool(insts),
                "instances": _instance_summary(insts),
                "log_exists": log_path.exists(),
                "log_size": log_path.stat().st_size if log_path.exists() else 0,
                "metrics": metrics_store.latest(spec.class_name),
            }
        )

    scrapers_running = process_manager.scan_scrapers()
    scrapers = []
    for spec in SCRAPERS:
        insts = scrapers_running.get(spec.slug, [])
        log_path = spec.log_path
        scrapers.append(
            {
                "slug": spec.slug,
                "name": spec.name,
                "description": spec.description,
                "script": spec.python_script,
                "args": spec.default_args_str,
                "running": bool(insts),
                "instances": _instance_summary(insts),
                "log_exists": log_path.exists(),
                "log_size": log_path.stat().st_size if log_path.exists() else 0,
            }
        )
    return {
        "generators": generators,
        "scrapers": scrapers,
        "mongo_connected": metrics_store.connected,
        "tick": True,
    }


# =============================================================================
# HTML / static
# =============================================================================


@app.get("/")
def index() -> FileResponse:
    return FileResponse(str(STATIC_DIR / "index.html"))


# =============================================================================
# REST
# =============================================================================


class StartPayload(BaseModel):
    count: int = Field(default=100, ge=1, le=1_000_000)
    model: str | None = None
    validation_model: str | None = None
    validation_pct: float = Field(default=1.0, ge=0.0, le=1.0)
    dry_run: bool = False


@app.get("/api/generators")
def list_generators() -> dict:
    return _snapshot()


@app.post("/api/generators/{slug}/start")
def start_generator(slug: str, payload: StartPayload) -> dict:
    spec = _get_spec(slug)
    model = _resolve_env_refs(payload.model) if payload.model else _default_model()
    validation_model = (
        _resolve_env_refs(payload.validation_model) if payload.validation_model else _default_validation_model()
    )
    try:
        pid = process_manager.start(
            spec,
            count=payload.count,
            model=model,
            validation_model=validation_model,
            validation_pct=payload.validation_pct,
            dry_run=payload.dry_run,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start: {e}")
    return {"ok": True, "slug": slug, "pid": pid, "log_path": str(spec.log_path)}


@app.post("/api/generators/{slug}/stop")
def stop_generator(slug: str) -> dict:
    spec = _get_spec(slug)
    killed = process_manager.stop(spec)
    return {"ok": True, "slug": slug, "killed": killed}


class ScraperStartPayload(BaseModel):
    args: str = Field(default="", description="Extra CLI args appended after the scraper's defaults")


@app.get("/api/scrapers")
def list_scrapers() -> dict:
    return _snapshot()


@app.post("/api/scrapers/{slug}/start")
def start_scraper(slug: str, payload: ScraperStartPayload) -> dict:
    spec = _get_scraper(slug)
    extra_args = payload.args.split() if payload.args.strip() else []
    try:
        pid = process_manager.start_scraper(spec, extra_args=extra_args)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start: {e}")
    return {"ok": True, "slug": slug, "pid": pid, "log_path": str(spec.log_path)}


@app.post("/api/scrapers/{slug}/stop")
def stop_scraper(slug: str) -> dict:
    spec = _get_scraper(slug)
    killed = process_manager.stop_scraper(spec)
    return {"ok": True, "slug": slug, "killed": killed}


# =============================================================================
# SSE
# =============================================================================


@app.get("/api/events")
async def events() -> StreamingResponse:
    return StreamingResponse(_event_stream(), media_type="text/event-stream")


async def _event_stream():
    while True:
        yield _sse(_snapshot())
        await asyncio.sleep(2)


@app.get("/api/logs/{slug}")
async def logs(slug: str) -> StreamingResponse:
    spec = _get_spec(slug)
    return StreamingResponse(_log_stream(spec), media_type="text/event-stream")


async def _log_stream(spec: GeneratorSpec):
    tailer = LogTailer(spec.log_path)

    yield _sse({"type": "init", "lines": tailer.tail(500), "log_path": str(spec.log_path)})
    last_trace = 0.0
    while True:
        lines = tailer.new_lines()
        if lines:
            yield _sse({"type": "lines", "lines": lines})
        now = asyncio.get_event_loop().time()
        if now - last_trace >= 3:
            last_trace = now
            yield _sse(
                {
                    "type": "traces",
                    "traces": metrics_store.recent_traces(spec.category),
                }
            )
        await asyncio.sleep(1)


@app.get("/api/scraper-logs/{slug}")
async def scraper_logs(slug: str) -> StreamingResponse:
    spec = _get_scraper(slug)
    return StreamingResponse(_scraper_log_stream(spec), media_type="text/event-stream")


async def _scraper_log_stream(spec: ScraperSpec):
    tailer = LogTailer(spec.log_path)

    yield _sse({"type": "init", "lines": tailer.tail(500), "log_path": str(spec.log_path)})
    while True:
        lines = tailer.new_lines()
        if lines:
            yield _sse({"type": "lines", "lines": lines})
        await asyncio.sleep(1)


# =============================================================================
# Helpers
# =============================================================================


def _get_spec(slug: str) -> GeneratorSpec:
    spec = GENERATOR_BY_SLUG.get(slug)
    if spec is None:
        raise HTTPException(status_code=404, detail=f"Unknown generator: {slug}")
    return spec


def _get_scraper(slug: str) -> ScraperSpec:
    spec = SCRAPER_BY_SLUG.get(slug)
    if spec is None:
        raise HTTPException(status_code=404, detail=f"Unknown scraper: {slug}")
    return spec


def _default_model() -> str:
    from config import DEFAULT_MODEL

    return _resolve_env_refs(DEFAULT_MODEL)


def _default_validation_model() -> str:
    from config import DEFAULT_VALIDATION_MODEL

    return _resolve_env_refs(DEFAULT_VALIDATION_MODEL)


# =============================================================================
# CLI
# =============================================================================


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="MTG Generator Dashboard")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8080, help="Port to bind (default: 8080)")
    parser.add_argument("--mongo-uri", default=MONGO_URI)
    parser.add_argument("--mongo-user", default=MONGO_USER)
    parser.add_argument("--mongo-pass", default=MONGO_PASS)
    return parser


def main() -> None:
    args = build_parser().parse_args()

    global metrics_store
    metrics_store = MetricsStore(args.mongo_uri, args.mongo_user, args.mongo_pass)

    print(f"MTG Generator Dashboard → http://{args.host}:{args.port}")

    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
