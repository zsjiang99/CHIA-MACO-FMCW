"""Loopback-only demo API: immutable archives and explicitly requested CHIA jobs."""
from __future__ import annotations

import fcntl
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import uuid
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, Field, ConfigDict
from typing import Literal

from .data import ARCHIVES, ROOT, array_model, read_json

RUNTIME = ROOT / "chia-maco/gui/runtime"
app = FastAPI(title="CHIA MACO Studio")
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])
_lock = threading.Lock()
_active: subprocess.Popen | None = None
_active_id: str | None = None


@app.middleware("http")
async def same_origin(request: Request, call_next):
    # The unauthenticated local demo must not launch jobs for another website.
    origin = request.headers.get("origin")
    if request.method == "POST" and origin and urlparse(origin).netloc != request.headers.get("host"):
        return JSONResponse({"detail": "Cross-origin job requests are not allowed"}, status_code=403)
    return await call_next(request)


@app.get("/api/health")
def health():
    return {"ok": True, "project": "maco", "mode": "local demo", "live_openroad": True,
            "active_job": _active_id if _active is not None and _active.poll() is None else None}


@app.get("/api/archive/maco")
def maco():
    return read_json(ARCHIVES["maco"])


@app.get("/api/array/{size}")
def geometry(size: int):
    if size not in (2, 4, 6):
        raise HTTPException(400, "Only the evaluated 2x2, 4x4, and 6x6 arrays are supported")
    return array_model(size)


@app.get("/api/download/{name}")
def download(name: str):
    if name != "maco":
        raise HTTPException(404, "Unknown archive")
    return FileResponse(ARCHIVES[name], filename=ARCHIVES[name].name)


class JobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["maco", "maco-agent", "cgra-verify", "cgra-synth", "cgra-layout"]
    workload: dict | None = None
    rounds: int = Field(default=3, ge=1, le=6)
    interpretation: dict | None = None
    architecture: dict | None = None


class DescriptionRequest(BaseModel):
    description: str = Field(min_length=1, max_length=4000)


@app.post("/api/workload/interpret")
def interpret_workload(spec: DescriptionRequest):
    from chia_maco.agent_search import AgentConfig, LocalModel
    from chia_maco.workload import interpret_description
    try:
        model = LocalModel(AgentConfig(max_tokens=512), lambda *args, **kwargs: None)
        result = interpret_description(spec.description, model)
        return {**result, "trace": model.calls, "model_identity": model.identity}
    except Exception as exc:
        raise HTTPException(422, f"Workload interpretation failed: {type(exc).__name__}: {exc}")


def latest_agent_path() -> Path:
    paths = list((ROOT / "chia-maco/results").glob("agent_*/agent_trace.json"))
    paths += list(RUNTIME.glob("*/agent_trace.json"))
    if not paths:
        raise HTTPException(404, "No agent execution yet")
    return max(paths, key=lambda p: p.stat().st_mtime).parent


@app.get("/api/agent/latest")
def latest_agent():
    path = latest_agent_path()
    progress = read_json(path / "progress.json")
    last = progress.get("events", [{}])[-1].get("kind")
    state = {"run_finished": "completed", "run_failed": "failed"}.get(last, "running")
    value = {"id": path.name, "kind": "maco-agent", "state": state, "progress": progress}
    if (path / "result.json").exists():
        value["result"] = read_json(path / "result.json")
    return value


@app.get("/api/agent/latest/trace")
def latest_agent_trace():
    return FileResponse(latest_agent_path() / "agent_trace.json", filename="agent_trace.json")


@app.get("/api/radar/design")
def radar_design():
    from .radar import design_view
    return design_view(latest_agent_path())


@app.get("/api/radar/demo")
@app.get("/api/radar/demo/{resource}")
def radar_demo(resource: str | None = None):
    path = ROOT / "chia-maco/results/agent_qwen38_27b_seed37_v3"
    if resource == "trace":
        return FileResponse(path / "agent_trace.json", filename="maco-demo-seed37.json")
    if resource == "guide":
        return FileResponse(ROOT / "chia-maco/DEMO.txt", media_type="text/plain", filename="MACO_DEMO.txt")
    if resource is not None:
        raise HTTPException(404, "Unknown demo resource")
    from .radar import design_view
    return design_view(path)


@app.get("/api/radar/validation")
@app.get("/api/radar/validation/{scene}")
def radar_validation(scene: str | None = None):
    from .radar import validation_view
    try:
        return validation_view(scene)
    except (ValueError, FileNotFoundError):
        raise HTTPException(404, "No validation evidence for this scene")


@app.get("/api/radar/rtl-audit")
def radar_rtl_audit():
    return read_json(ROOT / "chia-maco/results/rtl_audit/report.json")


@app.get("/api/radar/log/{run_id}/{index}")
def radar_log(run_id: str, index: int):
    latest_agent_path()
    allowed = {p.name: p for p in (ROOT / "chia-maco/results").glob("agent_*") if p.is_dir()}
    allowed.update({p.name: p for p in RUNTIME.glob("*") if p.is_dir()})
    if run_id not in allowed or not 0 <= index < 36:
        raise HTTPException(404, "Unknown mapper log")
    path = allowed[run_id] / f"mapper_logs/mapping_{index:03d}.log"
    if not path.is_file():
        raise HTTPException(404, "Mapper log not retained")
    return FileResponse(path, media_type="text/plain", filename=path.name)


def _job_dir(job_id: str) -> Path:
    if len(job_id) != 32 or any(c not in "0123456789abcdef" for c in job_id):
        raise HTTPException(404, "Unknown job")
    path = RUNTIME / job_id
    if not (path / "meta.json").is_file():
        raise HTTPException(404, "Unknown job")
    return path


def _finish(proc: subprocess.Popen, path: Path, log) -> None:
    code = proc.wait()
    log.close()
    meta = read_json(path / "meta.json")
    meta.update(state="completed" if code == 0 else "failed", return_code=code, finished_at=time.time())
    from .worker import save
    save(path / "meta.json", meta)


@app.post("/api/jobs", status_code=202)
def start_job(spec: JobRequest):
    global _active, _active_id
    if spec.kind.startswith("cgra-"):
        try:
            from chia_maco.cgra_flow import architecture_yaml
            architecture_yaml(spec.architecture or {})
        except ValueError as exc:
            raise HTTPException(422, str(exc))
    if spec.workload is not None:
        if spec.kind != "maco-agent":
            raise HTTPException(400, "Workload configuration requires a MACO agent job")
        from chia_maco.workload import Workload
        try:
            Workload.from_dict(spec.workload)
        except (ValueError, TypeError) as exc:
            raise HTTPException(422, str(exc))
        if spec.interpretation and spec.interpretation.get("unsupported"):
            raise HTTPException(422, "Revise unsupported requirements before launching")
    with _lock:
        if _active is not None and _active.poll() is None:
            raise HTTPException(409, "A CHIA job is already running")
        # The worker inherits this lock, so server restarts cannot create overlaps.
        RUNTIME.mkdir(parents=True, exist_ok=True)
        job_lock = (RUNTIME / "job.lock").open("a")
        try:
            fcntl.flock(job_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            job_lock.close()
            raise HTTPException(409, "Another demo worker holds the execution lock")
        if spec.kind in ("maco", "maco-agent", "cgra-verify", "cgra-synth", "cgra-layout"):
            images = ["cgra/neura-flow:20260114" if spec.kind.startswith("cgra-") else "cgramapper:v1"]
            for image in images:
                try:
                    probe = subprocess.run(["docker", "image", "inspect", image],
                                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
                    if probe.returncode:
                        job_lock.close()
                        raise HTTPException(503, f"Install the {image} Docker image before running this task")
                except (FileNotFoundError, subprocess.TimeoutExpired):
                    job_lock.close()
                    raise HTTPException(503, "Docker is unavailable; archived replay still works")
        job_id = uuid.uuid4().hex
        path = RUNTIME / job_id
        path.mkdir(parents=True)
        from .worker import save
        save(path / "request.json", spec.model_dump())
        save(path / "meta.json", {"id": job_id, "kind": spec.kind, "state": "running", "started_at": time.time()})
        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join([str(ROOT / "gui"), str(ROOT / "chia-maco/src"),
                                           env.get("PYTHONPATH", "")])
        log = (path / "worker.log").open("w")
        try:
            _active = subprocess.Popen([sys.executable, "-m", "backend.worker", spec.kind, str(path)],
                                       cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
                                       start_new_session=True, pass_fds=(job_lock.fileno(),))
        except OSError:
            log.close()
            save(path / "meta.json", {"id": job_id, "kind": spec.kind, "state": "failed"})
            raise HTTPException(503, "Could not start worker; check the local runtime log")
        finally:
            job_lock.close()
        _active_id = job_id
        threading.Thread(target=_finish, args=(_active, path, log), daemon=True).start()
        return {"id": job_id}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    path = _job_dir(job_id)
    meta = read_json(path / "meta.json")
    if meta["state"] == "running" and job_id != _active_id:
        meta["state"] = "unknown"
        meta["error"] = "Server restarted; worker status is unknown. Inspect local logs before starting another job."
    for name in ("progress", "result"):
        if (path / f"{name}.json").exists():
            meta[name] = read_json(path / f"{name}.json")
    if meta["state"] == "failed":
        meta["error"] = f"Worker failed. Inspect chia-maco/gui/runtime/{job_id}/worker.log on the host."
    return meta


@app.get("/api/jobs/{job_id}/log")
def job_log(job_id: str):
    path = _job_dir(job_id)
    log = path / ("cgra-flow.log" if (path / "cgra-flow.log").is_file() else "worker.log")
    if not log.is_file():
        raise HTTPException(404, "Job log is not available yet")
    return FileResponse(log, media_type="text/plain", filename=log.name)


@app.get("/api/jobs/{job_id}/implementation/{action}/log")
def implementation_log(job_id: str, action: str):
    if action not in ("verify", "synth", "layout"):
        raise HTTPException(404, "Unknown implementation stage")
    path = _job_dir(job_id) / "implementation" / action / "cgra-flow.log"
    if not path.is_file():
        raise HTTPException(404, "Stage log is not available yet")
    return FileResponse(path, media_type="text/plain", filename=f"{action}.log")


@app.get("/api/jobs/{job_id}/layout")
def job_layout(job_id: str):
    root = _job_dir(job_id)
    path = root / "layout.webp"
    if not path.is_file():
        path = root / "implementation/layout/layout.webp"
    if not path.is_file():
        raise HTTPException(404, "Layout is not available yet")
    return FileResponse(path, media_type="image/webp", filename="maco-cgra-layout.webp")


@app.get("/api/jobs/{job_id}/rtl")
def job_rtl(job_id: str):
    root = _job_dir(job_id)
    path = root / "candidate.sv"
    if not path.is_file():
        path = root / "implementation/verify/candidate.sv"
    if not path.is_file():
        raise HTTPException(404, "Generated SystemVerilog is not available yet")
    return FileResponse(path, media_type="text/plain", filename="candidate.sv")


DIST = ROOT / "chia-maco/gui/dist"
if DIST.is_dir():
    app.mount("/", StaticFiles(directory=DIST, html=True), name="demo")
