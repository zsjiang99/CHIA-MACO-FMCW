# MACO submission text

Paper authors: Zesong Jiang, Cheng Tan, Jeff Zhang (Arizona State University).

## Summary of project contributions

- We built a CHIA-managed MACO agent loop that evaluates compiler and CGRA choices for five FMCW radar hotspots using real LLVM/CGRA-Mapper feedback.
- We provide an executable FMCW C workload, explicit frame-cost model, deterministic 36-mapping reference search, and retained numerical-validation failures.
- In one three-round Qwen run, the agent matched the reference's 39.15-million-cycle estimate with 18 rather than 36 unique mappings, while taking longer overall. Mapper feedback corrected an initial 6×6 preference in favor of 4×4; CA-CFAR accounts for 89.7% of modeled cycles.

## Artifact statement

The repository contains the CHIA/MACO integration loop, FMCW workload and mapping views, tests, archived mapper and model traces, result JSON, and a local browser demo that opens on the paper's frozen experiment. It documents pinned tool dependencies and distinguishes mapper-derived estimates from unverified hardware metrics.

## Abstract

We present a CHIA workflow for compiler–architecture exploration of an FMCW radar pipeline on a coarse-grained reconfigurable array. Four original MACO agent roles, driven by Qwen3.8-27B, propose and rank bounded array/unroll configurations using real mapper feedback. In one three-round run, 12 model calls and 18 unique mappings find the same 39.15-million-cycle estimate as a 36-mapping exhaustive reference, but require more wall time. Tool feedback reverses the agent's initial preference for a larger array; CA-CFAR accounts for 89.7% of the final modeled cycles. The artifact includes the C workload, agent/model traces, mapper logs, and a local GUI. Cycle results are analytical estimates from mapper initiation intervals; end-to-end CGRA correctness and physical performance remain unverified.

## Upload / URL

- PDF: `paper/paper.pdf` (four pages, IEEE two-column).
- Open-source artifact URL: https://github.com/zsjiang99/CHIA-MACO-FMCW

Human authors should review these claims against the final PDF and artifact before submission.
