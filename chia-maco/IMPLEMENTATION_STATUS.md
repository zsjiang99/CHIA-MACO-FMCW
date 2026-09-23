# MACO artifact status

## Reported CHIA–mapper experiment

The paper's frozen reference contains 36 successful mappings over 2×2, 4×4,
and 6×6 arrays with legal per-kernel unroll factors. The archived three-round
Qwen run contains 12 model calls and 18 fresh mappings; its best actual
full-frame plan matches the reference's 39,154,344-cycle analytical estimate.
These values come from mapper initiation intervals and a documented frame-cost
model, not RTL execution or measured throughput.

The native C smoke test recovers the injected range–Doppler peak. Independent
NumPy/native validation passes strict complete CFAR-mask equality in 2 of 6
scenes; all four failures are retained in `results/validation_v1/`.

## Experimental hardware extension

The GUI can request memory-bank/FU exploration, RTL generation, synthesis,
and CGRA-core layout. These are separate from the paper's search. FP32 FU/tile
regressions pass, but a complete mapper-schedule loader and whole-frame
candidate execution have not been established. No archived mapper result is
therefore labeled hardware-correct, area-feasible, or FPS-feasible. Core-only
layout excludes the Data SPM; it must not be presented as full-chip PPA.

## Reproduce

Follow the release-root `README.md` for pinned dependency setup, C smoke,
tests, mapper runs, agent runs, and the browser demo. `validate-native` returns
a nonzero exit code because four strict CFAR scenes currently fail; this is
expected and should not be masked.
