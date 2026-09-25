"""Frame-level CGRA dynamic-energy estimate from measured mapper activity."""
from __future__ import annotations

import re

from .evidence import parse_schedule

COEFFICIENTS_PJ = {
    "int_alu": 0.10, "int_mul": 3.10, "fp_add": 0.90, "fp_mul": 3.70,
    "div": 20.0, "register_transfer": 1.0, "route_hop": 0.20,
    "active_tile_cycle": 0.05,
}


def _operation(instruction: str) -> str:
    text = instruction.lower()
    if re.search(r"\bfdiv\b|\bsdiv\b|\budiv\b", text): return "div"
    if re.search(r"\bfmul\b", text): return "fp_mul"
    if re.search(r"\bfadd\b|\bfsub\b", text): return "fp_add"
    if re.search(r"\bmul\b", text): return "int_mul"
    return "int_alu"


def frame_dynamic_energy(mapped, logs, estimate, memory):
    """Estimate compute, communication, control and SRAM energy for one frame."""
    operation_counts = {name: 0 for name in ("int_alu", "int_mul", "fp_add", "fp_mul", "div")}
    register_transfers = route_hops = 0
    per_kernel = {}
    for result, log in zip(mapped, logs):
        schedule = parse_schedule(log.read_text(), result.to_dict())
        if not schedule["available"]:
            raise ValueError("Cannot estimate CGRA energy without complete mapper schedules")
        kernel = result.candidate["kernel"]
        groups = estimate["breakdown"][kernel]["scheduled_loop_groups"]
        local = {name: 0 for name in operation_counts}
        for placement in schedule["placements"]:
            local[_operation(placement["instruction"])] += groups
        for name, count in local.items(): operation_counts[name] += count
        edges = len(schedule.get("dfg_edges", [])) * groups
        hops = len(schedule.get("links", [])) * groups
        register_transfers += edges
        route_hops += hops
        per_kernel[kernel] = {"operations": sum(local.values()), "register_transfers": edges, "route_hops": hops}
    compute_pj = sum(operation_counts[name] * COEFFICIENTS_PJ[name] for name in operation_counts)
    register_pj = register_transfers * COEFFICIENTS_PJ["register_transfer"]
    route_pj = route_hops * COEFFICIENTS_PJ["route_hop"]
    rows, columns = mapped[0].candidate["rows"], mapped[0].candidate["columns"]
    control_pj = estimate["estimated_cycles"] * rows * columns * COEFFICIENTS_PJ["active_tile_cycle"]
    core_uj = (compute_pj + register_pj + route_pj + control_pj) / 1_000_000
    sram_uj = memory["dynamic_energy_uj"]
    return {
        "total_dynamic_energy_uj": core_uj + sram_uj,
        "core_dynamic_energy_uj": core_uj,
        "sram_dynamic_energy_uj": sram_uj,
        "components_uj": {"compute": compute_pj / 1_000_000,
                          "register_and_control": (register_pj + control_pj) / 1_000_000,
                          "interconnect": route_pj / 1_000_000, "sram": sram_uj},
        "activity": {"operations": operation_counts, "register_transfers": register_transfers,
                     "route_hops": route_hops, "per_kernel": per_kernel},
        "coefficients_pj": COEFFICIENTS_PJ,
        "source": "measured mapper schedules + 45 nm operation/activity model + CGRA-Flow CACTI",
        "scope": "CGRA and SRAM dynamic energy per frame; excludes leakage and host transfers",
        "reference": "M. Horowitz, ISSCC 2014, Computing's Energy Problem",
    }
