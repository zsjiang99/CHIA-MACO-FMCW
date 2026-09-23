import pytest

from chia_maco.mapper import parse_mapper_output
from chia_maco.schema import CoDesignCandidate
from chia_maco.architecture import architecture_config


def test_candidate_rejects_unbounded_array_size() -> None:
    with pytest.raises(ValueError, match="unsupported array size"):
        CoDesignCandidate(kernel="fmcw_window", rows=32, columns=32).validate()


def test_mapper_output_is_structured() -> None:
    candidate = CoDesignCandidate(kernel="fmcw_window")
    output = """
    [ResMII: 2]
    [RecMII: 2]
    [Mapping II: 4]
    DFG node count: 17; DFG edge count: 22; SIMD node count: 0
    [Mapping Success]
    tile avg fu utilization: 26.5625%; avg xbar utilization: 60.9375%;
    """

    result = parse_mapper_output(candidate, output, 0.5)

    assert result.success
    assert result.mapping_ii == 4
    assert result.resource_mii == 2
    assert result.recurrence_mii == 2
    assert result.dfg_nodes == 17
    assert result.dfg_edges == 22
    assert result.fu_utilization_percent == 26.5625
    assert result.xbar_utilization_percent == 60.9375


def test_cgra_flow_architecture_has_real_fu_and_memory_configuration() -> None:
    arch = architecture_config(4, 4, "checkerboard", 2, 16)
    assert arch["memory"]["capacity_kib"] == 32
    assert arch["memory"]["interface_tiles"] == [0, 8]
    assert arch["multiplier_tiles"] == 8
    assert "Mul" in arch["tiles"]["0"]["supportedFUs"]
    assert "Mul" not in arch["tiles"]["1"]["supportedFUs"]
    assert arch["tiles"]["0"]["accessMem"]
