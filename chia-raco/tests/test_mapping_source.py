import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize("factor", range(1, 7))
def test_mapping_source_compiles_for_full_unroll_scope(factor, tmp_path):
    compiler = shutil.which("cc")
    if compiler is None:
        pytest.skip("C compiler unavailable")
    workload = Path(__file__).resolve().parents[1] / "workload"
    subprocess.run([
        compiler, "-std=c11", "-fsyntax-only", f"-DFMCW_UNROLL_FACTOR={factor}",
        "-I", str(workload), str(workload / "fmcw_mapping.c"),
    ], check=True, cwd=tmp_path)
