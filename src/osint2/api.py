"""The one FastAPI app. Locally it runs jobs in-process; on Modal the same app is mounted and the
job backend is swapped for spawn/poll (see deploy/modal_app.py). Models and routes live at module
scope on purpose: FastAPI cannot resolve string annotations for locally scoped names."""
from __future__ import annotations

import asyncio
import json
import os
import uuid
from pathlib import Path
from typing import Any, Optional, Protocol

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .agent import run_investigation
from .config import Settings


class InvestigateRequest(BaseModel):
    target: str = Field(min_length=2, max_length=500)
    max_tool_calls: Optional[int] = Field(default=None, ge=1, le=200)
    max_usd: Optional[float] = Field(default=None, gt=0, le=20)
    max_seconds: Optional[int] = Field(default=None, ge=30, le=7200)


class JobBackend(Protocol):
    def submit(self, target: str, overrides: dict[str, Any]) -> str: ...
    def status(self, job_id: str) -> dict[str, Any]: ...
    def trace(self, job_id: str) -> Optional[str]: ...
    def source(self, job_id: str, source_id: str) -> Optional[str]: ...


def clamp_overrides(body: InvestigateRequest, settings: Settings, authorized: bool) -> dict[str, Any]:
    """Anonymous callers cannot raise budgets above the shipped defaults, so a public URL cannot
    spend the reserve. A caller with the API key may."""
    ov: dict[str, Any] = {}
    if body.max_tool_calls is not None:
        ov["MAX_TOOL_CALLS"] = body.max_tool_calls if authorized else min(body.max_tool_calls, settings.max_tool_calls)
    if body.max_usd is not None:
        ov["MAX_USD"] = body.max_usd if authorized else min(body.max_usd, settings.max_usd)
    if body.max_seconds is not None:
        ov["MAX_SECONDS"] = body.max_seconds if authorized else min(body.max_seconds, settings.max_seconds)
    return ov


class LocalBackend:
    """In-process jobs for local runs and tests."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.jobs: dict[str, dict[str, Any]] = {}

    def submit(self, target: str, overrides: dict[str, Any]) -> str:
        job_id = uuid.uuid4().hex[:12]
        self.jobs[job_id] = {"status": "queued", "partial": None, "report": None, "error": None, "workspace": None}

        def on_step(p: dict[str, Any]) -> None:
            self.jobs[job_id]["partial"] = p
            self.jobs[job_id]["status"] = "running"

        async def run() -> None:
            self.jobs[job_id]["status"] = "running"
            try:
                settings = Settings.from_env(overrides)
                report, ws = await run_investigation(target, settings, on_step=on_step)
                self.jobs[job_id].update(status="done", report=report, workspace=str(ws.dir))
            except Exception as exc:  # noqa: BLE001
                self.jobs[job_id].update(status="failed", error={"type": type(exc).__name__, "message": str(exc)[:500]})

        asyncio.create_task(run())
        return job_id

    def status(self, job_id: str) -> dict[str, Any]:
        job = self.jobs.get(job_id)
        if job is None:
            raise KeyError(job_id)
        out = {"job_id": job_id, "status": job["status"]}
        if job["status"] in ("queued", "running"):
            out["partial"] = job["partial"]
        elif job["status"] == "done":
            out["report"] = job["report"]
            out["trace_url"] = f"/jobs/{job_id}/trace"
        else:
            out["error"] = job["error"]
        return out

    def _ws(self, job_id: str) -> Optional[Path]:
        job = self.jobs.get(job_id)
        return Path(job["workspace"]) if job and job.get("workspace") else None

    def trace(self, job_id: str) -> Optional[str]:
        ws = self._ws(job_id)
        p = ws / "trace.jsonl" if ws else None
        return p.read_text() if p and p.exists() else None

    def source(self, job_id: str, source_id: str) -> Optional[str]:
        ws = self._ws(job_id)
        if not ws:
            return None
        sources = json.loads((ws / "sources.json").read_text()) if (ws / "sources.json").exists() else []
        rel = next((s["path"] for s in sources if s["id"] == source_id), None)
        return (ws / rel).read_text() if rel and (ws / rel).exists() else None


def create_app(backend: JobBackend, settings: Settings) -> FastAPI:
    app = FastAPI(title="osint-agent-v2", version="0.1.0")

    def authorized(key: Optional[str]) -> bool:
        return bool(settings.agent_api_key) and key == settings.agent_api_key

    @app.get("/healthz")
    def healthz() -> dict[str, Any]:
        return {"ok": True, "tools": list(settings.tools), "deep_dive": settings.deep_dive,
                "defaults": {"max_tool_calls": settings.max_tool_calls, "max_usd": settings.max_usd, "max_seconds": settings.max_seconds},
                "keys": {"openrouter": bool(settings.openrouter_api_key), "perplexity": bool(settings.perplexity_api_key),
                         "exa": bool(settings.exa_api_key), "firecrawl": bool(settings.firecrawl_api_key), "github": bool(settings.github_token)}}

    @app.post("/investigate", status_code=202)
    def investigate(body: InvestigateRequest, x_api_key: Optional[str] = Header(default=None)) -> dict[str, Any]:
        ov = clamp_overrides(body, settings, authorized(x_api_key))
        job_id = backend.submit(body.target.strip(), ov)
        return {"job_id": job_id, "status": "queued", "poll_url": f"/jobs/{job_id}", "budgets": {**{"MAX_TOOL_CALLS": settings.max_tool_calls, "MAX_USD": settings.max_usd, "MAX_SECONDS": settings.max_seconds}, **ov}}

    @app.get("/jobs/{job_id}")
    def job(job_id: str) -> dict[str, Any]:
        try:
            return backend.status(job_id)
        except KeyError:
            raise HTTPException(404, "unknown job id")

    @app.get("/jobs/{job_id}/trace", response_class=PlainTextResponse)
    def trace(job_id: str) -> str:
        text = backend.trace(job_id)
        if text is None:
            raise HTTPException(404, "no trace for this job (not finished, or unknown id)")
        return text

    @app.get("/jobs/{job_id}/sources/{source_id}", response_class=PlainTextResponse)
    def source(job_id: str, source_id: str) -> str:
        text = backend.source(job_id, source_id)
        if text is None:
            raise HTTPException(404, "unknown job or source id")
        return text

    # The built frontend (web/dist) is served at "/" when present, so the page and the API share an origin.
    dist = Path(os.environ.get("WEB_DIST", str(Path(__file__).resolve().parents[2] / "web" / "dist")))
    if (dist / "index.html").exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/", include_in_schema=False)
        def index() -> FileResponse:
            return FileResponse(dist / "index.html")

    return app


def local_app() -> FastAPI:
    settings = Settings.from_env()
    return create_app(LocalBackend(settings), settings)


app = local_app()
