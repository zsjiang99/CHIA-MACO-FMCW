# Results

`codesign_search_certified.json` is the authoritative CHIA run used by the
paper. It contains all 36 raw mappings, per-architecture compiler selections,
the analytical frame estimates, and Pareto labels.

`reference_4x4.json` is a five-kernel mapper smoke result using the final
mapping views. Files under `audit/invalid_cleanup_loop` are retained only to
document the rejected early experiment in which LLVM/CGRA-Mapper selected a
scalar cleanup loop. They must not be used as performance results.
