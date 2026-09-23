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


def run(kind: str, output: Path) -> None:
    os.environ.setdefault("RAY_NODE_IP_ADDRESS", "127.0.0.1")
    if kind.startswith("cgra-"):
        from chia_maco.cgra_flow import run as run_cgra_flow
        request = json.loads((output / "request.json").read_text())
        run_cgra_flow(kind.removeprefix("cgra-"), request["architecture"], output)
        return
    if kind == "maco-agent":
        from chia_maco.agent_search import AgentConfig, run_agent_search
        from chia_maco.workload import Workload
        request = json.loads((output / "request.json").read_text()) if (output / "request.json").exists() else {}
        if request.get("workload"):
            run_agent_search(output, config=AgentConfig(rounds=request.get("rounds", 3), max_tokens=768),
                             workload=Workload.from_dict(request["workload"]))
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
