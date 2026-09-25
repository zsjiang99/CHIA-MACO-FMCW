"""Bounded compiler/architecture search orchestrated with CHIA."""

from __future__ import annotations

import time
from collections import defaultdict

from .mapper import MapperEvaluator
from .report import estimate_frame_cycles, frame_scheduled_groups
from .schema import CoDesignCandidate, KERNEL_LOOPS, MappingResult


ARCHITECTURES = ((2, 2), (4, 4), (6, 6))
KERNEL_UNROLL_FACTORS = {
    "fmcw_window": (1, 2, 4),
    "fmcw_fft_stage": (1, 2),
    "fmcw_transpose": (1, 2, 4),
    "fmcw_accumulate_power": (1, 2, 4),
    "fmcw_cfar_2d": (1,),
}


def search_candidates() -> list[CoDesignCandidate]:
    return [
        CoDesignCandidate(
            kernel=kernel,
            rows=rows,
            columns=columns,
            unroll_factor=unroll,
        )
        for rows, columns in ARCHITECTURES
        for kernel in KERNEL_LOOPS
        for unroll in KERNEL_UNROLL_FACTORS[kernel]
    ]


def _choose_compiler_configs(results: list[MappingResult]) -> list[dict]:
    grouped: dict[tuple[int, int, str], list[MappingResult]] = defaultdict(list)
    for result in results:
        candidate = result.candidate
        grouped[
            (candidate["rows"], candidate["columns"], candidate["kernel"])
        ].append(result)

    architectures = []
    for rows, columns in ARCHITECTURES:
        selected: list[MappingResult] = []
        baselines: list[MappingResult] = []
        for kernel in KERNEL_LOOPS:
            feasible = [
                result
                for result in grouped[(rows, columns, kernel)]
                if result.success and result.mapping_ii is not None
            ]
            if feasible:
                baseline = next(
                    (
                        result
                        for result in feasible
                        if result.candidate["unroll_factor"] == 1
                    ),
                    None,
                )
                if baseline is not None:
                    baselines.append(baseline)
                selected.append(
                    min(
                        feasible,
                        key=lambda result: (
                            frame_scheduled_groups(
                                result.candidate["unroll_factor"]
                            )[kernel] * result.mapping_ii,
                            result.candidate["unroll_factor"],
                        ),
                    )
                )
        estimate = estimate_frame_cycles(selected)
        baseline_estimate = estimate_frame_cycles(baselines)
        baseline_cycles = baseline_estimate.get("estimated_cycles")
        optimized_cycles = estimate.get("estimated_cycles")
        improvement = (
            100.0 * (baseline_cycles - optimized_cycles) / baseline_cycles
            if baseline_cycles and optimized_cycles is not None else None
        )
        architectures.append(
            {
                "rows": rows,
                "columns": columns,
                "tiles": rows * columns,
                "all_kernels_feasible": estimate["valid"],
                "selected_compiler_configs": [
                    result.to_dict() for result in selected
                ],
                "scalar_compiler_baseline": baseline_estimate,
                "frame_estimate": estimate,
                "compiler_speedup_percent": improvement,
            }
        )
    return architectures


def _annotate_pareto(architectures: list[dict]) -> None:
    feasible = [
        architecture
        for architecture in architectures
        if architecture["all_kernels_feasible"]
    ]
    for candidate in architectures:
        if candidate not in feasible:
            candidate["pareto_optimal"] = False
            continue
        cycles = candidate["frame_estimate"]["estimated_cycles"]
        tiles = candidate["tiles"]
        candidate["pareto_optimal"] = not any(
            other is not candidate
            and other["tiles"] <= tiles
            and other["frame_estimate"]["estimated_cycles"] <= cycles
            and (
                other["tiles"] < tiles
                or other["frame_estimate"]["estimated_cycles"] < cycles
            )
            for other in feasible
        )


def summarize_search(
    results: list[MappingResult], execution: str, elapsed_seconds: float
) -> dict:
    architectures = _choose_compiler_configs(results)
    _annotate_pareto(architectures)
    feasible = [item for item in architectures if item["all_kernels_feasible"]]
    recommended = min(
        feasible,
        key=lambda item: item["tiles"]
        * item["frame_estimate"]["estimated_cycles"],
    ) if feasible else None
    return {
        "execution": execution,
        "evaluations": len(results),
        "successful_mappings": sum(result.success for result in results),
        "elapsed_seconds": elapsed_seconds,
        "search_space": {
            "architectures": [list(item) for item in ARCHITECTURES],
            "unroll_factors_by_kernel": {
                kernel: list(factors)
                for kernel, factors in KERNEL_UNROLL_FACTORS.items()
            },
            "kernels": list(KERNEL_LOOPS),
        },
        "architectures": architectures,
        "recommended_by_cycle_tile_product": (
            {"rows": recommended["rows"], "columns": recommended["columns"]}
            if recommended else None
        ),
        "raw_results": [result.to_dict() for result in results],
    }


def run_search(use_chia: bool = True) -> dict:
    started = time.monotonic()
    candidates = search_candidates()
    if not use_chia:
        evaluator = MapperEvaluator()
        results = [evaluator.evaluate(candidate) for candidate in candidates]
        return summarize_search(
            results, "local", time.monotonic() - started
        )

    import ray
    from chia.base.ChiaFunction import get
    from .nodes import evaluate_candidate

    started_ray = not ray.is_initialized()
    if started_ray:
        ray.init(
            include_dashboard=False,
            resources={"cgra_mapper": 1},
        )
    try:
        refs = [
            evaluate_candidate.chia_remote(
                candidate.to_dict(),
                _chia_tag=(
                    f"{candidate.kernel}_{candidate.rows}x{candidate.columns}"
                    f"_u{candidate.unroll_factor}"
                ),
            )
            for candidate in candidates
        ]
        results = [MappingResult.from_dict(value) for value in get(refs)]
        return summarize_search(
            results, "chia", time.monotonic() - started
        )
    finally:
        if started_ray:
            ray.shutdown()
