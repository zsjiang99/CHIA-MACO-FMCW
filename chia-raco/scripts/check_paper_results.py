"""Check the current manuscript's budget-matched mapping records."""

from __future__ import annotations

import json
from pathlib import Path


RESULTS = Path(__file__).resolve().parents[1] / "results" / "matched_budget_10"
EXPECTED = {
    "full_maco": ("full_maco", 10, 38_728_360),
    "hardware_only": ("hardware_only", 10, 42_136_232),
    "single_agent": ("single_agent", 9, 41_448_104),
}


def check(label: str, actual: object, expected: object) -> None:
    if actual != expected:
        raise SystemExit(f"{label}: expected {expected!r}, found {actual!r}")


for folder, (method, successful, best_cycles) in EXPECTED.items():
    root = RESULTS / folder
    result = json.loads((root / "result.json").read_text(encoding="utf-8"))
    trace = json.loads((root / "agent_trace.json").read_text(encoding="utf-8"))
    request = json.loads((root / "request.json").read_text(encoding="utf-8"))
    raw = result["raw_results"]
    unique = {json.dumps(item["candidate"], sort_keys=True) for item in raw}
    measured = result["best_evaluated_plan"]["frame_estimate"]

    check(f"{folder} method", result["method"], method)
    check(f"{folder} budget", result["config"]["mapping_budget"], 10)
    check(f"{folder} seed", result["config"]["seed"], 37)
    check(f"{folder} rounds", len(result["rounds"]), 1)
    check(f"{folder} evaluations", result["evaluations"], 10)
    check(f"{folder} raw mappings", len(raw), 10)
    check(f"{folder} unique mappings", len(unique), 10)
    check(f"{folder} successful mappings", result["successful_mappings"], successful)
    check(f"{folder} best estimate", measured["estimated_cycles"], best_cycles)
    check(
        f"{folder} breakdown sum",
        sum(item["estimated_cycles"] for item in measured["breakdown"].values()),
        best_cycles,
    )
    check(f"{folder} mapper logs", len(list((root / "mapper_logs").glob("mapping_*.log"))), 10)
    check(f"{folder} trace method", trace["method"], method)
    check(f"{folder} request present", bool(request), True)

full = json.loads((RESULTS / "full_maco" / "result.json").read_text(encoding="utf-8"))
check("RACO candidate costs", [item["frame_estimate"]["estimated_cycles"] for item in full["history"]],
      [38_728_360, 40_202_920])

second = json.loads((RESULTS / "two_round_trace" / "result.json").read_text(encoding="utf-8"))
check("separate trace rounds", len(second["rounds"]), 2)
check("separate trace evaluations", second["evaluations"], 20)
check("separate trace successful mappings", second["successful_mappings"], 17)
check("separate trace incumbent", second["best_evaluated_plan"]["frame_estimate"]["estimated_cycles"], 38_728_360)

print("RACO matched-budget records: PASS (no mapper or model run)")
for folder, (_, successful, best_cycles) in EXPECTED.items():
    print(f"{folder}: {successful}/10 mappings, {best_cycles:,} estimated cycles/frame")
print("Separate two-round trace: 17/20 mappings; incumbent 38,728,360 cycles/frame")
