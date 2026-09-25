"""Evidence contracts and conservative extraction of successful mapper schedules."""
from __future__ import annotations

import hashlib
import json
import math
import re


def candidate_id(design):
    settings = {k: value for k, value in design.items() if k != "reasoning"}
    return "c-" + hashlib.sha256(json.dumps(settings, sort_keys=True).encode()).hexdigest()[:12]


def metric(value=None, unit="", source=None, status="pending", scope="full_frame", evidence=None):
    if status == "available" and (value is None or not source or not evidence):
        raise ValueError("available metrics require a value, source and evidence")
    if status != "available" and value is not None:
        raise ValueError("unverified metrics must not contain a value")
    return dict(value=value, unit=unit, source=source, status=status, scope=scope, evidence=evidence)


def mapper_metrics(cycles, evidence):
    return {
        "estimated_cycles": metric(cycles, "cycles/frame", "mapper_estimate", "available", evidence=evidence) if cycles is not None else metric(unit="cycles/frame"),
        "frame_time": metric(unit="s/frame"), "throughput": metric(unit="FPS"),
        "area": metric(unit="um2"), "energy": metric(unit="J/frame"),
        "hardware_correctness": metric(unit="boolean"),
    }


def hardware_feasible(metrics, reference_area):
    """Missing native/RTL/synthesis evidence cannot promote a candidate."""
    required = {"hardware_correctness": ("rtl_simulation", "boolean"), "area": ("synthesis", "um2"), "frame_time": ("rtl_cycles_and_timing", "s/frame")}
    for name, (source, unit) in required.items():
        m = metrics.get(name, {})
        if m.get("status") != "available" or m.get("source") != source or m.get("unit") != unit or m.get("scope") != "full_frame" or not m.get("evidence"):
            return False
    values = (reference_area, metrics["area"]["value"], metrics["frame_time"]["value"])
    if any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0 for v in values):
        return False
    return (metrics["hardware_correctness"]["value"] is True
            and 0 < metrics["area"]["value"] <= reference_area and metrics["frame_time"]["value"] > 0)


def parse_schedule(text, mapping):
    """Only the final successful heuristic attempt; never mix failed-II attempts."""
    unavailable = {"available": False, "placements": [], "links": [], "reason": "No complete successful schedule in retained log"}
    if not mapping["success"] or "[Mapping Success]" not in text:
        return unavailable
    attempts = list(re.finditer(r"\[DEBUG\] start heuristic algorithm with II=(\d+)", text))
    if not attempts:
        return unavailable
    final = attempts[-1]
    ii = int(final.group(1))
    part = text[final.end():].split("[Mapping Success]", 1)[0]
    placements = [dict(node=int(n), pe=int(pe), cycle=int(c), ii=int(i)) for n, pe, c, i in re.findall(
        r"schedule dfg node\[(\d+)\] onto fu\[(\d+)\] at cycle (\d+) within II: (\d+)", part)]
    count = mapping["candidate"]["rows"] * mapping["candidate"]["columns"]
    if (ii != mapping["mapping_ii"] or len(placements) != mapping["dfg_nodes"]
            or len({p["node"] for p in placements}) != len(placements)
            or any(p["pe"] >= count or p["ii"] != ii for p in placements)):
        return unavailable
    # LLVM IR printed after scheduling identifies operations without interpreting FU labels.
    instructions = {int(n): ir.strip() for ir, n in re.findall(r'\+\+\+ "(.*?)" \(ID: (\d+)\)', text)}
    for p in placements:
        p["instruction"] = instructions.get(p["node"], "not recorded")
    producers = {}
    for p in placements:
        match = re.match(r"\s*(%[-\w.]+)\s*=", p["instruction"])
        if match:
            producers[match.group(1)] = p["node"]
    dfg_edges = set()
    for p in placements:
        rhs = p["instruction"].split("=", 1)[-1]
        for value in re.findall(r"%[-\w.]+", rhs):
            source = producers.get(value)
            if source is not None and source != p["node"]:
                dfg_edges.add((source, p["node"]))
    links = sorted({(int(a), int(b), int(c)) for a, b, c in re.findall(
        r"occupy link\[(\d+)\]-->\[(\d+)\].*?at cycle (\d+)", part)})
    if any(a >= count or b >= count for a, b, _ in links):
        return unavailable
    return {"available": True, "ii": ii, "placements": placements,
            "dfg_edges": [{"source": a, "target": b} for a, b in sorted(dfg_edges)],
            "links": [{"source": a, "target": b, "cycle": cycle} for a, b, cycle in links],
            "memory_on_left": "enable load functionality on the left most column" in text,
            "source": "successful heuristic attempt in raw mapper log; not RTL execution",
            "routing_scope": "cycle-tagged occupied links from the successful heuristic attempt; not RTL execution"}
