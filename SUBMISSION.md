# RACO submission text

Paper authors: Zesong Jiang, Cheng Tan, Jeff Zhang (Arizona State University).

## Summary of project contributions

- RACO combines HW/SW candidate generation, design correction, multi-judge selection, and CHIA-based mapping feedback for one CGRA shared by five FMCW kernel views.
- Its executable workload and frame-cost model combine mapper-reported initiation intervals with scheduled loop counts, while retaining complete agent traces and raw mapper logs.
- Under 10 unique kernel-mapper evaluations per method, RACO reaches 38.73 million estimated cycles/frame, versus 42.14 million for HW-only and 41.45 million for single-agent one-shot.

## Artifact statement

The repository contains the RACO workflow, five FMCW mapping views, CHIA evaluator, tests, and result JSON, agent traces, and raw mapper logs for all three budget-matched runs and the separate two-round run discussed in the paper. The browser's default Earlier demo tab shows an older search; the paper runs are available under `chia-maco/results/matched_budget_10/`.

## Abstract

We present RACO, an agentic CGRA hardware/software co-design workflow for FMCW radar built with CHIA. It evaluates one architecture shared by five kernel views and uses mapper-reported initiation intervals to estimate steady-state frame cost. Under a common budget of 10 unique kernel-mapper evaluations, RACO achieves 38.73 million estimated cycles/frame, compared with 42.14 million for a hardware-only ablation and 41.45 million for a single-agent one-shot baseline. The artifact includes the executable workflow, decision traces, and raw mapper logs. These cycle counts are analytical estimates, not measured end-to-end execution time.

## Upload / URL

- Current manuscript source: `paper/paper.tex`; its referenced figures and `ref.bib` must be supplied before rebuilding the PDF.
- Artifact URL: https://github.com/zsjiang99/RACO.

Human authors should review these claims against the final PDF and artifact before submission.
