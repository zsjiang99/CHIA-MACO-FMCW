# RACO matched-budget records

These are the recorded seed-37 runs for the manuscript's 256-sample/chirp, 128-chirp/frame, 4-RX FMCW case. All three methods used the same served model, CHIA evaluator, frame-cost model, and budget of **10 unique kernel-mapper evaluations**. A complete design requires five evaluations, one per kernel view; the budget is **not** 10 complete CGRA designs. The results are mapper-derived steady-state estimates, not measured frame latency.

| Method | Result and trace | Successful mappings | Best estimated cycles/frame |
| --- | --- | ---: | ---: |
| RACO | [full_maco/result.json](full_maco/result.json) · [trace](full_maco/agent_trace.json) · [logs](full_maco/mapper_logs/) | 10/10 | **38,728,360** |
| HW-only | [hardware_only/result.json](hardware_only/result.json) · [trace](hardware_only/agent_trace.json) · [logs](hardware_only/mapper_logs/) | 10/10 | 42,136,232 |
| Single-agent one-shot | [single_agent/result.json](single_agent/result.json) · [trace](single_agent/agent_trace.json) · [logs](single_agent/mapper_logs/) | 9/10 | 41,448,104 |

Each folder also contains `request.json`. The `result.json` files record the selected whole-frame plan in `best_evaluated_plan`, all evaluated kernel mappings in `raw_results`, and the budget in `config.mapping_budget`. The trace records proposals, corrections, shortlist, judge choice, and mapper events. These three runs each have **one round**, so they do not demonstrate a subsequent feedback-driven design change.

The RACO run evaluated two complete 4×4 designs. Its selected design uses 4 × 16 KiB SRAM and unroll factors `[4, 4, 4, 4, 1]`, costing 38,728,360 cycles/frame. The other uses 8 × 16 KiB SRAM and `[2, 2, 2, 2, 1]`, costing 40,202,920 cycles/frame. The per-kernel II and cycle contributions are in `history[].frame_estimate.breakdown`.

The separate [two-round trace](two_round_trace/result.json) contains 20 kernel-mapper attempts (17 successful) and [raw logs](two_round_trace/mapper_logs/). Round two received candidate configurations, validity, and aggregate costs—not per-kernel II values. Its additional proposal failed three kernel mappings and did not improve the first-round 38,728,360-cycle incumbent. It is not part of the 10-evaluation baseline comparison.
