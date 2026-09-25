import json
from pathlib import Path

import numpy as np
import pytest

from chia_maco.validation import NativePipeline, cfar, compare, golden, scene
from chia_maco.evidence import candidate_id, hardware_feasible, mapper_metrics, metric, parse_schedule

ROOT = Path(__file__).resolve().parents[1]
SPEC = json.loads((ROOT / "configs/validation.json").read_text())


def test_cfar_guard_and_border():
    power = np.ones((16, 16))
    power[8, 8] = 100
    detections, thresholds = cfar(power)
    assert thresholds[8, 8] == 6
    assert detections.sum() == 1 and detections[8, 8]
    assert not detections[:5].any()


@pytest.mark.parametrize("name", ["zero", "noisy_targets"])
def test_full_native_matches_independent_oracle(tmp_path, name):
    data = scene(name, (4, 128, 256), 37)
    result = compare(golden(data, SPEC), NativePipeline(tmp_path).run(data), SPEC)
    assert result["status"] == "passed"


def test_wrong_outputs_cannot_pass():
    data = scene("single_target", (4, 128, 256), 37)
    ref = golden(data, SPEC)
    wrong = {k: v.copy() for k, v in ref.items()}
    wrong["power"] *= 2
    wrong["detections"][0, 0] = 1
    assert compare(ref, wrong, SPEC)["status"] == "failed"
    wrong["power"][0, 0] = np.nan
    assert compare(ref, wrong, SPEC)["status"] == "failed"


def test_noiseless_cfar_discrepancy_is_not_hidden(tmp_path):
    data = scene("single_target", (4, 128, 256), 37)
    result = compare(golden(data, SPEC), NativePipeline(tmp_path).run(data), SPEC)
    assert all(s["passed"] for s in result["stages"].values())
    assert result["detection_mismatches"] > 0 and result["status"] == "failed"


def test_metric_provenance_and_ids():
    with pytest.raises(ValueError):
        metric(0, status="pending")
    with pytest.raises(ValueError):
        metric(20, status="available", source="guess")
    assert not hardware_feasible(mapper_metrics(39154344, "archive"), None)
    measured = {"hardware_correctness": metric(True, "boolean", "rtl_simulation", "available", evidence="rtl/report"),
                "area": metric(10, "um2", "synthesis", "available", evidence="synth/report"),
                "frame_time": metric(.01, "s/frame", "rtl_cycles_and_timing", "available", evidence="timing/report")}
    assert hardware_feasible(measured, 12)
    assert not hardware_feasible(measured, 8)
    measured["hardware_correctness"]["source"] = "native_c"
    assert not hardware_feasible(measured, 12)
    a = {"tile_size": "4x4", "unroll_factors": [1]*5, "reasoning": "one"}
    assert candidate_id(a) == candidate_id({**a, "reasoning": "two"})


def test_all_recorded_schedules_are_complete():
    path = ROOT / "results/agent_qwen38_27b_seed37_v3"
    result = json.loads((path / "result.json").read_text())
    for i, mapping in enumerate(result["raw_results"]):
        text = (path / f"mapper_logs/mapping_{i:03d}.log").read_text()
        schedule = parse_schedule(text, mapping)
        assert schedule["available"]
        assert len(schedule["placements"]) == mapping["dfg_nodes"]
        assert not parse_schedule(text.replace("[Mapping Success]", "[Mapping Failed]"), mapping)["available"]
