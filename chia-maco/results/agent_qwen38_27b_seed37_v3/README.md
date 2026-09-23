# Validated Qwen / MACO run

Launched from the MACO browser GUI, job `ba49954f18544716b881ba3408d0dae9`.
This is the reported agent run; the runtime directory was copied here unchanged
so it is not lost through the runtime `.gitignore` rule.

- Qwen3.8-27B raw base model, NF4 double quantization; seed 37, temperature 0.2.
- 3 rounds, 12 real model calls, 18/18 successful fresh CHIA mapper evaluations.
- 210.43 s end-to-end; 29,657 prompt + 1,700 completion tokens.
- Best actual full plan: 4×4, unroll `[4,2,4,4,1]`, 39,154,344 estimated cycles.
- Round 1: 40,170,152 cycles. Round 2 repeats plans (cached). Round 3 improves.
- Same best estimate as the separate 36-mapping reference; no general search
  efficiency claim, and end-to-end latency is higher than that reference.

`result.json` records source hashes, model identity, all plans and mappings.
`agent_trace.json` includes unedited responses and usage. `mapper_logs/` contains
all 18 raw tool logs. `meta.json` and `worker.log` retain the GUI execution record.

Local mapper image ID:
`sha256:f506edb0b749589ae3d1002ddc08734d4f79ce45246fb46c99967b202e8c3548`.
This is an image ID, not a published registry digest or downloadable image URL.

Earlier trials remain separate: `v1` predates the corrected bounded-validator
injection and is not the reported result; `v2` failed on truncated coarse-judge
JSON. Neither is silently replaced by this successful run.
