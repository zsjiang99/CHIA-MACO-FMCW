# MACO submission text

Paper authors: Zesong Jiang, Cheng Tan, Jeff Zhang (Arizona State University).

## Summary of project contributions

- We built a CHIA-managed MACO agent loop that evaluates compiler and CGRA choices for five FMCW radar hotspots using real LLVM/CGRA-Mapper feedback.
- We provide an executable FMCW C workload, explicit frame-cost model, deterministic 36-mapping reference search, and retained numerical-validation failures.
- In one three-round Qwen run, the agent matched the reference's 39.15-million-cycle estimate with 18 rather than 36 unique mappings, while taking longer overall; CA-CFAR accounts for 89.7% of modeled cycles.

## Artifact statement

The repository contains the CHIA/MACO integration loop, FMCW workload and mapping views, tests, archived mapper and model traces, result JSON, and a local browser demo. It documents pinned tool dependencies and distinguishes mapper-derived estimates from unverified hardware metrics.

## Abstract

We present a CHIA workflow for compiler–architecture exploration of an FMCW radar pipeline on a coarse-grained reconfigurable array. Four MACO agent roles, driven by an OpenAI-compatible Qwen3.8-27B service, propose and rank bounded array and unroll configurations using feedback from real CGRA-Mapper runs. A deterministic 36-mapping search provides a reference under the same evaluator and frame-cost model. In one three-round agent run, 12 model calls and 18 unique mappings reached the reference's best estimate of 39.15 million cycles per frame, but required more wall time. The reference shows a non-monotonic array-size tradeoff and identifies CA-CFAR as the dominant modeled stage. The artifact includes the C workload, CHIA loop, mapping evidence, agent traces, tests, and a local GUI. Cycle results are analytical estimates from mapper initiation intervals; they are not cycle-accurate simulation, physical-design measurements, or proof of candidate hardware correctness.

## Upload / URL

- PDF: `paper/paper.pdf` (four pages, IEEE two-column).
- Open-source artifact URL: https://github.com/zsjiang99/CHIA-MACO-FMCW

Human authors should review these claims against the final PDF and artifact before submission.
