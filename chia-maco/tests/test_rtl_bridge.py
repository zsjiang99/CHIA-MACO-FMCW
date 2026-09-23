import copy
import json
from pathlib import Path

import pytest

from chia_maco.evidence import parse_schedule
from chia_maco.rtl_bridge import export_bridge, restore_opcodes

ROOT = Path(__file__).resolve().parents[1] / "results/rtl_audit"


def evidence():
    config = json.loads((ROOT / "window/config.json").read_text())
    dfg = json.loads((ROOT / "window/dfg.json").read_text())
    schedule = parse_schedule((ROOT / "window.log").read_text(),
                              json.loads((ROOT / "window_result.json").read_text()))
    return config, dfg, schedule


def test_restore_preserves_integer_and_routing():
    config, dfg, schedule = evidence()
    restored, changes = restore_opcodes(config, dfg, schedule, 4)
    assert {c["node"] for c in changes} == {5, 11}
    assert all(c["restored"] == "OPT_FMUL" for c in changes)
    assert any(e["opt"] == "OPT_ADD_CONST" for e in restored)
    for old, new in zip(config, restored):
        assert {k: v for k, v in old.items() if k != "opt"} == {k: v for k, v in new.items() if k != "opt"}


def test_reject_bad_evidence():
    config, dfg, schedule = evidence()
    with pytest.raises(ValueError):
        restore_opcodes(config, dfg, {"available": False}, 4)
    wrong = copy.deepcopy(config)
    next(e for e in wrong if e["opt"] == "OPT_MUL")["opt"] = "OPT_ADD"
    with pytest.raises(ValueError, match="mismatch"):
        restore_opcodes(wrong, dfg, schedule, 4)
    wrong = copy.deepcopy(schedule)
    next(p for p in wrong["placements"] if p["node"] == 5)["instruction"] = "%x = fmul double %a, %b"
    with pytest.raises(ValueError, match="Unsupported"):
        restore_opcodes(config, dfg, wrong, 4)


def test_export_is_not_hardware_certificate(tmp_path):
    args = (ROOT / "window", ROOT / "window.log", ROOT / "window_result.json", tmp_path / "bridge")
    report = export_bridge(*args)
    assert report["candidate_hardware_correctness"] == "pending"
    assert len(report["source_sha256"]) == 5
    with pytest.raises(FileExistsError):
        export_bridge(*args)


def test_square_is_not_constant_multiply():
    config, dfg, schedule = evidence()
    p = next(p for p in schedule["placements"] if p["node"] == 5)
    p["instruction"] = "%13 = fmul float %10, %10"
    next(n for n in dfg if n["id"] == 5)["JSON_opt"] = "OPT_MUL_CONST"
    for entry in config:
        if (entry["x"], entry["y"], entry["cycle"] % 4) == (1, 2, p["cycle"] % 4):
            entry["opt"] = "OPT_MUL_CONST"
    _, changes = restore_opcodes(config, dfg, schedule, 4)
    square = next(c for c in changes if c["node"] == 5)
    assert square["restored"] == "OPT_FMUL" and square["duplicate_operand"]


def test_unsigned_guard_is_not_equality():
    config, dfg, schedule = evidence()
    next(p for p in schedule["placements"] if p["node"] == 15)["instruction"] = "%21 = icmp ult i32 %20, 3"
    _, changes = restore_opcodes(config, dfg, schedule, 4)
    guard = next(c for c in changes if c["node"] == 15)
    assert guard["restored"] == "OPT_LT" and guard["constant_to_register_required"]
