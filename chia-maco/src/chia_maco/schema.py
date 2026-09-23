"""Validated contracts for compiler/architecture candidates and results."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


KERNEL_LOOPS = {
    "fmcw_window": 0,
    "fmcw_fft_stage": 0,
    "fmcw_transpose": 0,
    "fmcw_accumulate_power": 0,
    "fmcw_cfar_2d": 0,
}
KERNEL_FUNCTIONS = {
    "fmcw_window": "fmcw_window_map",
    "fmcw_fft_stage": "fmcw_fft_stage_map",
    "fmcw_transpose": "fmcw_transpose_map",
    "fmcw_accumulate_power": "fmcw_accumulate_power_map",
    "fmcw_cfar_2d": "fmcw_cfar_2d_map",
}
ARRAY_SIZES = {(size, size) for size in range(2, 9)}
VECTOR_MODES = {"none", "interleaved", "all"}
UNROLL_FACTORS = set(range(1, 9))


@dataclass(frozen=True)
class CoDesignCandidate:
    """One bounded compiler/architecture configuration."""

    kernel: str
    rows: int = 4
    columns: int = 4
    unroll_factor: int = 1
    compiler_vectorize: bool = False
    architecture_vectorization: str = "none"
    bypass_constraint: int = 4
    control_memory: int = 32
    register_count: int = 8
    heuristic_mapping: bool = True
    range_bins: int = 256
    doppler_bins: int = 128
    rx_channels: int = 4
    fu_profile: str = "legacy"
    memory_banks: int = 0
    bank_kib: int = 16
    tile_fus: dict[str, list[str]] | None = None

    def validate(self) -> None:
        from .workload import Workload
        from .architecture import FU_PROFILES, FU_TYPES
        Workload(samples=self.range_bins, chirps=self.doppler_bins, rx=self.rx_channels).validate()
        if self.fu_profile not in ("legacy", "custom", *FU_PROFILES):
            raise ValueError("unsupported FU profile")
        if self.memory_banks not in ((0,) if self.fu_profile == "legacy" else (1, 2, 4, 8)):
            raise ValueError("parameterized architecture needs 1, 2, 4 or 8 memory banks")
        if not 1 <= self.bank_kib <= 256:
            raise ValueError("unsupported SRAM capacity per bank")
        if self.fu_profile == "custom":
            expected = {str(i) for i in range(self.rows * self.columns)}
            if not isinstance(self.tile_fus, dict) or set(self.tile_fus) != expected:
                raise ValueError("custom architecture needs one FU list per tile")
            if any(not isinstance(fus, list) or not fus or any(fu not in FU_TYPES for fu in fus)
                   for fus in self.tile_fus.values()):
                raise ValueError("custom architecture contains unsupported FUs")
        elif self.tile_fus is not None:
            raise ValueError("tile_fus is valid only for a custom architecture")
        if self.kernel not in KERNEL_LOOPS:
            raise ValueError(f"unsupported kernel: {self.kernel}")
        if (self.rows, self.columns) not in ARRAY_SIZES:
            raise ValueError(
                f"unsupported array size: {self.rows}x{self.columns}"
            )
        if self.unroll_factor not in UNROLL_FACTORS:
            raise ValueError(f"unsupported unroll factor: {self.unroll_factor}")
        if self.architecture_vectorization not in VECTOR_MODES:
            raise ValueError(
                "architecture_vectorization must be none, interleaved, or all"
            )
        if not 1 <= self.bypass_constraint <= 8:
            raise ValueError("bypass_constraint must be between 1 and 8")
        if not 16 <= self.control_memory <= 1024:
            raise ValueError("control_memory must be between 16 and 1024")
        if not 2 <= self.register_count <= 32:
            raise ValueError("register_count must be between 2 and 32")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "CoDesignCandidate":
        candidate = cls(**value)
        candidate.validate()
        return candidate


@dataclass(frozen=True)
class MappingResult:
    """Structured CGRA-Mapper outcome returned to the CHIA loop."""

    candidate: dict[str, Any]
    success: bool
    mapping_ii: int | None
    resource_mii: int | None
    recurrence_mii: int | None
    dfg_nodes: int | None
    dfg_edges: int | None
    fu_utilization_percent: float | None
    xbar_utilization_percent: float | None
    elapsed_seconds: float
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "MappingResult":
        return cls(**value)
