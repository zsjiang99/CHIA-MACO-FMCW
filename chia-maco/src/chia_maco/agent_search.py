"""MACO's four original LLM agents driving bounded CHIA mapper evaluations.

The original prompts and classes are reused, with an explicit evaluator contract
and injectable transport. ECE is adapted from MACO's decaying-epsilon driver.
DC/PPA scoring and confidence-based tool skipping are deliberately NOT claimed.
"""
from __future__ import annotations

from contextlib import redirect_stdout
from dataclasses import dataclass, asdict
import hashlib
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import random
import subprocess
import time
from typing import Callable

from .report import estimate_frame_cycles
from .schema import CoDesignCandidate, MappingResult, KERNEL_LOOPS
from .search import KERNEL_UNROLL_FACTORS, summarize_search
from .workload import Workload
from .architecture import FU_PROFILES, architecture_config

UPSTREAM_COMMIT = "31c02ce013838d89ef2a6d211acfdf639ecb178d"
KERNELS = list(KERNEL_LOOPS)
CONTRACT = """
FMCW EVALUATOR CONTRACT (overrides generic design examples and criteria above):
Optimize minimum estimated whole-frame cycles, NOT PPA or raw II alone.
A design has ONLY these keys: tile_size, unroll_factors, reasoning.
tile_size is one of "2x2", "4x4", "6x6".
unroll_factors is exactly five integers, ordered as
[window, FFT, transpose, power, CFAR]. Legal values respectively are
[[1,2,4],[1,2],[1,2,4],[1,2,4],[1]].
reasoning: a brief design rationale of at most 18 words.
All other architecture settings are fixed: mapper FU/interconnect template,
control memory 32, registers 8, bypass 4, vectorization none.
Do NOT return FUs, config_mem, data_spm_kb, vectorize, or unroll_factor:
these generic upstream fields are NOT tunable in this experiment.
Example design: {"tile_size":"2x2","unroll_factors":[1,1,1,1,1],"reasoning":"Compact scalar starting point."}
Whole-frame cost is sum(scheduled_groups(kernel,unroll) * measured_II).
Groups are rounded PER loop invocation, especially for short FFT stages.
No DFG operation histogram is supplied initially; do not invent measurements.
Coarse/Fine judges must select EXACT input designs, not invent or modify them.
Keep the role's JSON envelope (list / fixed_arch_json / top_k_design / best_design).
The top-level "reason" field, if present, MUST be at most 10 words.
Do NOT explain calculations or repeat measured history in the output.
Return compact JSON only, no markdown or text outside JSON. Keep output under 350 tokens.
"""


@dataclass(frozen=True)
class AgentConfig:
    rounds: int = 3
    proposals: int = 2
    top_k: int = 2
    mapping_budget: int = 30
    seed: int = 37
    epsilon_0: float = 0.9
    gamma: float = 0.95
    temperature: float = 0.2
    max_tokens: int = 384
    timeout: float = 180

    def validate(self):
        if not 1 <= self.rounds <= 6 or not 1 <= self.proposals <= 3:
            raise ValueError("rounds must be 1..6 and proposals 1..3")
        if not 1 <= self.top_k <= self.proposals or not 5 <= self.mapping_budget <= 36:
            raise ValueError("invalid shortlist or mapper budget")


def save(path: Path, value):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    tmp.replace(path)


def validate_plan(plan: dict) -> dict:
    if not isinstance(plan, dict):
        raise ValueError("design must be an object")
    if set(plan) - {"tile_size", "unroll_factors", "reasoning", "fu_profile", "memory_banks", "bank_kib"}:
        raise ValueError("unsupported design fields; no unmeasured hardware knobs allowed")
    if plan.get("tile_size") not in ("2x2", "4x4", "6x6"):
        raise ValueError("tile_size must be 2x2, 4x4, or 6x6")
    factors = plan.get("unroll_factors")
    if not isinstance(factors, list) or len(factors) != 5:
        raise ValueError("unroll_factors must contain five entries")
    for k, u in zip(KERNELS, factors):
        if type(u) is not int or u not in KERNEL_UNROLL_FACTORS[k]:
            raise ValueError(f"unsupported unroll for {k}: {u}")
    if not isinstance(plan.get("reasoning", ""), str):
        raise ValueError("reasoning must be text")
    extended = {"fu_profile", "memory_banks", "bank_kib"}
    if extended.intersection(plan):
        if not extended.issubset(plan) or plan["fu_profile"] not in FU_PROFILES:
            raise ValueError("Provide a supported FU profile, memory banks and bank capacity")
        if type(plan["memory_banks"]) is not int or plan["memory_banks"] not in (1, 2, 4, 8):
            raise ValueError("memory_banks must be 1, 2, 4 or 8")
        if type(plan["bank_kib"]) is not int or plan["bank_kib"] not in (4, 8, 16, 32, 64):
            raise ValueError("bank_kib must be 4, 8, 16, 32 or 64")
    return plan


def plan_key(plan):
    validate_plan(plan)
    base = plan["tile_size"] + ":" + ",".join(map(str, plan["unroll_factors"]))
    return base + (f":{plan['fu_profile']}:{plan['memory_banks']}:{plan['bank_kib']}" if "fu_profile" in plan else "")


def candidates_for(plan, workload=None):
    validate_plan(plan)
    size = int(plan["tile_size"].split("x")[0])
    w = workload or Workload()
    return [CoDesignCandidate(kernel=k, rows=size, columns=size, unroll_factor=u,
                             range_bins=w.samples, doppler_bins=w.chirps, rx_channels=w.rx,
                             fu_profile=plan.get("fu_profile", "legacy"), memory_banks=plan.get("memory_banks", 0),
                             bank_kib=plan.get("bank_kib", 16))
            for k, u in zip(KERNELS, plan["unroll_factors"])]


def mapping_key(candidate):
    return json.dumps(candidate.to_dict(), sort_keys=True)


class LocalModel:
    """OpenAI-compatible transport; never serializes credentials or substitutes answers."""
    def __init__(self, config: AgentConfig, emit: Callable):
        from openai import OpenAI
        self.config, self.emit = config, emit
        self.model = os.environ.get("MACO_LLM_MODEL", "harp-raw-base")
        self.base_url = os.environ.get("MACO_LLM_BASE_URL", "http://127.0.0.1:18161/v1")
        self.client = OpenAI(base_url=self.base_url, api_key=os.environ.get("MACO_LLM_API_KEY", "local"),
                             timeout=config.timeout, max_retries=0)
        self.calls = []
        self.identity = {"served_model": self.model, "verification": "not available"}
        # Only probe loopback health; do not send credentials to a second service.
        from urllib.parse import urlparse
        parsed = urlparse(self.base_url)
        if parsed.hostname in ("127.0.0.1", "localhost"):
            import httpx
            try:
                health = httpx.get(f"{parsed.scheme}://{parsed.netloc}/healthz", timeout=5).json()
                self.identity.update({k: health[k] for k in ("model_path", "quantization", "service", "ready") if k in health})
                self.identity["verification"] = "local serving health response"
            except (httpx.HTTPError, ValueError):
                pass

    def __call__(self, role, prompt, temperature=0.2):
        self.emit("agent_started", role=role)
        start = time.monotonic()
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": "You are a MACO CGRA co-design agent. Follow the final FMCW evaluator contract exactly."},
                          {"role": "user", "content": prompt}],
                temperature=temperature, max_tokens=self.config.max_tokens, seed=self.config.seed)
        except Exception as exc:
            # Error messages can contain endpoint information; store only class/status.
            record = {"role": role, "success": False, "error_type": type(exc).__name__,
                      "status_code": getattr(exc, "status_code", None), "latency_seconds": time.monotonic() - start}
            self.calls.append(record)
            self.emit("agent_failed", **record)
            raise RuntimeError(f"{role} model call failed: {type(exc).__name__}") from None
        content = response.choices[0].message.content or ""
        usage = response.usage.model_dump() if response.usage else {}
        record = {"role": role, "success": True, "model": self.model,
                  "prompt": prompt, "response": content, "usage": usage,
                  "latency_seconds": time.monotonic() - start,
                  "finish_reason": response.choices[0].finish_reason}
        self.calls.append(record)
        self.emit("agent_returned", role=role, usage=usage, latency_seconds=record["latency_seconds"])
        # Validate strict JSON independently of the original permissive regex parsers.
        text = content.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        try:
            json.loads(text)
        except (ValueError, TypeError):
            raise ValueError(f"{role} did not return valid JSON; no fallback candidate was substituted")
        return text


class OriginalAgents:
    """Loads the original four modules independently; injects transport, not decisions."""
    ROLES = [("cgra_codesigner", "CGRACoDesigner"), ("cgra_fixer", "CGRAFixer"),
             ("coarse_grained_judge", "CoarseGrainedJudge"), ("fine_grained_judge", "FineGrainedJudge")]

    def __init__(self, model_call, config, context, contract=CONTRACT):
        self.agents, self.hashes = {}, {}
        root = Path(os.environ["MACO_AGENT_DIR"]) if os.environ.get("MACO_AGENT_DIR") else Path(__file__).parent / "vendor/maco"
        for module_name, role in self.ROLES:
            path = root / f"{module_name}.py"
            if not path.is_file():
                raise FileNotFoundError(f"MACO agent module not found: {path}; set MACO_AGENT_DIR")
            self.hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
            spec = importlib.util.spec_from_file_location(f"maco_reused_{module_name}_{id(self)}", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            def call(model, prompt, temperature=0.7, role_name=role):
                return model_call(role_name, prompt + "\n" + context() + "\n" + contract, config.temperature)
            module.call_model = call
            if module_name == "cgra_fixer":
                def reports(designs):
                    out = []
                    for i, design in enumerate(designs):
                        try:
                            validate_plan(design)
                            issues = []
                        except ValueError as error:
                            issues = [str(error)]
                        out.append({"design_index": i, "valid": not issues, "issues": issues})
                    return out
                module.validate_design_list = reports
            self.agents[role] = getattr(module, role)(model=getattr(model_call, "model", "test"))

    def invoke(self, role, method, **kwargs):
        # Upstream prints responses. Durable traces below are the public interface.
        with redirect_stdout(io.StringIO()):
            return getattr(self.agents[role], method)(**kwargs)


def run_agent_search(output: Path, config: AgentConfig | None = None,
                     model_call=None, evaluate=None, progress_callback=None, workload: Workload | None = None) -> dict:
    config = config or AgentConfig(max_tokens=768 if workload else 384)
    config.validate()
    if workload:
        workload.validate()
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    if (output / "agent_trace.json").exists():
        raise ValueError("Choose a new output directory; existing agent traces are never overwritten")
    (output / "mapper_logs").mkdir(exist_ok=True)
    started = time.monotonic()
    adapter_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    events, rounds, raw_results, cache, history = [], [], [], {}, []
    transport = model_call
    phase = {"round": 0}
    current = {}
    result = {}
    memory_cache = {}
    log_paths = {}

    def checkpoint():
        usage = [c.get("usage", {}) for c in getattr(transport, "calls", [])]
        state = {"policy": "maco_llm_agents", "round": phase["round"], "rounds_total": config.rounds,
                 "workload": workload.to_dict() if workload else None,
                 "model_identity": getattr(transport, "identity", {}),
                 "adapter_sha256": adapter_hash,
                 "completed": len(raw_results), "total": config.mapping_budget,
                 "events": events, "rounds": rounds, "raw_results": [r.to_dict() for r in raw_results],
                 "llm_calls": len(getattr(transport, "calls", [])),
                 "prompt_tokens": sum(u.get("prompt_tokens", 0) for u in usage),
                 "completion_tokens": sum(u.get("completion_tokens", 0) for u in usage),
                 "elapsed_seconds": time.monotonic() - started}
        save(output / "progress.json", state)
        save(output / "agent_trace.json", {**state, "llm_trace": getattr(transport, "calls", [])})
        if progress_callback:
            progress_callback(state)

    def emit(kind, **payload):
        events.append({"sequence": len(events) + 1, "round": phase["round"], "kind": kind, **payload})
        checkpoint()

    if transport is None:
        transport = LocalModel(config, emit)
    # Only current-run measured feedback goes into these prompts. No baseline archive.
    source = (Path(__file__).resolve().parents[2] / "workload/fmcw_mapping.c").read_text()
    def context():
        return "Current run context:\n" + json.dumps(current, separators=(",", ":"))
    contract = CONTRACT
    if workload:
        contract = CONTRACT.replace("A design has ONLY these keys: tile_size, unroll_factors, reasoning.",
            "Each design MUST have: tile_size, unroll_factors, reasoning, fu_profile, memory_banks, bank_kib.")
        start, end = contract.index("All other architecture settings"), contract.index("Whole-frame cost")
        contract = contract[:start] + """fu_profile: uniform (Mul on every PE), checkerboard (Mul on alternating PEs),
column (Mul on west-column PEs). Add/control operations remain on every PE.
memory_banks: 1,2,4,8; bank_kib: 4,8,16,32,64. Mesh interconnect fixed.
LD/ST interfaces are min(memory_banks, array rows), placed on the west edge.
Bank conflict/arbitration/spill timing is NOT modeled. CACTI estimates SRAM at
45nm, 1 read + 1 write port per bank. SPM energy excludes PE/interconnect/leakage.
Total PE count must not exceed workload.max_pes. Read workload in current context.
For cycles minimize estimated_cycles; for spm_energy minimize memory.dynamic_energy_uj,
using cycles as tie breaker. Do not invent unavailable area, FPS or total energy.
""" + contract[end:]
        contract = contract.replace("Optimize minimum estimated whole-frame cycles, NOT PPA or raw II alone.",
                                    "Optimize workload.objective using mandatory tool evaluations.")
        contract = contract.replace("under 350 tokens", "under 700 tokens")
    agents = OriginalAgents(transport, config, context, contract)
    def cost(measurement):
        return (measurement.get("memory", {}).get("dynamic_energy_uj") if workload and workload.objective == "spm_energy"
                else measurement["frame_estimate"].get("estimated_cycles"))
    random_source = random.Random(config.seed)
    confidence = 0.0
    ray_started = False
    try:
        if evaluate is None:
            import ray
            from chia.base.ChiaFunction import get
            from .nodes import evaluate_candidate
            if not ray.is_initialized():
                ray.init(include_dashboard=False, num_cpus=2, resources={"cgra_mapper": 1})
                ray_started = True
            def evaluate(candidate, log_path):
                return MappingResult.from_dict(get(evaluate_candidate.chia_remote(candidate.to_dict(), str(log_path))))
        emit("run_started", source_commit=UPSTREAM_COMMIT, config=asdict(config), model=getattr(transport, "model", "test"))
        for iteration in range(1, config.rounds + 1):
            phase["round"] = iteration
            epsilon = config.epsilon_0 * config.gamma ** iteration
            mode = "explore" if random_source.random() < epsilon else "exploit"
            current = {"iteration": iteration, "mode": mode, "epsilon": epsilon,
                       "workload": workload.to_dict() if workload else Workload().to_dict(),
                       "measured_history": history, "remaining_mapping_budget": config.mapping_budget - len(raw_results),
                       "already_evaluated_plan_keys": sorted({plan_key(h["design"]) for h in history}),
                       "instructions": "Propose distinct new full-frame plans. Learn from measured failures and costs. Do not repeat evaluated full plans."}
            emit("round_started", mode=mode, epsilon=epsilon)
            common = {"kernel": "FMCW full frame: window, FFT, transpose, power, CA-CFAR",
                      "DFG_node_counts": {}, "max_independent_ops_per_cycle": "unknown until extraction",
                      "vectorizable_ops": [], "optimization_goal": "performance"}
            proposals = agents.invoke("CGRACoDesigner", "design", **common, N=config.proposals,
                                      extra_prompt="Source mapping views:\n" + source,
                                      extra_prompt2=f"ECE mode: {mode}. Propose {config.proposals} distinct full-frame designs.")
            if not isinstance(proposals, list) or not 1 <= len(proposals) <= config.proposals:
                raise ValueError("Co-designer returned no proposals; no random fallback")
            emit("proposed", role="CGRACoDesigner", designs=proposals)
            repaired = agents.invoke("CGRAFixer", "repair", candidates=proposals, **common)
            if not isinstance(repaired, list) or not 1 <= len(repaired) <= config.proposals:
                raise ValueError("Fixer returned an invalid candidate list")
            valid, seen = [], set()
            for plan in repaired:
                try:
                    key = plan_key(plan)
                    if workload and ("fu_profile" not in plan or int(plan["tile_size"].split("x")[0]) ** 2 > workload.max_pes):
                        raise ValueError("Candidate lacks architecture settings or exceeds the workload PE limit")
                    if key not in seen:
                        valid.append(plan)
                        seen.add(key)
                except ValueError as exc:
                    emit("candidate_rejected", design=plan, reason=str(exc))
            if not valid:
                raise ValueError("Fixer produced no executable bounded designs")
            emit("repaired", role="CGRAFixer", designs=valid)
            top = agents.invoke("CoarseGrainedJudge", "judge", candidate_designs=valid,
                                optimization_goal="performance", top_k=min(config.top_k, len(valid)))
            valid_by_key = {plan_key(p): p for p in valid}
            if not isinstance(top, list) or not top or len(top) > config.top_k:
                raise ValueError("Coarse judge returned an invalid shortlist")
            if any(plan_key(p) not in valid_by_key for p in top) or len({plan_key(p) for p in top}) != len(top):
                raise ValueError("Coarse judge changed or duplicated a design")
            top = [valid_by_key[plan_key(p)] for p in top]
            emit("shortlisted", role="CoarseGrainedJudge", designs=top)
            prediction = agents.invoke("FineGrainedJudge", "select_best", topk_designs=top,
                                       optimization_goal="performance", feedback=json.dumps(history))
            if plan_key(prediction) not in {plan_key(p) for p in top}:
                raise ValueError("Fine judge selected a design outside the shortlist")
            emit("predicted", role="FineGrainedJudge", design=prediction)
            measurements = []
            for plan in top:
                candidates = candidates_for(plan, workload)
                missing = sum(mapping_key(c) not in cache for c in candidates)
                if len(raw_results) + missing > config.mapping_budget:
                    emit("budget_skipped", design=plan, new_evaluations_required=missing)
                    continue
                mapped = []
                for candidate in candidates:
                    key = mapping_key(candidate)
                    if key not in cache:
                        emit("evaluation_started", candidate=candidate.to_dict())
                        log_paths[key] = output / "mapper_logs" / f"mapping_{len(raw_results):03d}.log"
                        value = evaluate(candidate, log_paths[key])
                        cache[key] = value
                        raw_results.append(value)
                        emit("evaluation_finished", candidate=candidate.to_dict(), success=value.success,
                             mapping_ii=value.mapping_ii, error=value.error)
                    else:
                        emit("cache_hit", candidate=candidate.to_dict())
                    mapped.append(cache[key])
                measured = {"design": plan, "frame_estimate": estimate_frame_cycles(mapped, workload),
                            "evaluations_so_far": len(raw_results), "round": iteration}
                if workload:
                    from .memory import evaluate_memory, frame_memory_energy
                    size = candidates[0].rows
                    measured["architecture"] = architecture_config(size, size, plan["fu_profile"], plan["memory_banks"], plan["bank_kib"])
                    save(output / f"architecture_{len(history):03d}.json", measured["architecture"])
                    if measured["frame_estimate"]["valid"]:
                        memory_key = (plan["memory_banks"], plan["bank_kib"])
                        emit("memory_evaluation_started", banks=memory_key[0], bank_kib=memory_key[1])
                        try:
                            if memory_key not in memory_cache:
                                memory_cache[memory_key] = evaluate_memory(*memory_key, output / f"memory_{memory_key[0]}x{memory_key[1]}")
                            measured["memory"] = frame_memory_energy(mapped, [log_paths[mapping_key(c)] for c in candidates],
                                                                     measured["frame_estimate"], memory_cache[memory_key])
                        except (ValueError, OSError, subprocess.SubprocessError) as exc:
                            measured["memory"] = {"error": str(exc), "dynamic_energy_uj": None}
                            emit("memory_evaluation_failed", error=str(exc))
                measurements.append(measured)
                history.append(measured)
                emit("design_measured", **measured)
            feasible = [m for m in measurements if m["frame_estimate"]["valid"] and cost(m) is not None]
            winner = min(feasible, key=lambda m: (cost(m), m["frame_estimate"]["estimated_cycles"])) if feasible else None
            predicted_measurement = next((m for m in feasible if plan_key(m["design"]) == plan_key(prediction)), None)
            agreement = None
            if winner and predicted_measurement:
                best_cost = cost(winner)
                regret = (cost(predicted_measurement) - best_cost) / best_cost
                agreement = math.exp(-regret / 0.1)
                confidence = 0.3 * agreement + 0.7 * confidence
            record = {"iteration": iteration, "mode": mode, "epsilon": epsilon,
                      "proposals": proposals, "repaired": valid, "shortlist": top,
                      "llm_choice": prediction, "measured_winner": winner,
                      "confidence": confidence, "agreement": agreement,
                      "tool_validation": "mandatory; confidence never substitutes for measurements"}
            rounds.append(record)
            emit("feedback", winner=winner, confidence=confidence, agreement=agreement)
            if len(raw_results) >= config.mapping_budget:
                break
        summary = (dict(execution="chia", evaluations=len(raw_results), successful_mappings=sum(r.success for r in raw_results),
                        raw_results=[r.to_dict() for r in raw_results], architectures=[], elapsed_seconds=time.monotonic()-started)
                   if workload else summarize_search(raw_results, "chia", time.monotonic() - started))
        feasible = [h for h in history if h["frame_estimate"]["valid"] and cost(h) is not None]
        winner = min(feasible, key=lambda h: (cost(h), h["frame_estimate"]["estimated_cycles"])) if feasible else None
        result = {**summary, "policy": "maco_llm_agents", "config": asdict(config),
                  "workload": workload.to_dict() if workload else None,
                  "model": getattr(transport, "model", "test"), "model_identity": getattr(transport, "identity", {"verification": "injected test transport"}),
                  "adapter_sha256": adapter_hash,
                  "source_commit": UPSTREAM_COMMIT, "agent_source_sha256": agents.hashes,
                  "rounds": rounds, "best_evaluated_plan": winner, "history": history,
                  "llm_calls": len(getattr(transport, "calls", [])),
                  "llm_usage": {field: sum(c.get("usage", {}).get(field, 0) for c in getattr(transport, "calls", []))
                                for field in ("prompt_tokens", "completion_tokens", "total_tokens")},
                  "monetary_cost": None, "cost_note": "Local inference; no monetary rate assumed. Token counts and latency recorded.",
                  "limitations": ["bounded mapper search; no full-frame RTL or total-CGRA energy evidence",
                                  "confidence formula adapted to cycle regret; no tool skipping",
                                  "architecture aggregates may combine measured per-kernel settings",
                                  "best_evaluated_plan identifies an actually evaluated whole-frame plan"]}
        save(output / "result.json", result)
        emit("run_finished", best_evaluated_plan=winner)
        return result
    except Exception as exc:
        emit("run_failed", error=str(exc))
        raise
    finally:
        if ray_started:
            import ray
            ray.shutdown()
