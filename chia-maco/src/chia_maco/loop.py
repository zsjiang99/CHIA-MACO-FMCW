"""Programmatic CHIA loop for FMCW compiler/architecture evaluation."""

from __future__ import annotations

import ray
from chia.base.ChiaFunction import get

from .nodes import evaluate_candidate
from .schema import CoDesignCandidate


def run_reference_candidate() -> dict:
    """Run one real mapper evaluation through a CHIA remote node."""

    started_ray = not ray.is_initialized()
    if started_ray:
        ray.init(
            include_dashboard=False,
            resources={"cgra_mapper": 1},
        )

    try:
        candidate = CoDesignCandidate(kernel="fmcw_window")
        result_ref = evaluate_candidate.chia_remote(
            candidate.to_dict(),
            _chia_tag="fmcw_window_reference_4x4",
        )
        return get(result_ref)
    finally:
        if started_ray:
            ray.shutdown()

