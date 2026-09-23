# Evidence for the four-page paper

From a fresh clone, `make -C chia-maco artifact-check` prints and checks the
paper's headline numbers using these saved files. It does not invoke a mapper
or model service.

| Paper claim | Authoritative record |
| --- | --- |
| 36 reference mappings; best 39,154,344 estimated cycles/frame | [`codesign_search_certified.json`](codesign_search_certified.json): `raw_results`, `successful_mappings`, `architectures[].frame_estimate` |
| 18 unique agent mappings, 12 model calls, same best estimate | [`agent_qwen38_27b_seed37_v3/result.json`](agent_qwen38_27b_seed37_v3/result.json): `evaluations`, `llm_calls`, `best_evaluated_plan` |
| Agent proposals and tool feedback | [`agent_trace.json`](agent_qwen38_27b_seed37_v3/agent_trace.json), [raw mapper logs](agent_qwen38_27b_seed37_v3/mapper_logs/) |
| CA-CFAR contributes 89.7% of selected frame estimate | `best_evaluated_plan.frame_estimate.breakdown.fmcw_cfar_2d` in the agent result above |
| Exact NumPy/native CFAR masks agree in 2 of 6 scenes | [`validation_v1/validation.json`](validation_v1/validation.json): `cases[].status` and `detection_mismatches` |

The reference archive stores parsed mapping records; the reported agent
archive also retains raw logs and model messages. [`reference_4x4.json`](reference_4x4.json)
is a five-kernel mapper smoke, not the 36-point result. The `agent_qwen38_27b_seed37_v1/`
and `v2/` directories are earlier trials, not substituted for the reported
`v3/` run. `agent_workload_banked_20260921_152350/`, `rtl_audit/`, and
`rtl_bridge_v*/` document experimental extensions outside the paper's
array/unroll comparison. `audit/invalid_cleanup_loop/` preserves a rejected
early mapping and must not be used as a performance result.

All frame-cycle figures are analytical estimates from mapping initiation
intervals, not measured FPS, area, total energy, or verified CGRA execution.
