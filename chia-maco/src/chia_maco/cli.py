"""Small command-line interface used by smoke tests and artifact scripts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .mapper import MapperEvaluator
from .report import estimate_frame_cycles
from .schema import CoDesignCandidate, KERNEL_LOOPS


def _emit(payload: object, output: str | None = None) -> None:
    serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if output:
        destination = Path(output)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(serialized, encoding="utf-8")
    print(serialized, end="")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="chia-maco")
    subparsers = parser.add_subparsers(dest="command", required=True)
    bridge = subparsers.add_parser("export-rtl-opcodes", help="restore FP32 opcodes from retained LLVM/mapping evidence (not execution)")
    for name in ("artifacts", "log", "mapping", "output-dir"):
        bridge.add_argument("--" + name, type=Path, required=True)
    validation = subparsers.add_parser("validate-native", help="compare native FMCW against independent NumPy reference (not RTL)")
    validation.add_argument("--output-dir", type=Path, required=True)
    agent = subparsers.add_parser("agent-search", help="run original MACO LLM agents with CHIA mapper feedback")
    agent.add_argument("--output-dir", type=Path, required=True)
    agent.add_argument("--rounds", type=int, default=3)
    agent.add_argument("--mapping-budget", type=int, default=30)
    agent.add_argument("--seed", type=int, default=37)
    evaluate = subparsers.add_parser("evaluate", help="map one FMCW kernel")
    evaluate.add_argument("kernel")
    evaluate.add_argument("--rows", type=int, default=4)
    evaluate.add_argument("--columns", type=int, default=4)
    evaluate.add_argument("--unroll", type=int, default=1)
    evaluate.add_argument(
        "--arch-vectorization",
        choices=("none", "interleaved", "all"),
        default="none",
    )
    evaluate.add_argument("--compiler-vectorize", action="store_true")
    evaluate.add_argument("--output")
    evaluate.add_argument("--raw-log")
    evaluate.add_argument("--artifacts", type=Path, help="retain compiler and mapper output in a new directory")
    evaluate_all = subparsers.add_parser(
        "evaluate-all", help="map every FMCW hotspot on the reference CGRA"
    )
    evaluate_all.add_argument("--output")
    reference = subparsers.add_parser(
        "reference-run",
        help="map all hotspots and emit the nominal frame-level estimate",
    )
    reference.add_argument("--output", default="results/reference_4x4.json")
    chia_smoke = subparsers.add_parser(
        "chia-smoke", help="run one mapper evaluation through a CHIA node"
    )
    chia_smoke.add_argument("--output")
    search = subparsers.add_parser(
        "codesign-search",
        help="search bounded compiler and CGRA choices through CHIA",
    )
    search.add_argument("--local", action="store_true")
    search.add_argument("--output", default="results/codesign_search.json")
    summarize = subparsers.add_parser(
        "summarize-search", help="recompute a search summary from saved raw results"
    )
    summarize.add_argument("input")
    summarize.add_argument("--output")
    return parser


def main() -> None:
    arguments = build_parser().parse_args()
    if arguments.command == "export-rtl-opcodes":
        from .rtl_bridge import export_bridge
        _emit(export_bridge(arguments.artifacts, arguments.log, arguments.mapping, arguments.output_dir))
        return
    if arguments.command == "validate-native":
        from .validation import run_validation
        result = run_validation(arguments.output_dir)
        _emit({"status": result["status"], "output": str(arguments.output_dir),
               "cases": [{k: r[k] for k in ("scene", "status", "detection_mismatches")} for r in result["cases"]]})
        raise SystemExit(0 if result["status"] == "passed" else 1)
    if arguments.command == "agent-search":
        from .agent_search import AgentConfig, run_agent_search
        result = run_agent_search(arguments.output_dir, AgentConfig(rounds=arguments.rounds, mapping_budget=arguments.mapping_budget, seed=arguments.seed))
        _emit({"output_dir": str(arguments.output_dir), "policy": result["policy"],
               "evaluations": result["evaluations"], "llm_calls": result["llm_calls"],
               "best_evaluated_plan": result["best_evaluated_plan"]})
        raise SystemExit(0 if result["best_evaluated_plan"] else 1)
    if arguments.command == "evaluate":
        candidate = CoDesignCandidate(
            kernel=arguments.kernel,
            rows=arguments.rows,
            columns=arguments.columns,
            unroll_factor=arguments.unroll,
            compiler_vectorize=arguments.compiler_vectorize,
            architecture_vectorization=arguments.arch_vectorization,
        )
        result = MapperEvaluator().evaluate(
            candidate,
            raw_log_path=Path(arguments.raw_log) if arguments.raw_log else None,
            artifact_dir=arguments.artifacts,
        )
        _emit(result.to_dict(), arguments.output)
        raise SystemExit(0 if result.success else 1)

    if arguments.command == "evaluate-all":
        evaluator = MapperEvaluator()
        results = [
            evaluator.evaluate(CoDesignCandidate(kernel=kernel)).to_dict()
            for kernel in KERNEL_LOOPS
        ]
        _emit(results, arguments.output)
        raise SystemExit(0 if all(result["success"] for result in results) else 1)

    if arguments.command == "reference-run":
        evaluator = MapperEvaluator()
        mapping_results = [
            evaluator.evaluate(CoDesignCandidate(kernel=kernel))
            for kernel in KERNEL_LOOPS
        ]
        payload = {
            "configuration": "reference_4x4",
            "mapping_results": [result.to_dict() for result in mapping_results],
            "frame_estimate": estimate_frame_cycles(mapping_results),
        }
        _emit(payload, arguments.output)
        raise SystemExit(0 if payload["frame_estimate"]["valid"] else 1)

    if arguments.command == "chia-smoke":
        from .loop import run_reference_candidate

        result = run_reference_candidate()
        _emit(result, arguments.output)
        raise SystemExit(0 if result["success"] else 1)

    if arguments.command == "codesign-search":
        from .search import run_search

        result = run_search(use_chia=not arguments.local)
        _emit(result, arguments.output)
        raise SystemExit(
            0 if any(item["all_kernels_feasible"] for item in result["architectures"])
            else 1
        )

    if arguments.command == "summarize-search":
        from .search import summarize_search
        from .schema import MappingResult

        saved = json.loads(Path(arguments.input).read_text(encoding="utf-8"))
        results = [MappingResult.from_dict(value) for value in saved["raw_results"]]
        result = summarize_search(
            results,
            saved.get("execution", "saved"),
            float(saved.get("elapsed_seconds", 0.0)),
        )
        _emit(result, arguments.output)
        raise SystemExit(0)


if __name__ == "__main__":
    main()
