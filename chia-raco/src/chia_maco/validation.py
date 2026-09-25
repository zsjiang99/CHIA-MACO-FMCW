"""Independent NumPy oracle against the unchanged native C pipeline, not RTL."""
from __future__ import annotations

import ctypes
import hashlib
import json
from pathlib import Path
import subprocess

import numpy as np

ROOT = Path(__file__).resolve().parents[2]


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def scene(name, shape, seed):
    rx, chirps, samples = np.indices(shape)
    def tone(r, d, amplitude=1):
        return amplitude * np.exp(1j * (2 * np.pi * (r * samples / shape[2] + d * chirps / shape[1]) + .17 * rx))
    data = tone(17, 9)
    if name in ("multiple_targets", "noisy_targets"):
        data += tone(63, 24, .6)
    if name == "noisy_targets":
        rng = np.random.default_rng(seed)
        data += .1 * (rng.normal(size=shape) + 1j * rng.normal(size=shape))
    elif name == "zero":
        data *= 0
    elif name == "edge_target":
        data = tone(0, 127)
    elif name == "large_amplitude":
        data *= 30000
    elif name not in ("single_target", "multiple_targets"):
        raise ValueError(f"unknown scene: {name}")
    return data.astype(np.complex64)


def cfar(power, training_radius=4, guard_radius=1, threshold_scale=6):
    """Vectorized 2-D box-window oracle; no translation of the C summation loop."""
    radius = training_radius + guard_radius
    windows = np.lib.stride_tricks.sliding_window_view(power, (2 * radius + 1,) * 2)
    mask = np.ones(windows.shape[-2:], dtype=bool)
    mask[radius-guard_radius:radius+guard_radius+1, radius-guard_radius:radius+guard_radius+1] = False
    thresholds = np.zeros_like(power, dtype=np.float64)
    thresholds[radius:-radius, radius:-radius] = np.sum(windows[..., mask], axis=-1, dtype=np.float64) * threshold_scale / mask.sum()
    detections = np.zeros(power.shape, dtype=np.uint8)
    detections[radius:-radius, radius:-radius] = power[radius:-radius, radius:-radius] > thresholds[radius:-radius, radius:-radius]
    return detections, thresholds


def golden(data, spec):
    # Match the public float32 input/window contract, not the native FFT algorithm.
    window = np.hanning(data.shape[-1]).astype(np.float32).astype(np.float64)
    windowed = data.astype(np.complex128) * window
    ranges = np.fft.fft(windowed, axis=2)
    transposed = np.ascontiguousarray(ranges.transpose(0, 2, 1))
    doppler = np.fft.fft(transposed, axis=2)
    power = np.sum(np.abs(doppler) ** 2, axis=0)
    detections, thresholds = cfar(power, **spec["cfar"])
    return {"range_fft": ranges, "doppler_fft": doppler, "power": power, "detections": detections, "thresholds": thresholds}


class NativePipeline:
    def __init__(self, output):
        library = output / "fmcw_native.so"
        self.command = ["cc", "-shared", "-fPIC", "-O3", "-std=c11", "-fno-fast-math",
                        "-ffp-contract=off", str(ROOT / "workload/fmcw.c"), "-o", str(library)]
        subprocess.run(self.command, check=True, capture_output=True)
        self.library = ctypes.CDLL(str(library.resolve()))
        self.library.fmcw_pipeline.argtypes = [np.ctypeslib.ndpointer(dtype=np.float32, flags="C_CONTIGUOUS")] * 12 + [np.ctypeslib.ndpointer(dtype=np.uint8, flags="C_CONTIGUOUS")]
        self.library.fmcw_pipeline.restype = None

    def run(self, data):
        if data.shape != (4, 128, 256):
            raise ValueError("native pipeline has fixed shape (4, 128, 256)")
        def f32(x):
            return np.ascontiguousarray(x, dtype=np.float32)
        def twiddles(n):
            w = np.exp(-2j * np.pi * np.arange(n // 2) / n)
            return f32(w.real), f32(w.imag)
        rr, ri = (np.zeros(data.shape, np.float32) for _ in range(2))
        dr, di = (np.zeros((4, 256, 128), np.float32) for _ in range(2))
        power, detections = np.zeros((256, 128), np.float32), np.zeros((256, 128), np.uint8)
        self.library.fmcw_pipeline(f32(data.real), f32(data.imag), f32(np.hanning(256)),
                                  *twiddles(256), *twiddles(128), rr, ri, dr, di, power, detections)
        return {"range_fft": rr + 1j * ri, "doppler_fft": dr + 1j * di, "power": power, "detections": detections}


def compare(expected, actual, spec):
    stages = {}
    for name in ("range_fft", "doppler_fft", "power"):
        reference, candidate = expected[name], actual[name]
        if reference.shape != candidate.shape:
            raise ValueError(f"{name}: shape mismatch")
        scale = float(np.max(np.abs(reference)))
        finite = bool(np.isfinite(candidate).all() and np.isfinite(reference).all())
        error = float(np.max(np.abs(candidate - reference))) if finite else None
        limit = scale * spec["normalized_max_error_limit"] if scale else spec["zero_reference_absolute_limit"]
        stages[name] = {"max_absolute_error": error, "normalized_max_error": error / scale if finite and scale else None,
                        "absolute_limit": limit, "passed": finite and error <= limit}
    mismatch = expected["detections"] != actual["detections"]
    count = int(mismatch.sum())
    return {"status": "passed" if all(s["passed"] for s in stages.values()) and count == 0 else "failed",
            "stages": stages, "detection_mismatches": count,
            "golden_detections": int(expected["detections"].sum()), "native_detections": int(actual["detections"].sum()),
            "golden_peak": list(map(int, np.unravel_index(np.argmax(expected["power"]), expected["power"].shape))),
            "native_peak": list(map(int, np.unravel_index(np.argmax(actual["power"]), actual["power"].shape)))}


def run_validation(output: Path):
    output.mkdir(parents=True, exist_ok=False)
    spec_path = ROOT / "configs/validation.json"
    spec = json.loads(spec_path.read_text())
    native = NativePipeline(output)
    reports = []
    for name in spec["scenes"]:
        data = scene(name, tuple(spec["shape_rx_chirps_samples"]), spec["seed"])
        expected, actual = golden(data, spec), native.run(data)
        # Store full numerical evidence; the browser can downsample only for display.
        bundle = output / f"{name}.npz"
        np.savez_compressed(bundle, input=data, **{f"golden_{k}": v for k, v in expected.items()},
                            **{f"native_{k}": v for k, v in actual.items()})
        reports.append({"scene": name, **compare(expected, actual, spec), "arrays": bundle.name, "sha256": sha256(bundle)})
    report = {"scope": spec["scope"], "spec": spec, "spec_sha256": sha256(spec_path),
              "source_sha256": {p.name: sha256(p) for p in (Path(__file__), ROOT / "workload/fmcw.c", ROOT / "workload/fmcw.h")},
              "compiler": subprocess.check_output(["cc", "--version"], text=True).splitlines()[0],
              "compile_command": native.command, "numpy_version": np.__version__, "cases": reports,
              "status": "passed" if all(r["status"] == "passed" for r in reports) else "failed",
              "candidate_hardware_correctness": "pending; no CGRA execution in this test"}
    (output / "validation.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    return report
