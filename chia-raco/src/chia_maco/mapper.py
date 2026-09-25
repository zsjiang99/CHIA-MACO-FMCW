"""Local, deterministic wrapper around the CGRA-Mapper Docker image."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

from .schema import (
    CoDesignCandidate,
    KERNEL_FUNCTIONS,
    KERNEL_LOOPS,
    MappingResult,
)


INTEGER_PATTERNS = {
    "mapping_ii": re.compile(r"\[Mapping II:\s*(\d+)\]"),
    "resource_mii": re.compile(r"\[ResMII:\s*(\d+)\]"),
    "recurrence_mii": re.compile(r"\[RecMII:\s*(\d+)\]"),
    "dfg_nodes": re.compile(r"DFG node count:\s*(\d+)"),
    "dfg_edges": re.compile(r"DFG edge count:\s*(\d+)"),
}
UTILIZATION_PATTERN = re.compile(
    r"tile avg fu utilization:\s*([0-9.]+)%;\s*"
    r"avg xbar utilization:\s*([0-9.]+)%"
)


def _last_integer(pattern: re.Pattern[str], output: str) -> int | None:
    matches = pattern.findall(output)
    return int(matches[-1]) if matches else None


def parse_mapper_output(
    candidate: CoDesignCandidate,
    output: str,
    elapsed_seconds: float,
    return_code: int = 0,
) -> MappingResult:
    """Convert verbose CGRA-Mapper text into a stable result contract."""

    candidate.validate()
    utilization_matches = UTILIZATION_PATTERN.findall(output)
    fu_utilization = None
    xbar_utilization = None
    if utilization_matches:
        fu_utilization = float(utilization_matches[-1][0])
        xbar_utilization = float(utilization_matches[-1][1])

    success = return_code == 0 and "[Mapping Success]" in output
    error = None
    if not success:
        if return_code != 0:
            error = f"CGRA-Mapper exited with status {return_code}"
        elif "[Mapping Failed]" in output:
            error = "CGRA-Mapper could not place and route the DFG"
        else:
            error = "CGRA-Mapper did not report a mapping outcome"

    values = {
        name: _last_integer(pattern, output)
        for name, pattern in INTEGER_PATTERNS.items()
    }
    return MappingResult(
        candidate=candidate.to_dict(),
        success=success,
        mapping_ii=values["mapping_ii"],
        resource_mii=values["resource_mii"],
        recurrence_mii=values["recurrence_mii"],
        dfg_nodes=values["dfg_nodes"],
        dfg_edges=values["dfg_edges"],
        fu_utilization_percent=fu_utilization,
        xbar_utilization_percent=xbar_utilization,
        elapsed_seconds=elapsed_seconds,
        error=error,
    )


class MapperEvaluator:
    """Compile one FMCW kernel and map it on one CGRA candidate."""

    def __init__(
        self,
        workload_dir: Path | None = None,
        docker_image: str = "cgramapper:v1",
        timeout_seconds: int = 60,
    ) -> None:
        root = Path(__file__).resolve().parents[2]
        self.workload_dir = workload_dir or root / "workload"
        self.docker_image = docker_image
        self.timeout_seconds = timeout_seconds

    def _mapper_parameters(self, candidate: CoDesignCandidate) -> dict:
        params = {
            "kernel": KERNEL_FUNCTIONS[candidate.kernel],
            "targetFunction": False,
            "targetNested": False,
            "targetLoopsID": [KERNEL_LOOPS[candidate.kernel]],
            "doCGRAMapping": True,
            "row": candidate.rows,
            "column": candidate.columns,
            "vectorizationMode": candidate.architecture_vectorization,
            "fusionStrategy": [],
            "isTrimmedDemo": True,
            "heuristicMapping": candidate.heuristic_mapping,
            "parameterizableCGRA": False,
            "bypassConstraint": candidate.bypass_constraint,
            "isStaticElasticCGRA": False,
            "precisionAware": False,
            "ctrlMemConstraint": candidate.control_memory,
            "regConstraint": candidate.register_count,
            "supportDVFS": False,
            "DVFSIslandDim": 2,
            "DVFSAwareMapping": False,
            "enablePowerGating": False,
        }
        if candidate.fu_profile != "legacy":
            from .architecture import architecture_config, custom_architecture
            arch = (custom_architecture(candidate.rows, candidate.columns, candidate.tile_fus,
                                        candidate.control_memory, candidate.memory_banks,
                                        candidate.memory_banks * candidate.bank_kib)
                    if candidate.fu_profile == "custom" else
                    architecture_config(candidate.rows, candidate.columns, candidate.fu_profile,
                                        candidate.memory_banks, candidate.bank_kib))
            params.update(parameterizableCGRA=True, tiles=arch["tiles"], links=arch["links"])
        return params

    def evaluate(
        self,
        candidate: CoDesignCandidate,
        raw_log_path: Path | None = None,
        artifact_dir: Path | None = None,
    ) -> MappingResult:
        candidate.validate()
        if artifact_dir is not None and artifact_dir.exists():
            raise ValueError("Choose a new artifact directory; evidence is never overwritten")
        started = time.monotonic()

        with tempfile.TemporaryDirectory(prefix="chia_maco_") as temporary:
            work_dir = Path(temporary)
            shutil.copy2(
                self.workload_dir / "fmcw_mapping.c",
                work_dir / "fmcw_mapping.c",
            )
            shutil.copy2(self.workload_dir / "fmcw.h", work_dir / "fmcw.h")
            (work_dir / "param.json").write_text(
                json.dumps(self._mapper_parameters(candidate), indent=2) + "\n",
                encoding="utf-8",
            )

            vector_flags = ""
            if not candidate.compiler_vectorize:
                vector_flags = "-fno-vectorize -fno-slp-vectorize"
            container_command = " && ".join(
                [
                    "clang-12 -emit-llvm -O3 -fno-unroll-loops "
                    f"-DFMCW_UNROLL_FACTOR={candidate.unroll_factor} "
                    f"-DFMCW_RANGE_BINS={candidate.range_bins} -DFMCW_DOPPLER_BINS={candidate.doppler_bins} "
                    f"-DFMCW_RX_CHANNELS={candidate.rx_channels} "
                    f"{vector_flags} -I. -c fmcw_mapping.c -o kernel_map.bc",
                    "opt-12 -load "
                    "/root/cgra/CGRA-Mapper/build/src/libmapperPass.so "
                    "-mapperPass -disable-output kernel_map.bc",
                ]
            )
            if artifact_dir is not None:
                container_command += " && llvm-dis-12 kernel_map.bc -o kernel_map.ll"
            container_name = f"chia-raco-{uuid.uuid4().hex[:12]}"
            command = [
                "docker",
                "run",
                "--rm",
                "--name",
                container_name,
                "-v",
                f"{work_dir}:/work",
                "-w",
                "/work",
                self.docker_image,
                "bash",
                "-lc",
                container_command,
            ]
            try:
                completed = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_seconds,
                    check=False,
                )
            except subprocess.TimeoutExpired as error:
                subprocess.run(
                    ["docker", "rm", "-f", container_name],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                stdout = error.stdout or ""
                stderr = error.stderr or ""
                if isinstance(stdout, bytes):
                    stdout = stdout.decode(errors="replace")
                if isinstance(stderr, bytes):
                    stderr = stderr.decode(errors="replace")
                completed = subprocess.CompletedProcess(
                    command, 124, stdout, stderr + "\nmapper timeout\n"
                )
            output = completed.stdout + completed.stderr

            if raw_log_path is not None:
                raw_log_path.parent.mkdir(parents=True, exist_ok=True)
                raw_log_path.write_text(output, encoding="utf-8")
            if artifact_dir is not None:
                shutil.copytree(work_dir, artifact_dir)

        return parse_mapper_output(
            candidate,
            output,
            time.monotonic() - started,
            completed.returncode,
        )
