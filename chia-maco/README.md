# RACO

Agentic CGRA hardware/software co-design for FMCW radar with CHIA.

Current implementation and open validation issues:
[IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md). Hardware feasibility is
not yet established. Start with the release-root README for setup and demo steps.

The workload is one end-to-end native C reference with separately callable,
mapping-friendly kernels for windowing, FFT butterflies, transposition, power
accumulation, and 2-D CA-CFAR. CGRA-Mapper evaluates one hot loop at a time; the
artifact combines the measured per-kernel costs into a frame-level objective.

## Native workload smoke test

```bash
make smoke
```

The smoke test builds the C workload, runs a deterministic synthetic target,
and checks that the range-Doppler peak is recovered at the injected bin.

## Nominal workload

- 256 ADC samples per chirp
- 128 chirps per frame
- 4 receive channels
- complex single-precision reference data

## Reproducible mapper gates

```bash
make mapper-smoke    # map all five hotspots on the reference 4x4 CGRA
make reference-run   # also save results/reference_4x4.json
make chia-smoke      # evaluate one real candidate through a CHIA node
make codesign-search # 36-point compiler/architecture search via CHIA
```

The frame estimate multiplies each measured mapping initiation interval by its
scheduled loop-group count, rounded per invocation after unrolling. It is a transparent steady-state proxy, not a
cycle-accurate system simulation; the JSON records the excluded costs.

The bounded co-design search evaluates three array sizes and legal compiler
unroll factors for each hotspot. CFAR remains scalar because its unrolled DFG
exceeds the artifact's 60-second evaluation budget. The search selects the best compiler setting per
kernel, reports the cycle/tile Pareto front, and retains all raw mapper results.
`workload/fmcw_mapping.c` contains fixed-shape, source-unrolled views of the
same stage operations so CGRA-Mapper always targets one unambiguous steady-state
loop rather than an LLVM scalar remainder.

The archived certified run is `results/codesign_search_certified.json`: all
36 mappings succeeded. The 2x2 and 4x4 arrays form the cycle/tile Pareto front;
4x4 has the lowest estimate (39,154,344 cycles), while 2x2 minimizes the
cycle-times-tile product. These are mapper-derived analytical estimates, not
cycle-accurate, PPA, energy, or throughput measurements.

## Reported RACO comparison

The [matched-budget records](results/matched_budget_10/) contain the manuscript's seed-37 runs: RACO, HW-only, and single-agent one-shot, each with a budget of 10 unique kernel-mapper evaluations. RACO reaches 38,728,360 estimated cycles/frame, compared with 42,136,232 and 41,448,104. These are one-round runs; the separate 20-evaluation trace records cross-round feedback. Each run retains `request.json`, `result.json`, `agent_trace.json`, and raw `mapper_logs/`.

The browser's **Live exploration** mode runs the broader design space and offers **Multi-agent**, **Hardware only**, and **Single agent** methods. See the release-root README for model, mapper, and GUI setup. Set `RACO_LLM_BASE_URL`, `RACO_LLM_MODEL`, and, if needed, `RACO_LLM_API_KEY`; the model service and weights are not bundled. Set `RACO_AGENT_DIR` to the pinned upstream agent checkout when running from a fresh clone. Use a new output directory for every run.

The `agent-search` CLI command without a workload argument still executes the earlier array/unroll experiment; it does **not** reproduce the new matched-budget RACO comparison. Likewise, `make codesign-search` creates the earlier 36-evaluation reference. Their archived records remain under `results/` for provenance, not as substitutes for the manuscript's current three-method comparison.

`best_evaluated_plan` is an actually evaluated whole-frame plan. Mapping success establishes a schedulable extracted graph, not end-to-end hardware correctness. Source provenance and licensing information are in `src/chia_maco/vendor/maco/NOTICE.md`.
