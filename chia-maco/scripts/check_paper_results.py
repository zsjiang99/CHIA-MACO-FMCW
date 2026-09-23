"""Check reported paper numbers against the archived results."""

from __future__ import annotations

import json
from pathlib import Path


RESULTS = Path(__file__).resolve().parents[1] / "results"


def read(path: str) -> dict:
    return json.loads((RESULTS / path).read_text(encoding="utf-8"))


reference = read("codesign_search_certified.json")
agent = read("agent_qwen38_27b_seed37_v3/result.json")
validation = read("validation_v1/validation.json")

feasible = [item for item in reference["architectures"] if item["all_kernels_feasible"]]
reference_winner = min(
    feasible,
    key=lambda item: item["frame_estimate"]["estimated_cycles"],
)
reference_best = reference_winner["frame_estimate"]["estimated_cycles"]
agent_plan = agent["best_evaluated_plan"]
agent_frame = agent_plan["frame_estimate"]
cfar_share = 100 * (
    agent_frame["breakdown"]["fmcw_cfar_2d"]["estimated_cycles"]
    / agent_frame["estimated_cycles"]
)
passed_scenes = sum(case["status"] == "passed" for case in validation["cases"])

checks = {
    "reference mappings": (reference["successful_mappings"], 36),
    "reference raw records": (len(reference["raw_results"]), 36),
    "reference best cycles": (reference_best, 39_154_344),
    "reference best array": (
        f"{reference_winner['rows']}x{reference_winner['columns']}",
        "4x4",
    ),
    "reference wall time (s)": (round(reference["elapsed_seconds"], 2), 38.71),
    "agent mappings": (agent["successful_mappings"], 18),
    "agent evaluations": (agent["evaluations"], 18),
    "agent model calls": (agent["llm_calls"], 12),
    "agent best cycles": (agent_frame["estimated_cycles"], 39_154_344),
    "agent best array": (agent_plan["design"]["tile_size"], "4x4"),
    "agent wall time (s)": (round(agent["elapsed_seconds"], 2), 210.43),
    "CFAR share (%)": (round(cfar_share, 1), 89.7),
    "strict CFAR scenes": (f"{passed_scenes}/{len(validation['cases'])}", "2/6"),
}
for label, (actual, expected) in checks.items():
    if actual != expected:
        raise SystemExit(f"{label}: expected {expected}, found {actual}")

print("Archived paper results: PASS (no mapper or model run)")
print(f"Reference: 36 mappings, {reference_best:,} estimated cycles/frame")
print(f"MACO: 18 mappings, 12 model calls, {agent_frame['estimated_cycles']:,} estimated cycles/frame")
print(f"CFAR: {cfar_share:.1f}% of modeled cycles; strict native masks: {passed_scenes}/6 scenes")
