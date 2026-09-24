import json
from types import SimpleNamespace

import pytest

from chia_maco.agent_search import AgentConfig, LocalModel, OriginalAgents, candidates_for, run_agent_search, validate_plan
from chia_maco.architecture import BASE_FUS
from chia_maco.schema import MappingResult
from chia_maco.workload import Workload


P1 = {"tile_size": "4x4", "unroll_factors": [2, 2, 2, 2, 1], "reasoning": "Balanced plan"}
P2 = {"tile_size": "6x6", "unroll_factors": [4, 2, 4, 4, 1], "reasoning": "Wider plan"}
FULL = {"tile_size": "2x2", "FUs": {
    "tile0": ["Ld", "St", "Mul"], "tile1": ["FMul"],
    "tile2": ["FAdd"], "tile3": [],
}, "config_mem": 128, "data_spm_kb": 32, "memory_banks": 4,
    "unroll": {"window": 4, "fft": 2, "transpose": 3, "power": 4, "cfar": 1},
    "vectorize": "none", "reasoning": "Workload-specific per-tile architecture"}


class Model:
    model = "mock-for-unit-tests-only"

    def __init__(self, invalid=False):
        self.calls = []
        self.invalid = invalid

    def __call__(self, role, prompt, temperature):
        values = {
            "CGRACoDesigner": [P1, P2],
            "CGRAFixer": {"fixed_arch_json": [P1, P2]},
            "CoarseGrainedJudge": {"top_k_design": ["candidate_0", "candidate_1"]},
            "FineGrainedJudge": {"best_design": "candidate_99" if self.invalid else "candidate_0"},
        }
        self.calls.append({"role": role, "prompt": prompt, "usage": {"total_tokens": 3}})
        return json.dumps(values[role])


class FullModel(Model):
    def __call__(self, role, prompt, temperature):
        values = {
            "CGRACoDesigner": [FULL],
            "CGRAFixer": {"fixed_arch_json": [FULL]},
            "CoarseGrainedJudge": {"top_k_design": ["candidate_0"]},
            "FineGrainedJudge": {"best_design": "candidate_0"},
        }
        self.calls.append({"role": role, "prompt": prompt, "usage": {"total_tokens": 3}})
        return json.dumps(values[role])


def mapper(candidate, path):
    path.write_text("unit-test mapper only\n")
    return MappingResult(candidate.to_dict(), True, 5, 1, 1, 12, 15, 30, 40, .01)


def test_original_four_agents_feedback_cache_and_provenance(tmp_path):
    model = Model()
    result = run_agent_search(tmp_path, AgentConfig(rounds=2), model, mapper)
    assert result["evaluations"] == 10  # second round reuses only this run's measurements
    assert result["llm_calls"] == 8
    assert result["llm_usage"]["total_tokens"] == 24
    assert len(result["agent_source_sha256"]) == 4
    assert result["best_evaluated_plan"]["frame_estimate"]["valid"]
    assert [c["role"] for c in model.calls[:4]] == [r for _, r in OriginalAgents.ROLES]
    fixer_prompt = model.calls[1]["prompt"]
    assert '"valid":true' in fixer_prompt  # bounded validator actually injected
    assert "FU dictionary has 0 tiles" not in fixer_prompt
    assert '"candidate_id": "candidate_0"' in model.calls[2]["prompt"]
    assert 'top_k_design as ["candidate_0"]' in model.calls[2]["prompt"]
    assert 'best_design as "candidate_0"' in model.calls[3]["prompt"]
    assert '"measured_history":[]' in model.calls[0]["prompt"]
    assert '"estimated_cycles":' in model.calls[4]["prompt"]
    assert "39154344" not in model.calls[0]["prompt"]  # no archived optimum
    trace = json.loads((tmp_path / "agent_trace.json").read_text())
    assert trace["events"][-1]["kind"] == "run_finished"
    assert any(e["kind"] == "cache_hit" for e in trace["events"])
    assert len(list((tmp_path / "mapper_logs").glob("*.log"))) == 10
    with pytest.raises(ValueError, match="never overwritten"):
        run_agent_search(tmp_path, model_call=model, evaluate=mapper)


def test_budget_does_not_partially_measure_full_plan(tmp_path):
    result = run_agent_search(tmp_path, AgentConfig(rounds=1, mapping_budget=5), Model(), mapper)
    assert result["evaluations"] == 5
    assert len(result["history"]) == 1
    trace = json.loads((tmp_path / "agent_trace.json").read_text())
    assert any(e["kind"] == "budget_skipped" for e in trace["events"])


def test_judge_cannot_invent_design_or_fall_back(tmp_path):
    with pytest.raises(ValueError, match="outside the shortlist"):
        run_agent_search(tmp_path, AgentConfig(rounds=1), Model(invalid=True), mapper)
    trace = json.loads((tmp_path / "agent_trace.json").read_text())
    assert trace["events"][-1]["kind"] == "run_failed"
    assert trace["completed"] == 0
    assert not (tmp_path / "result.json").exists()


@pytest.mark.parametrize("change", [
    {"tile_size": "8x8"}, {"FUs": {}}, {"unroll_factors": [2, 4, 2, 2, 1]},
    {"unroll_factors": [True, 2, 2, 2, 1]}, {"unroll_factors": [2, 2, 2, 2, 2]},
])
def test_reject_unsupported_knobs(change):
    with pytest.raises(ValueError):
        validate_plan({**P1, **change})


def test_full_maco_space_preserves_per_tile_architecture():
    validate_plan(FULL)
    candidates = candidates_for(FULL, Workload(max_pes=64))
    assert [candidate.unroll_factor for candidate in candidates] == [4, 2, 3, 4, 1]
    assert all(candidate.fu_profile == "custom" for candidate in candidates)
    assert all(candidate.tile_fus["1"] == [*BASE_FUS, "FMul"] for candidate in candidates)
    assert all(candidate.control_memory == 128 for candidate in candidates)
    assert all(candidate.memory_banks == 4 and candidate.bank_kib == 8 for candidate in candidates)


@pytest.mark.parametrize("factor", range(1, 7))
def test_full_maco_accepts_each_unroll_factor(factor):
    plan = {**FULL, "unroll": {name: factor for name in ("window", "fft", "transpose", "power", "cfar")}}
    validate_plan(plan)
    assert {candidate.unroll_factor for candidate in candidates_for(plan, Workload(max_pes=64))} == {factor}


def test_live_agent_uses_full_maco_space(monkeypatch, tmp_path):
    import chia_maco.memory as memory
    monkeypatch.setattr(memory, "evaluate_memory", lambda *args: {"read_nj": 1, "write_nj": 1})
    monkeypatch.setattr(memory, "frame_memory_energy", lambda *args: {"dynamic_energy_uj": 10})
    model = FullModel()
    result = run_agent_search(tmp_path, AgentConfig(rounds=1, proposals=1, top_k=1, mapping_budget=5),
                              model, mapper, workload=Workload(max_pes=64))
    assert result["best_evaluated_plan"]["design"] == FULL
    assert result["best_evaluated_plan"]["architecture"]["fu_profile"] == "custom"
    assert "FUs maps every tile0..tileN to its SPECIALIZED FUs" in model.calls[0]["prompt"]


@pytest.mark.parametrize("method,expected_calls", [("full_maco", 4), ("hardware_only", 4), ("single_agent", 1)])
def test_live_search_methods(monkeypatch, tmp_path, method, expected_calls):
    import chia_maco.memory as memory
    monkeypatch.setattr(memory, "evaluate_memory", lambda *args: {"read_nj": 1, "write_nj": 1})
    monkeypatch.setattr(memory, "frame_memory_energy", lambda *args: {"dynamic_energy_uj": 10})
    model = FullModel()
    result = run_agent_search(tmp_path, AgentConfig(rounds=1, proposals=1, top_k=1, mapping_budget=5),
                              model, mapper, workload=Workload(max_pes=64), method=method)
    assert result["method"] == method
    assert result["llm_calls"] == expected_calls
    design = result["best_evaluated_plan"]["design"]
    if method == "hardware_only":
        assert set(design["unroll"].values()) == {1}
        assert design["vectorize"] == "none"
    if method == "single_agent":
        assert [call["role"] for call in model.calls] == ["CGRACoDesigner"]


@pytest.mark.parametrize("change", [
    {"FUs": {"tile0": ["Add"]}}, {"config_mem": 8}, {"data_spm_kb": 30},
    {"unroll": {"window": 1}}, {"vectorize": "sometimes"},
])
def test_reject_invalid_full_maco_design(change):
    with pytest.raises(ValueError):
        validate_plan({**FULL, **change})


def test_full_maco_rejects_base_fus_in_compact_specialized_lists():
    repeated_base = {tile: list(fus) for tile, fus in FULL["FUs"].items()}
    repeated_base["tile2"].append("Shift")
    with pytest.raises(ValueError, match="only specialized FUs"):
        validate_plan({**FULL, "FUs": repeated_base})


def test_full_maco_requires_workload_fus_somewhere():
    without_mul = {tile: [fu for fu in fus if fu != "Mul"] for tile, fus in FULL["FUs"].items()}
    with pytest.raises(ValueError, match="workload operations across the array: Mul"):
        validate_plan({**FULL, "FUs": without_mul})


def test_truncated_model_json_is_retained_and_rejected():
    transport = LocalModel.__new__(LocalModel)
    transport.config, transport.model, transport.calls = AgentConfig(), "mock", []
    transport.emit = lambda *args, **kwargs: None
    response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"top_k_design":['), finish_reason="stop")], usage=None)
    transport.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: response)))
    with pytest.raises(ValueError, match="no fallback"):
        transport("CoarseGrainedJudge", "test prompt")
    assert transport.calls[0]["response"] == '{"top_k_design":['
