"""Modal deployment. The same FastAPI app as src/osint2/api.py, mounted through @modal.asgi_app, with
the job backend swapped for spawn/poll: POST /investigate spawns a worker function and returns its
call id; GET /jobs/{id} polls it and serves live progress from a modal.Dict while it runs. Run
workspaces live on a Volume mounted by both the worker and the web container, so the trace and the
source files are servable after the worker exits.

    uv run modal deploy deploy/modal_app.py

Gotcha carried over from v1: the app and its models must be defined at module scope, or FastAPI
cannot resolve the string annotations that `from __future__ import annotations` produces.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

import modal

ROOT = Path(__file__).resolve().parents[1]
RUNS = "/runs"

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("fastapi[standard]>=0.115", "httpx>=0.27", "openai>=1.50", "pydantic>=2.8", "rapidfuzz>=3.9")
    .add_local_python_source("osint2")
    .add_local_dir(str(ROOT / "web" / "dist"), remote_path="/root/web/dist")
)
app = modal.App("osint-agent-v2")
secrets = modal.Secret.from_dotenv(ROOT)
runs_volume = modal.Volume.from_name("osint2-runs", create_if_missing=True)
progress = modal.Dict.from_name("osint2-progress", create_if_missing=True)


@app.function(image=image, secrets=[secrets], volumes={RUNS: runs_volume}, timeout=7200)
async def investigate_remote(target: str, overrides: dict[str, Any]) -> dict[str, Any]:
    import os
    os.environ["RUNS_DIR"] = RUNS
    from osint2.agent import run_investigation
    from osint2.config import Settings
    call_id = modal.current_function_call_id()

    def on_step(p: dict[str, Any]) -> None:
        progress[call_id] = p

    try:
        settings = Settings.from_env(overrides)
        report, ws = await run_investigation(target, settings, runs_dir=Path(RUNS), on_step=on_step)
        runs_volume.commit()
        out = {"status": "done", "report": report, "workspace": str(ws.dir)}
    except Exception as exc:  # noqa: BLE001
        out = {"status": "failed", "error": {"type": type(exc).__name__, "message": str(exc)[:500]}}
    finally:
        progress.pop(call_id, None)
    return out


class ModalBackend:
    def submit(self, target: str, overrides: dict[str, Any]) -> str:
        call = investigate_remote.spawn(target, overrides)
        return call.object_id

    def _result(self, job_id: str) -> Optional[dict[str, Any]]:
        try:
            fc = modal.FunctionCall.from_id(job_id)
            return fc.get(timeout=0)
        except TimeoutError:
            return None

    def status(self, job_id: str) -> dict[str, Any]:
        try:
            res = self._result(job_id)
        except Exception as exc:  # noqa: BLE001
            if "not found" in str(exc).lower():
                raise KeyError(job_id)
            return {"job_id": job_id, "status": "failed", "error": {"type": type(exc).__name__, "message": str(exc)[:300]}}
        if res is None:
            return {"job_id": job_id, "status": "running", "partial": progress.get(job_id)}
        if res.get("status") == "done":
            return {"job_id": job_id, "status": "done", "report": res["report"], "trace_url": f"/jobs/{job_id}/trace"}
        return {"job_id": job_id, "status": "failed", "error": res.get("error")}

    def _ws(self, job_id: str) -> Optional[Path]:
        try:
            res = self._result(job_id)
        except Exception:  # noqa: BLE001
            return None
        if not res or not res.get("workspace"):
            return None
        runs_volume.reload()
        return Path(res["workspace"])

    def trace(self, job_id: str) -> Optional[str]:
        ws = self._ws(job_id)
        p = ws / "trace.jsonl" if ws else None
        return p.read_text() if p and p.exists() else None

    def source(self, job_id: str, source_id: str) -> Optional[str]:
        ws = self._ws(job_id)
        if not ws or not (ws / "sources.json").exists():
            return None
        sources = json.loads((ws / "sources.json").read_text())
        rel = next((s["path"] for s in sources if s["id"] == source_id), None)
        return (ws / rel).read_text() if rel and (ws / rel).exists() else None


@app.function(image=image, secrets=[secrets], volumes={RUNS: runs_volume})
@modal.asgi_app()
def web():
    import os
    os.environ.setdefault("WEB_DIST", "/root/web/dist")
    from osint2.api import create_app
    from osint2.config import Settings
    return create_app(ModalBackend(), Settings.from_env())
