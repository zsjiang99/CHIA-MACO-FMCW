"""CHIA nodes for CGRA compiler/architecture evaluation."""

from __future__ import annotations
from pathlib import Path

from chia.base.ChiaFunction import ChiaFunction

from .mapper import MapperEvaluator
from .schema import CoDesignCandidate


@ChiaFunction(resources={"cgra_mapper": 1})
def evaluate_candidate(candidate_data: dict, raw_log_path: str | None = None) -> dict:
    """Compile and map one validated FMCW compiler/CGRA candidate."""

    candidate = CoDesignCandidate.from_dict(candidate_data)
    return MapperEvaluator().evaluate(candidate, raw_log_path=Path(raw_log_path) if raw_log_path else None).to_dict()
