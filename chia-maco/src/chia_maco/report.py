"""Frame-level aggregation for measured per-kernel mapping results."""

from __future__ import annotations

import math
from typing import Iterable

from .schema import MappingResult
from .workload import Workload


RANGE_BINS = 256
DOPPLER_BINS = 128
RX_CHANNELS = 4
CFAR_OUTER_RADIUS = 5


def frame_iteration_counts(workload: Workload | None = None) -> dict[str, int]:
    """Return dynamic loop iterations for one nominal FMCW frame."""

    workload = workload or Workload()
    workload.validate()
    RANGE_BINS, DOPPLER_BINS, RX_CHANNELS = workload.samples, workload.chirps, workload.rx
    range_butterflies = (
        RX_CHANNELS
        * DOPPLER_BINS
        * (RANGE_BINS // 2)
        * (RANGE_BINS.bit_length() - 1)
    )
    doppler_butterflies = (
        RX_CHANNELS
        * RANGE_BINS
        * (DOPPLER_BINS // 2)
        * (DOPPLER_BINS.bit_length() - 1)
    )
    interior_cells = (
        (RANGE_BINS - 2 * CFAR_OUTER_RADIUS)
        * (DOPPLER_BINS - 2 * CFAR_OUTER_RADIUS)
    )
    cfar_neighbor_iterations = interior_cells * (2 * CFAR_OUTER_RADIUS + 1) ** 2

    return {
        "fmcw_window": RX_CHANNELS * DOPPLER_BINS * RANGE_BINS,
        "fmcw_fft_stage": range_butterflies + doppler_butterflies,
        "fmcw_transpose": 2 * RX_CHANNELS * RANGE_BINS * DOPPLER_BINS,
        "fmcw_accumulate_power": RX_CHANNELS * RANGE_BINS * DOPPLER_BINS,
        "fmcw_cfar_2d": cfar_neighbor_iterations,
    }


def frame_scheduled_groups(unroll_factor: int, workload: Workload | None = None) -> dict[str, int]:
    """Return mapper-loop groups after a compiler unroll transformation.

    Counts are computed per invocation so short loops such as four-channel
    power accumulation are not incorrectly treated as one global flat loop.
    """

    if unroll_factor < 1:
        raise ValueError("unroll_factor must be positive")
    workload = workload or Workload()
    workload.validate()
    RANGE_BINS, DOPPLER_BINS, RX_CHANNELS = workload.samples, workload.chirps, workload.rx

    def fft_groups(length: int, calls: int) -> int:
        groups = 0
        butterfly_size = 2
        while butterfly_size <= length:
            outer_groups = length // butterfly_size
            inner_iterations = butterfly_size // 2
            groups += outer_groups * math.ceil(inner_iterations / unroll_factor)
            butterfly_size *= 2
        return calls * groups

    interior_cells = (
        (RANGE_BINS - 2 * CFAR_OUTER_RADIUS)
        * (DOPPLER_BINS - 2 * CFAR_OUTER_RADIUS)
    )
    cfar_width = 2 * CFAR_OUTER_RADIUS + 1
    return {
        "fmcw_window": (
            RX_CHANNELS
            * DOPPLER_BINS
            * math.ceil(RANGE_BINS / unroll_factor)
        ),
        "fmcw_fft_stage": (
            fft_groups(RANGE_BINS, RX_CHANNELS * DOPPLER_BINS)
            + fft_groups(DOPPLER_BINS, RX_CHANNELS * RANGE_BINS)
        ),
        "fmcw_transpose": (
            2
            * RX_CHANNELS
            * DOPPLER_BINS
            * math.ceil(RANGE_BINS / unroll_factor)
        ),
        "fmcw_accumulate_power": (
            RANGE_BINS
            * DOPPLER_BINS
            * math.ceil(RX_CHANNELS / unroll_factor)
        ),
        "fmcw_cfar_2d": (
            interior_cells
            * cfar_width
            * math.ceil(cfar_width / unroll_factor)
        ),
    }


def estimate_frame_cycles(results: Iterable[MappingResult], workload: Workload | None = None) -> dict:
    """Combine measured mapping IIs with nominal dynamic iteration counts.

    This is a steady-state analytical estimate. It intentionally excludes loop
    setup, memory-system stalls, bit reversal, and host/CGRA transfer costs.
    """

    by_kernel = {result.candidate["kernel"]: result for result in results}
    counts = frame_iteration_counts(workload)
    missing = sorted(set(counts) - set(by_kernel))
    failed = sorted(
        kernel
        for kernel, result in by_kernel.items()
        if not result.success or result.mapping_ii is None
    )
    if missing or failed:
        return {
            "valid": False,
            "missing_kernels": missing,
            "failed_kernels": failed,
            "estimated_cycles": None,
        }

    breakdown = {}
    for kernel, iterations in counts.items():
        result = by_kernel[kernel]
        unroll = result.candidate["unroll_factor"]
        scheduled_groups = frame_scheduled_groups(unroll, workload)[kernel]
        breakdown[kernel] = {
            "dynamic_iterations": iterations,
            "compiler_unroll_factor": unroll,
            "scheduled_loop_groups": scheduled_groups,
            "measured_mapping_ii": result.mapping_ii,
            "estimated_cycles": scheduled_groups * result.mapping_ii,
        }
    return {
        "valid": True,
        "model": "steady_state_scheduled_groups_x_mapping_ii",
        "excluded_costs": [
            "loop_setup",
            "memory_stalls",
            "fft_bit_reversal",
            "host_cgra_transfers",
        ],
        "breakdown": breakdown,
        "estimated_cycles": sum(
            item["estimated_cycles"] for item in breakdown.values()
        ),
    }
