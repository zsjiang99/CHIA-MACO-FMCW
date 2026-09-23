from chia_maco.report import (
    estimate_frame_cycles,
    frame_iteration_counts,
    frame_scheduled_groups,
)
from chia_maco.schema import CoDesignCandidate, KERNEL_LOOPS, MappingResult
from chia_maco.workload import Workload


def test_nominal_iteration_counts() -> None:
    counts = frame_iteration_counts()
    assert counts["fmcw_window"] == 4 * 128 * 256
    assert counts["fmcw_fft_stage"] == 983_040
    assert counts["fmcw_transpose"] == 2 * 4 * 128 * 256
    assert counts["fmcw_accumulate_power"] == 4 * 128 * 256
    assert counts["fmcw_cfar_2d"] == (256 - 10) * (128 - 10) * 121


def test_frame_estimate_uses_measured_iis() -> None:
    results = [
        MappingResult(
            candidate=CoDesignCandidate(kernel=kernel).to_dict(),
            success=True,
            mapping_ii=2,
            resource_mii=1,
            recurrence_mii=1,
            dfg_nodes=1,
            dfg_edges=1,
            fu_utilization_percent=1.0,
            xbar_utilization_percent=1.0,
            elapsed_seconds=0.1,
        )
        for kernel in KERNEL_LOOPS
    ]
    estimate = estimate_frame_cycles(results)
    assert estimate["valid"]
    assert estimate["estimated_cycles"] == 2 * sum(frame_iteration_counts().values())


def test_unroll_group_counts_respect_short_loop_invocations() -> None:
    groups = frame_scheduled_groups(8)
    assert groups["fmcw_accumulate_power"] == 256 * 128
    assert groups["fmcw_cfar_2d"] == (256 - 10) * (128 - 10) * 11 * 2


def test_workload_dimensions_change_frame_model() -> None:
    workload = Workload(description="smaller FMCW", samples=128, chirps=64, rx=2, max_pes=16)
    counts = frame_iteration_counts(workload)
    assert counts["fmcw_window"] == 2 * 64 * 128
    assert counts["fmcw_cfar_2d"] == (128 - 10) * (64 - 10) * 121
