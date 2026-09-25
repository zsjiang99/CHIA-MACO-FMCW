"""Run selected MACO architectures through the pinned CGRA-Flow image."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import uuid

IMAGE = "cgra/neura-flow:20260114"

FU_NAMES = {
    "Add": "add", "Mul": "mul", "Div": "div", "FAdd": "fadd",
    "FMul": "fmul", "FDiv": "fdiv", "Logic": "logic", "Cmp": "cmp",
    "Sel": "sel", "Ld": "mem", "St": "mem", "Phi": "phi",
    "Ret": "return", "Shift": "shift", "Br": "loop_control",
}


def architecture_yaml(payload: dict) -> dict:
    design, architecture = payload.get("design"), payload.get("architecture")
    if not isinstance(design, dict) or not isinstance(architecture, dict):
        raise ValueError("A selected MACO design and architecture are required")
    try:
        rows, columns = map(int, str(design["tile_size"]).lower().split("x"))
        memory = architecture["memory"]
        banks, bank_kib = int(memory["banks"]), int(memory["bank_kib"])
        tiles = architecture["tiles"]
        control_memory = int(architecture.get("control_memory", 32))
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("Invalid selected architecture") from error
    if (rows != columns or not 2 <= rows <= 8 or not 1 <= banks <= 16
            or not 1 <= bank_kib <= 256 or not 16 <= control_memory <= 1024):
        raise ValueError("Architecture is outside the evaluated MACO bounds")
    if not isinstance(tiles, dict) or set(tiles) != {str(i) for i in range(rows * columns)}:
        raise ValueError("Architecture tile set is incomplete")
    overrides = []
    for tile_id in range(rows * columns):
        raw = tiles[str(tile_id)]
        names = sorted({FU_NAMES[name] for name in raw.get("supportedFUs", []) if name in FU_NAMES})
        if raw.get("accessMem"):
            names.append("mem")
        if not names:
            raise ValueError(f"Tile {tile_id} has no supported functional unit")
        overrides.append({"cgra_x": 0, "cgra_y": 0, "tile_x": tile_id % columns,
                          "tile_y": tile_id // columns, "fu_types": sorted(set(names)),
                          "existence": not bool(raw.get("disabled", False))})
    all_fus = sorted(set(FU_NAMES.values()))
    # CGRA-Flow connects the SPM to the west and south boundaries by default.
    # MACO's mapper model uses west-edge interfaces only, so disable the extra
    # south links instead of silently adding memory FUs to the candidate.
    link_overrides = []
    for column in range(1, columns):
        port = rows - 1 + column
        link_overrides.extend((
            {"src_cgra_x": 0, "src_cgra_y": 0, "dst_cgra_x": 0, "dst_cgra_y": 0,
             "src_tile_x": -1, "src_tile_y": -1, "dst_tile_x": column,
             "dst_tile_y": port, "existence": False},
            {"src_cgra_x": 0, "src_cgra_y": 0, "dst_cgra_x": 0, "dst_cgra_y": 0,
             "src_tile_x": column, "src_tile_y": port, "dst_tile_x": -1,
             "dst_tile_y": -1, "existence": False},
        ))
    return {
        "architecture": {"name": "MACOSelectedCgra", "version": "1.0"},
        "multi_cgra_defaults": {"base_topology": "mesh", "rows": 1, "columns": 1,
            "memory": {"capacity": banks * bank_kib, "data bitwidth": 32, "vector lanes": 1}},
        "cgra_defaults": {"rows": rows, "columns": columns, "configMemSize": control_memory,
                          "per bank sram": bank_kib},
        "tile_defaults": {"num_registers": 16, "fu_types": all_fus},
        "tile_overrides": overrides,
        "link_overrides": link_overrides,
        "maco_memory": {"banks": banks, "bank_kib": bank_kib},
    }


def run(action: str, payload: dict, output: Path) -> None:
    if action not in ("verify", "synth", "layout"):
        raise ValueError("Unknown CGRA-Flow action")
    arch = architecture_yaml(payload)
    (output / "arch.yaml").write_text(json.dumps(arch, indent=2) + "\n")
    memory = None
    if action == "synth":
        from .memory import evaluate_memory
        memory = evaluate_memory(arch["maco_memory"]["banks"], arch["maco_memory"]["bank_kib"],
                                 output / "cacti")
    container = f"chia-raco-cgra-{uuid.uuid4().hex[:12]}"
    patch = Path(__file__).resolve().parents[2] / "patches/VectorCGRA/noc/CrossbarRTL.py"
    command = ["docker", "run", "--rm", "--name", container, "--network", "none",
               "-v", f"{output.resolve()}:/job",
               "-v", f"{Path(__file__).resolve().parents[2]}:/artifact:ro",
               "-v", f"{patch}:/WORK_REPO/CGRA-Flow/VectorCGRA/noc/CrossbarRTL.py:ro",
               "--entrypoint", "bash", IMAGE, "-lc",
               f"source /WORK_REPO/venv/bin/activate && "
               f"PYTHONPATH=/WORK_REPO/CGRA-Flow python /artifact/scripts/cgra_flow_runner.py {action} /job"]
    try:
        with (output / "cgra-flow.log").open("w") as log:
            completed = subprocess.run(command, text=True, stdout=log,
                                       stderr=subprocess.STDOUT, timeout={"verify": 1800, "synth": 3600,
                                                                         "layout": 43200}[action])
    except subprocess.TimeoutExpired:
        subprocess.run(["docker", "rm", "-f", container], capture_output=True, text=True)
        raise
    if completed.returncode:
        raise RuntimeError(f"CGRA-Flow {action} exited with status {completed.returncode}")
    if memory is not None:
        memory["power_mw"] = memory["read_nj"] / memory["access_ns"] * 1000
        result_path = output / "result.json"
        result = json.loads(result_path.read_text())
        result["memory"] = memory
        temporary = output / "result.updated.json"
        temporary.write_text(json.dumps(result, indent=2) + "\n")
        temporary.replace(result_path)
