"""CGRA-Flow's CACTI memory model, isolated per evaluation and with raw evidence."""
import json
import math
from pathlib import Path
import re
import subprocess
import tempfile

from .evidence import parse_schedule

IMAGE = "cgra/neura-flow:20260114"
CACTI = "/WORK_REPO/CGRA-Flow/tools/cacti"


def parse_cacti(output):
    patterns = {
        "read_nj": r"Total dynamic read energy(?:/access| per access)\s*\(nJ\):\s*([\d.eE+-]+)",
        "write_nj": r"Total dynamic write energy(?:/access| per access)\s*\(nJ\):\s*([\d.eE+-]+)",
        "area_mm2": r"Data array: Area\s*\(mm2\):\s*([\d.eE+-]+)",
        "access_ns": r"(?:Access time \(ns\)|Data side \(with Output driver\) \(ns\)):\s*([\d.eE+-]+)",
    }
    values = {}
    for key, pattern in patterns.items():
        match = re.search(pattern, output)
        if not match:
            raise ValueError(f"CACTI did not report {key}")
        values[key] = float(match[1])
        if not math.isfinite(values[key]) or values[key] <= 0:
            raise ValueError(f"Invalid CACTI {key}")
    return values


def evaluate_memory(banks, bank_kib, output: Path):
    output.mkdir(parents=True, exist_ok=False)
    template = subprocess.run(["docker", "run", "--rm", IMAGE, "cat", f"{CACTI}/spm_template.cfg"],
                              capture_output=True, text=True, check=True, timeout=30).stdout
    config = template.replace("[SPM_SIZE]", str(banks * bank_kib * 1024)).replace("[READ_PORT_COUNT]", "1").replace("[WRITE_PORT_COUNT]", "1")
    config = config.replace("-UCA bank count 1", f"-UCA bank count {banks}")
    (output / "cacti.cfg").write_text(config)
    # The image is immutable; configs and CACTI-generated CSVs stay in a temp mount.
    with tempfile.TemporaryDirectory(prefix="maco_cacti_") as temporary:
        Path(temporary, "cacti.cfg").write_text(config)
        result = subprocess.run(["docker", "run", "--rm", "-v", f"{temporary}:/work", "-w", CACTI,
                                 IMAGE, f"{CACTI}/cacti", "-infile", "/work/cacti.cfg"],
                                capture_output=True, text=True, timeout=90)
    raw = result.stdout + result.stderr
    (output / "cacti.log").write_text(raw)
    if result.returncode:
        raise ValueError(f"CACTI exited with status {result.returncode}")
    values = {**parse_cacti(raw), "banks": banks, "bank_kib": bank_kib, "technology_nm": 45,
              "source": "CGRA-Flow CACTI", "scope": "SRAM only; one read and one write port per bank",
              "evidence": str(output.name) + "/cacti.log"}
    (output / "memory.json").write_text(json.dumps(values, indent=2))
    return values


def frame_memory_energy(mapped, logs, estimate, memory):
    """Representative mapper DFG activity, not runtime memory transactions."""
    reads = writes = 0
    for result, log in zip(mapped, logs):
        schedule = parse_schedule(log.read_text(), result.to_dict())
        if not schedule["available"]:
            raise ValueError("Cannot estimate memory energy without complete mapper schedules")
        groups = estimate["breakdown"][result.candidate["kernel"]]["scheduled_loop_groups"]
        reads += groups * sum(bool(re.search(r"\bload\b", p["instruction"])) for p in schedule["placements"])
        writes += groups * sum(bool(re.search(r"\bstore\b", p["instruction"])) for p in schedule["placements"])
    return {**memory, "estimated_reads": reads, "estimated_writes": writes,
            "dynamic_energy_uj": (reads * memory["read_nj"] + writes * memory["write_nj"]) / 1000,
            "activity_source": "scheduled DFG load/store counts × steady-state loop groups",
            "excluded": ["PE energy", "interconnect energy", "leakage", "bank conflicts", "capacity spills", "host transfers"]}
