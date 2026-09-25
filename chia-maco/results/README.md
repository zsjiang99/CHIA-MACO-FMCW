# RACO result records

The [matched-budget records](matched_budget_10/) support the current manuscript's comparison: 38,728,360 estimated cycles/frame for RACO, 42,136,232 for HW-only, and 41,448,104 for single-agent one-shot under 10 unique kernel-mapper evaluations per method. They include result JSON, agent traces, and raw mapper logs. From a fresh clone, `make -C chia-maco artifact-check` checks these saved results without invoking a mapper or model service.

## Earlier array/unroll study

The files below belong to an earlier 36-mapping reference and 18-mapping agent study. They are retained as historical evidence, **not** substituted for the current matched-budget comparison.

| Earlier-study claim | Authoritative record |
| --- | --- |
| 36 reference mappings; best 39,154,344 estimated cycles/frame | [`codesign_search_certified.json`](codesign_search_certified.json): `raw_results`, `successful_mappings`, `architectures[].frame_estimate` |
| 18 unique agent mappings, 12 model calls, same best estimate | [`agent_qwen38_27b_seed37_v3/result.json`](agent_qwen38_27b_seed37_v3/result.json): `evaluations`, `llm_calls`, `best_evaluated_plan` |
| Agent proposals and tool feedback | [`agent_trace.json`](agent_qwen38_27b_seed37_v3/agent_trace.json), [raw mapper logs](agent_qwen38_27b_seed37_v3/mapper_logs/) |
| CA-CFAR contributes 89.7% of selected frame estimate | `best_evaluated_plan.frame_estimate.breakdown.fmcw_cfar_2d` in the agent result above |
| Exact NumPy/native CFAR masks agree in 2 of 6 scenes | [`validation_v1/validation.json`](validation_v1/validation.json): `cases[].status` and `detection_mismatches` |

The earlier study's agent/tool feedback table is reconstructed from
[`agent_qwen38_27b_seed37_v3/result.json`](agent_qwen38_27b_seed37_v3/result.json):

| Round | Fine Judge choice | Tool-selected round winner | Cumulative unique mappings | Best estimated cycles/frame |
| --- | --- | --- | ---: | ---: |
| 1 | 6×6 | 4×4 | 10 | 40,170,152 |
| 2 | 4×4 | 4×4 | 10 | 40,170,152 |
| 3 | 4×4 | 4×4 | 18 | 39,154,344 |

The round-one judge ranking was overturned by mapper-derived frame costs.
Round two reused the same candidates. This single trajectory explains the
feedback behavior; it does not establish a speedup over a budget-matched search.

The reference archive stores parsed mapping records; the earlier agent archive
retains raw logs and model messages. [`reference_4x4.json`](reference_4x4.json)
is a five-kernel mapper smoke, not the 36-point result. `rtl_audit/` and
`rtl_bridge_v3/` document component-level RTL experiments outside the paper's
matched-budget comparison.

All frame-cycle figures are analytical estimates from mapping initiation
intervals, not measured FPS, area, total energy, or verified CGRA execution.
