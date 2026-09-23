"""Recover scalar opcodes from LLVM evidence; this is not a configuration loader."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from .evidence import parse_schedule


def restore_opcodes(config, dfg, schedule, columns):
    if not schedule.get("available"):
        raise ValueError("A complete successful mapper schedule is required")
    nodes = {n["id"]: n for n in dfg}
    if len(nodes) != len(dfg) or set(nodes) != {p["node"] for p in schedule["placements"]}:
        raise ValueError("DFG and schedule node identities differ")
    slots, changes = {}, []
    for p in schedule["placements"]:
        node = nodes[p["node"]]
        key = (p["pe"] % columns, p["pe"] // columns, p["cycle"] % schedule["ii"])
        if key in slots:
            raise ValueError(f"Ambiguous scheduled operation at {key}")
        opcode = node["JSON_opt"]
        ir = p["instruction"]
        if ir == "not recorded":
            raise ValueError(f"Missing LLVM instruction for node {p['node']}")
        match = re.search(r"=\s*(fadd|fsub|fmul)\s+float\s+([^,]+),\s*([^,]+)", ir)
        if match:
            op, left, right = (v.strip() for v in match.groups())
            old = "OPT_" + op[1:].upper()
            if opcode not in (old, old + "_CONST"):
                raise ValueError(f"DFG/LLVM opcode mismatch for node {p['node']}")
            constant = not left.startswith("%") or not right.startswith("%")
            opcode = "OPT_" + op.upper() + ("_CONST" if constant else "")
            if opcode == "OPT_FSUB_CONST":
                raise ValueError("FSUB_CONST requires operand-order lowering; not supported")
            changes.append(dict(node=p["node"], pe=p["pe"], slot=key[2],
                                original=node["JSON_opt"], restored=opcode, instruction=ir,
                                operands=[left, right], duplicate_operand=left == right))
        elif re.search(r"=\s*f(?:add|sub|mul|div|rem|cmp|neg)\b", ir):
            raise ValueError(f"Unsupported floating instruction: {ir}")
        compare = re.search(r"=\s*icmp\s+(\w+)\s+i(\d+)\s+([^,]+),\s*([^,]+)", ir)
        if compare:
            predicate, width, left, right = (v.strip() for v in compare.groups())
            if predicate not in ("eq", "ne", "ult"):
                raise ValueError(f"Unsupported integer comparison: {ir}")
            # CompRTL has unsigned LT but no LT_CONST: loader must supply operand 2.
            opcode = "OPT_LT" if predicate == "ult" else "OPT_" + predicate.upper()
            if predicate != "ult" and (not left.startswith("%") or not right.startswith("%")):
                opcode += "_CONST"
            if opcode != node["JSON_opt"]:
                changes.append(dict(node=p["node"], pe=p["pe"], slot=key[2],
                                    original=node["JSON_opt"], restored=opcode, instruction=ir,
                                    operands=[left, right], operand_width=int(width),
                                    constant_to_register_required=predicate == "ult" and not right.startswith("%")))
        slots[key] = (node, opcode)

    restored, seen = [], set()
    for entry in config:
        result = dict(entry)
        key = (entry["x"], entry["y"], entry["cycle"] % schedule["ii"])
        if entry["opt"] != "OPT_NAH":
            if key not in slots or slots[key][0]["JSON_opt"] != entry["opt"]:
                raise ValueError(f"Configuration/schedule mismatch at {key}")
            node, result["opt"] = slots[key]
            seen.add(node["id"])
        restored.append(result)
    if seen != set(nodes):
        raise ValueError("Configuration does not cover every scheduled DFG node")
    return restored, changes


def export_bridge(artifacts: Path, log: Path, mapping: Path, output: Path):
    files = {name: artifacts / name for name in ("config.json", "dfg.json", "kernel_map.bc")}
    files.update(log=log, mapping=mapping)
    result = json.loads(mapping.read_text())
    schedule = parse_schedule(log.read_text(), result)
    config, changes = restore_opcodes(
        json.loads(files["config.json"].read_text()), json.loads(files["dfg.json"].read_text()),
        schedule, result["candidate"]["columns"])
    report = dict(schema_version=2, scope="opcode restoration only; not executable or hardware-validated",
                  status="opcodes_restored", candidate=result["candidate"], changes=changes,
                  adapter_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  source_sha256={name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in files.items()},
                  pending=["operand/register and routing translation, including duplicate operands",
                           "constants (including LT operand 2) and memory addresses", "integer width/address lowering",
                           "configuration/data loader", "whole-kernel RTL execution"],
                  candidate_hardware_correctness="pending")
    output.mkdir(parents=True, exist_ok=False)
    (output / "adapter.py").write_bytes(Path(__file__).read_bytes())
    for name, value in (("config.json", config), ("report.json", report)):
        (output / name).write_text(json.dumps(value, indent=2) + "\n")
    return report
