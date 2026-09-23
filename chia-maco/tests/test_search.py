from chia_maco.schema import CoDesignCandidate, KERNEL_LOOPS, MappingResult
from chia_maco.search import search_candidates, summarize_search


def _result(kernel: str, rows: int, ii: int) -> MappingResult:
    return MappingResult(
        candidate=CoDesignCandidate(
            kernel=kernel, rows=rows, columns=rows
        ).to_dict(),
        success=True,
        mapping_ii=ii,
        resource_mii=1,
        recurrence_mii=1,
        dfg_nodes=1,
        dfg_edges=1,
        fu_utilization_percent=1.0,
        xbar_utilization_percent=1.0,
        elapsed_seconds=0.1,
    )


def test_search_space_size() -> None:
    assert len(search_candidates()) == 3 * (3 + 2 + 3 + 3 + 1)


def test_pareto_marks_area_latency_tradeoff() -> None:
    results = [
        _result(kernel, rows, {2: 6, 4: 3, 6: 2}[rows])
        for rows in (2, 4, 6)
        for kernel in KERNEL_LOOPS
    ]
    summary = summarize_search(results, "test", 1.0)
    assert all(item["pareto_optimal"] for item in summary["architectures"])
