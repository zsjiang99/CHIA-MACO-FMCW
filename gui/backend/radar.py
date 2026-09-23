"""Candidate-linked views of recorded evidence; no experiments on GET requests."""
from functools import lru_cache
from pathlib import Path

from .data import ROOT, ARCHIVES, read_json
from chia_maco.agent_search import candidates_for, mapping_key
from chia_maco.schema import CoDesignCandidate
from chia_maco.workload import Workload
from chia_maco.evidence import candidate_id, mapper_metrics, parse_schedule

VALIDATION = ROOT / "chia-maco/results/validation_v1"


@lru_cache(maxsize=128)
def schedule(path: str, modified: int, mapping_json: str):
    import json
    return parse_schedule(Path(path).read_text(), json.loads(mapping_json))


def design_view(run: Path):
    import json
    p = read_json(run / "progress.json")
    raw = p["raw_results"]
    workload = Workload.from_dict(p["workload"]) if p.get("workload") else None
    def key_without_control_memory(candidate):
        value = json.loads(mapping_key(candidate))
        value.pop("control_memory", None)
        return json.dumps(value, sort_keys=True)

    exact = {mapping_key(CoDesignCandidate.from_dict(r["candidate"])): (i, r)
             for i, r in enumerate(raw)}
    legacy = {key_without_control_memory(CoDesignCandidate.from_dict(r["candidate"])): (i, r)
              for i, r in enumerate(raw)}
    entries = []
    for event in p["events"]:
        if event["kind"] != "design_measured":
            continue
        design = event["design"]
        mappings = []
        for c in candidates_for(design, workload):
            i, mapping = exact.get(mapping_key(c)) or legacy[key_without_control_memory(c)]
            log = run / f"mapper_logs/mapping_{i:03d}.log"
            overlay = schedule(str(log), log.stat().st_mtime_ns, json.dumps(mapping, sort_keys=True)) if log.exists() else {"available": False, "placements": [], "links": []}
            mappings.append({**mapping, "schedule": overlay, "log_index": i})
        architecture = event.get("architecture")
        if architecture and mappings:
            architecture = {**architecture, "control_memory": mappings[0]["candidate"]["control_memory"]}
        entries.append({"id": candidate_id(design), "event": event["sequence"], "round": event["round"],
                        "design": design, "frame_estimate": event["frame_estimate"], "mappings": mappings,
                        "architecture": architecture, "memory": event.get("memory"), "energy": event.get("energy"),
                        "metrics": mapper_metrics(event["frame_estimate"].get("estimated_cycles"), f"{run.name}/agent_trace.json#event-{event['sequence']}")})
    baseline = read_json(ROOT / "chia-maco/configs/baseline.json")
    archive = read_json(ARCHIVES["maco"])
    reference_best = min((a["frame_estimate"]["estimated_cycles"] for a in archive["architectures"]
                          if a["all_kernels_feasible"]))
    result_path = run / "result.json"
    result = read_json(result_path) if result_path.is_file() else None
    native_validation = read_json(VALIDATION / "validation.json")
    implementation = read_json(run / "implementation.json") if (run / "implementation.json").is_file() else None
    if implementation and implementation.get("current"):
        phase = implementation["current"]
        step = run / "implementation" / phase / "progress.json"
        if step.is_file():
            implementation["detail"] = read_json(step)
    baseline["mappings"] = [r for r in archive["raw_results"] if r["candidate"]["rows"] == 4 and r["candidate"]["unroll_factor"] == 1]
    baseline["frame_estimate"] = next(a["scalar_compiler_baseline"] for a in archive["architectures"] if a["rows"] == 4)
    return {"run": run.name, "entries": entries, "baseline": baseline,
            "reference": {"evaluations": archive["evaluations"], "elapsed_seconds": archive["elapsed_seconds"],
                          "best_estimated_cycles": reference_best},
            "run_summary": ({"evaluations": result["evaluations"], "llm_calls": result["llm_calls"],
                             "elapsed_seconds": result["elapsed_seconds"]} if result else None),
            "native_validation": {"passed": sum(c["status"] == "passed" for c in native_validation["cases"]),
                                  "total": len(native_validation["cases"])},
            "implementation": implementation,
            "workload": workload.to_dict() if workload else Workload().to_dict(),
            "baseline_comparable": workload is None or (workload.samples, workload.chirps, workload.rx) == (256, 128, 4),
            "best_validated_feasible": None,
            "constraint_status": "pending: no candidate RTL correctness, synthesis area or clock measurement",
            "progress": p}


def validation_view(scene: str | None = None):
    report = read_json(VALIDATION / "validation.json")
    if scene is None:
        return report
    names = {c["scene"]: c for c in report["cases"]}
    if scene not in names:
        raise ValueError("Unknown validation scene")
    import numpy as np
    with np.load(VALIDATION / names[scene]["arrays"], allow_pickle=False) as data:
        maximum = max(float(data["golden_power"].max()), float(data["native_power"].max()), 1e-30)
        maps = {}
        for kind in ("golden", "native"):
            # Shared 0..-100 dB display; raw arrays remain in the NPZ evidence.
            db = 10 * np.log10(np.maximum(data[f"{kind}_power"] / maximum, 1e-10))
            maps[kind] = {"db": np.round(db, 2).tolist(), "detections": np.argwhere(data[f"{kind}_detections"] != 0).tolist()}
    return {"scene": scene, "report": names[scene], "maps": maps, "color_scale_db": [-100, 0],
            "scope": "native C vs NumPy; not selected CGRA hardware output"}
