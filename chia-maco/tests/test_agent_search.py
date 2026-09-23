import json
from types import SimpleNamespace

import pytest

from chia_maco.agent_search import AgentConfig, LocalModel, OriginalAgents, run_agent_search, validate_plan
from chia_maco.schema import MappingResult


P1 = {"tile_size": "4x4", "unroll_factors": [2, 2, 2, 2, 1], "reasoning": "Balanced plan"}
P2 = {"tile_size": "6x6", "unroll_factors": [4, 2, 4, 4, 1], "reasoning": "Wider plan"}


class Model:
    model = "mock-for-unit-tests-only"

    def __init__(self, invalid=False):
        self.calls = []
        self.invalid = invalid

    def __call__(self, role, prompt, temperature):
        values = {
            "CGRACoDesigner": [P1, P2],
            "CGRAFixer": {"fixed_arch_json": [P1, P2]},
            "CoarseGrainedJudge": {"top_k_design": [P1, P2]},
            "FineGrainedJudge": {"best_design": {**P1, "tile_size": "2x2"} if self.invalid else P1},
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


def test_truncated_model_json_is_retained_and_rejected():
    transport = LocalModel.__new__(LocalModel)
    transport.config, transport.model, transport.calls = AgentConfig(), "mock", []
    transport.emit = lambda *args, **kwargs: None
    response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"top_k_design":['), finish_reason="stop")], usage=None)
    transport.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: response)))
    with pytest.raises(ValueError, match="no fallback"):
        transport("CoarseGrainedJudge", "test prompt")
    assert transport.calls[0]["response"] == '{"top_k_design":['
