"""Isolated live CHIA jobs. Writes only to the caller's new runtime directory."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import time


def save(path: Path, data: dict) -> None:
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(data, indent=2) + "\n")
    temp.replace(path)


def complete_maco_flow(output: Path, search: dict) -> None:
    from chia_maco.cgra_flow import run as run_cgra_flow
    from chia_maco.evidence import candidate_id

    winner = search.get("best_evaluated_plan")
    if not winner or not winner.get("architecture"):
        raise RuntimeError("No mapped, measurable design is available for hardware implementation")
    payload = {"design": winner["design"], "architecture": winner["architecture"]}
    record = {"state": "running", "design_id": candidate_id(winner["design"]),
              "current": None, "stages": {name: {"state": "pending"} for name in ("verify", "synth", "layout")}}
    target = output / "implementation.json"
    for action in ("verify", "synth"):
        path = output / "implementation" / action
        path.mkdir(parents=True, exist_ok=False)
        record["current"] = action
        record["stages"][action] = {"state": "running"}
        save(target, record)
        try:
            run_cgra_flow(action, payload, path)
            result = json.loads((path / "result.json").read_text())
            if result.get("status") != "passed":
                raise RuntimeError(result.get("error", f"{action} did not pass"))
        except Exception as error:
            result_path = path / "result.json"
            detail = json.loads(result_path.read_text()).get("error") if result_path.is_file() else None
            record["state"] = "failed"
            record["stages"][action] = {"state": "failed", "error": detail or str(error)}
            save(target, record)
            raise
        record["stages"][action] = {"state": "passed", "result": result}
        save(target, record)
    record.update(state="passed", current=None)
    save(target, record)


def run(kind: str, output: Path) -> None:
    os.environ.setdefault("RAY_NODE_IP_ADDRESS", "127.0.0.1")
    if kind.startswith("cgra-"):
        from chia_maco.cgra_flow import run as run_cgra_flow
        request = json.loads((output / "request.json").read_text())
        action = kind.removeprefix("cgra-")
        source = output.parent / request["source_run"] if action == "layout" else None
        if source:
            target = source / "implementation.json"
            record = json.loads(target.read_text())
            record["stages"]["layout"] = {"state": "running", "job_id": output.name}
            save(target, record)
        try:
            run_cgra_flow(action, request["architecture"], output)
            if source:
                result = json.loads((output / "result.json").read_text())
                if result.get("status") != "passed":
                    raise RuntimeError(result.get("error", "Layout did not pass"))
                record["stages"]["layout"] = {"state": "passed", "job_id": output.name, "result": result}
                save(target, record)
        except Exception as error:
            if source:
                result_path = output / "result.json"
                detail = json.loads(result_path.read_text()).get("error") if result_path.is_file() else None
                record["stages"]["layout"] = {"state": "failed", "job_id": output.name, "error": detail or str(error)}
                save(target, record)
            raise
        return
    if kind == "maco-agent":
        from chia_maco.agent_search import AgentConfig, run_agent_search
        from chia_maco.workload import Workload
        request = json.loads((output / "request.json").read_text()) if (output / "request.json").exists() else {}
        if request.get("workload"):
            search = run_agent_search(output, config=AgentConfig(rounds=request.get("rounds", 3), max_tokens=4096),
                                      workload=Workload.from_dict(request["workload"]),
                                      method=request.get("method", "full_maco"))
            complete_maco_flow(output, search)
        else:
            run_agent_search(output)
        return
    import ray
    from chia.base.ChiaFunction import get

    started = time.monotonic()
    if kind != "maco":
        raise ValueError(f"Unsupported MACO job: {kind}")
    resources = {"cgra_mapper": 1}
    ray.init(include_dashboard=False, num_cpus=2, resources=resources)
    try:
        from chia_maco.nodes import evaluate_candidate
        from chia_maco.schema import MappingResult
        from chia_maco.search import search_candidates, summarize_search
        results = []
        candidates = search_candidates()
        for candidate in candidates:
            value = get(evaluate_candidate.chia_remote(candidate.to_dict()))
            results.append(MappingResult.from_dict(value))
            save(output / "progress.json", {
                "completed": len(results), "total": len(candidates),
                "raw_results": [r.to_dict() for r in results],
            })
        result = summarize_search(results, "chia", time.monotonic() - started)
        result["demo_policy"] = "deterministic enumeration; not LLM search"
        save(output / "result.json", result)
    finally:
        ray.shutdown()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=["maco", "maco-agent",
                                         "cgra-verify", "cgra-synth", "cgra-layout"])
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        run(args.kind, args.output)
    except BaseException:
        meta = json.loads((args.output / "meta.json").read_text())
        save(args.output / "meta.json", {**meta, "state": "failed", "finished_at": time.time()})
        raise
    else:
        meta = json.loads((args.output / "meta.json").read_text())
        save(args.output / "meta.json", {**meta, "state": "completed", "finished_at": time.time()})
