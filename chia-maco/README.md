# CHIA-MACO

Agentic compiler/architecture co-design for an FMCW radar pipeline on a
parameterized CGRA.

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

## MACO agents with Qwen 3.8 27B

The four original MACO agent classes are reused: Co-designer → Fixer → Coarse
Judge → Fine Judge. Qwen proposes and ranks whole-frame plans; CHIA executes
real LLVM/CGRA-Mapper evaluations and feeds measured costs into the next round.
The enumeration above remains a separate baseline, never input to the agents.

```bash
# From chia-maco; install this package in ../.venv first.
export MACO_LLM_BASE_URL=http://127.0.0.1:18161/v1
export MACO_LLM_MODEL=harp-raw-base
../.venv/bin/python -m chia_maco.cli agent-search \
  --output-dir results/my_agent_run --rounds 3 --mapping-budget 30 --seed 37
```

Use a new output directory each time. The configured local service serves the
raw Qwen3.8-27B model with NF4 double quantization, not a HARP policy adapter.
The service must already be running and permit at least 4096 completion tokens;
model weights and the serving process are not bundled. Other compatible endpoints use the same environment variables and,
if needed, `MACO_LLM_API_KEY`. No key is written into the artifact.

- Search: arrays 2×2/4×4/6×6 and five legal per-kernel unroll factors. Other
  hardware parameters stay fixed; unsupported knobs are rejected.
- Budget: 3 rounds, 2 proposals/round, at most 12 model calls and 30 unique
  mappings. Duplicate mappings reuse only this run's cache.
- Evidence: `agent_trace.json` contains prompts, responses, usage and events;
  `mapper_logs/` contains raw tool output; `result.json` contains measured plans.
- Failure: malformed/truncated model output stops the run visibly. No random
  candidates, replayed results or fabricated metrics replace failures.
- Scope: decaying-epsilon exploration hints and a confidence diagnostic are adapted
  from MACO. Every shortlisted plan that fits the budget is tool-validated;
  confidence does not skip tools. This is not full MACO PPA/CAS reproduction.

`best_evaluated_plan` is an actually evaluated whole-frame plan. The separate
`architectures` frontier may combine independently measured kernel settings.
Do not confuse these two results or claim agent search beats enumeration.

For the live GUI, run `bash gui/start.sh` and open port 8765. Select **MACO agents**
or **Enumeration baseline**, then **Run new search**. The agent view shows model
identity, four roles, round decisions, measured winners, token counts and events.
See `../gui/README.md` for the frontend build and remote access.

Source provenance and the upstream licensing caveat are in
`src/chia_maco/vendor/maco/NOTICE.md`. Public publishing remains a separate step.

Validated run: `results/agent_qwen38_27b_seed37_v3/` — 3 rounds, 12 model calls,
18/18 real mappings, 210.43 s. Best: 4×4, unroll `[4,2,4,4,1]`, 39,154,344 cycles.
It matches the separate 36-mapping reference but is slower end-to-end. The v1
integration trial and failed v2 trace are retained separately, not reported as
the validated result.
