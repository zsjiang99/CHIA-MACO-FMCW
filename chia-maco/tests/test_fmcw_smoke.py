import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_native_pipeline_recovers_injected_target() -> None:
    subprocess.run(["make", "build/fmcw_smoke"], cwd=ROOT, check=True)
    completed = subprocess.run(
        [str(ROOT / "build" / "fmcw_smoke")],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    result = json.loads(completed.stdout)

    assert result["peak_range"] == 17
    assert result["peak_doppler"] == 9
    assert result["detections"] >= 1
    assert result["power_sum"] > 0.0

