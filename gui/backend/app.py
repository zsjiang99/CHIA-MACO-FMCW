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
allowed_hosts = ["127.0.0.1", "localhost", "testserver"]
allowed_hosts += [host.strip() for host in os.environ.get("A3_GUI_ALLOWED_HOSTS", "").split(",") if host.strip()]
app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)
_lock = threading.Lock()


def _worker_pid(job_id: str) -> int | None:
    """Find this job's live worker, including after an API-server restart."""
    path = RUNTIME / job_id
    expected = str(path)
    meta_path = path / "meta.json"
    candidates: list[int] = []
    if meta_path.is_file():
        pid = read_json(meta_path).get("worker_pid")
        if isinstance(pid, int):
            candidates.append(pid)
    for entry in Path("/proc").glob("[0-9]*"):
        try:
            pid = int(entry.name)
        except ValueError:
            continue
        if pid not in candidates:
            candidates.append(pid)
    for pid in candidates:
        try:
            argv = (Path("/proc") / str(pid) / "cmdline").read_bytes().split(b"\0")
            args = [arg.decode(errors="replace") for arg in argv if arg]
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            continue
        if "backend.worker" in args and expected in args:
            return pid
    return None


def _running_jobs() -> list[tuple[float, str, str]]:
    if not RUNTIME.is_dir():
        return []
    running: list[tuple[float, str, str]] = []
    for meta_path in RUNTIME.glob("*/meta.json"):
        try:
            meta = read_json(meta_path)
        except (OSError, ValueError):
            continue
        job_id = meta_path.parent.name
        if meta.get("state") == "running" and _worker_pid(job_id) is not None:
            running.append((float(meta.get("started_at", 0)), job_id, str(meta.get("kind", ""))))
    return sorted(running)


def _job_group(kind: str) -> str:
    return "layout" if kind == "cgra-layout" else "workflow"


@app.middleware("http")
async def same_origin(request: Request, call_next):
    # The unauthenticated local demo must not launch jobs for another website.
    origin = request.headers.get("origin")
    public_origin = os.environ.get("A3_GUI_PUBLIC_ORIGIN", "").rstrip("/")
    local_origin = origin and urlparse(origin).netloc == request.headers.get("host")
    tunnel_origin = origin and public_origin and origin.rstrip("/") == public_origin
    if request.method == "POST" and origin and not (local_origin or tunnel_origin):
        return JSONResponse({"detail": "Cross-origin job requests are not allowed"}, status_code=403)
    return await call_next(request)


@app.get("/api/health")
def health():
    jobs = _running_jobs()
    return {"ok": True, "project": "maco", "mode": "local demo", "live_openroad": True,
            "active_job": jobs[-1][1] if jobs else None,
            "active_jobs": [job_id for _, job_id, _ in jobs]}


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
    rounds: int = Field(default=2, ge=1, le=6)
    method: Literal["full_maco", "hardware_only", "single_agent"] = "full_maco"
    interpretation: dict | None = None
    architecture: dict | None = None
    source_run: str | None = None


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


def latest_measured_path() -> Path:
    """Keep the last complete design visible while a new search is starting."""
    if PROJECT != "maco":
        raise HTTPException(404, "Not available in this project")
    paths = list((ROOT / "chia-maco/results").glob("agent_*/progress.json"))
    paths += list(RUNTIME.glob("*/progress.json"))
    measured = []
    for path in paths:
        try:
            if any(event.get("kind") == "design_measured"
                   and event.get("frame_estimate", {}).get("valid")
                   for event in read_json(path).get("events", [])):
                measured.append(path)
        except (OSError, ValueError):
            continue
    if not measured:
        raise HTTPException(404, "No fully mapped design is available")
    return max(measured, key=lambda path: path.stat().st_mtime).parent


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
    return design_view(latest_measured_path())


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
    group = _job_group(spec.kind)
    if spec.kind == "cgra-layout":
        if not spec.source_run:
            raise HTTPException(422, "Select a completed MACO run before layout")
        source = _job_dir(spec.source_run)
        if read_json(source / "meta.json").get("kind") != "maco-agent":
            raise HTTPException(422, "Layout requires a completed MACO run")
        record_path = source / "implementation.json"
        if not record_path.is_file():
            raise HTTPException(422, "RTL verification and synthesis must finish before layout")
        record = read_json(record_path)
        stages = record.get("stages", {})
        if any(stages.get(name, {}).get("state") != "passed" for name in ("verify", "synth")):
            raise HTTPException(422, "RTL verification and synthesis must finish before layout")
        from chia_maco.evidence import candidate_id
        winner = read_json(source / "result.json").get("best_evaluated_plan") or {}
        if (not winner.get("design") or not winner.get("architecture")
                or record.get("design_id") != candidate_id(winner["design"])
                or (spec.architecture or {}).get("design") != winner["design"]):
            raise HTTPException(422, "Layout architecture must match the verified design")
        spec.architecture = {"design": winner["design"], "architecture": winner["architecture"]}
    elif spec.source_run is not None:
        raise HTTPException(422, "source_run is only valid for optional layout")
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
        for _, _, running_kind in _running_jobs():
            if _job_group(running_kind) == group:
                label = "layout" if group == "layout" else "MACO workflow"
                raise HTTPException(409, f"A {label} job is already running")
        # Layout and the main workflow have isolated outputs and may run together.
        # A group-specific inherited lock prevents duplicate starts across servers.
        RUNTIME.mkdir(parents=True, exist_ok=True)
        job_lock = (RUNTIME / f"{group}.lock").open("a")
        try:
            fcntl.flock(job_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            job_lock.close()
            raise HTTPException(409, f"Another {group} job is already running")
        if spec.kind in ("maco", "maco-agent", "cgra-verify", "cgra-synth", "cgra-layout"):
            images = (["cgramapper:v1", "cgra/neura-flow:20260114"] if spec.kind == "maco-agent" and spec.workload
                      else ["cgra/neura-flow:20260114" if spec.kind.startswith("cgra-") else "cgramapper:v1"])
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
            proc = subprocess.Popen([sys.executable, "-m", "backend.worker", spec.kind, str(path)],
                                    cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
                                    start_new_session=True, pass_fds=(job_lock.fileno(),))
            meta = read_json(path / "meta.json")
            save(path / "meta.json", {**meta, "worker_pid": proc.pid})
        except OSError:
            log.close()
            save(path / "meta.json", {"id": job_id, "kind": spec.kind, "state": "failed"})
            raise HTTPException(503, "Could not start worker; check the local runtime log")
        finally:
            job_lock.close()
        threading.Thread(target=_finish, args=(proc, path, log), daemon=True).start()
        return {"id": job_id}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    path = _job_dir(job_id)
    meta = read_json(path / "meta.json")
    if meta["state"] == "running":
        worker_pid = _worker_pid(job_id)
        if worker_pid is None:
            meta["state"] = "unknown"
            meta["error"] = "The worker is no longer running. Inspect the local task log."
        else:
            meta["worker_pid"] = worker_pid
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
