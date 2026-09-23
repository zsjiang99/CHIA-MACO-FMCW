# <img src="assets/maco-mark.svg" width="38" height="38" alt="MACO radar and CGRA icon"> MACO × CHIA

**Agent-guided CGRA co-design for FMCW radar.**

[Paper (PDF)](paper/paper.pdf) · [Reproduce](docs/REPRODUCE.md) · [Results and logs](chia-maco/results/README.md) · [Browser demo](docs/REPRODUCE.md#browser-demo)

## 🧭 Overview

The FMCW range–Doppler workload uses **256 samples/chirp × 128 chirps/frame × 4 RX channels** of FP32 complex data. Its five C mapping views are window, FFT (range and Doppler), transpose, power, and CA-CFAR.

```text
┌──────────────┐   ┌──────────────┐   ┌──────────────────┐   ┌──────────────────┐
│ CGRA         │ → │ CGRA         │ → │ Coarse-grained   │ → │ Fine-grained     │
│ Co-designer  │   │ Fixer        │   │ Judge            │   │ Judge            │
│ propose      │   │ repair       │   │ shortlist        │   │ predict best     │
└──────────────┘   └──────────────┘   └──────────────────┘   └─────────┬────────┘
       ↑                                                               │ shortlist
       │                                                               ▼
       │                 ┌─────────────────────────────────────────────────────────┐
       └── II + cycles ──┤ CHIA → LLVM 12 → CGRA-Mapper → frame-cycle model        │
                         │ Map shortlisted plans within the evaluation budget     │
                         └─────────────────────────────────────────────────────────┘
```

## 🚀 Quick start

Check the native workload and archived paper results; no Docker or LLM is needed:

```bash
git clone https://github.com/zsjiang99/CHIA-MACO-FMCW.git
cd CHIA-MACO-FMCW
make -C chia-maco artifact-check
```

For fresh mapper/agent runs or the browser demo, follow the [reproduction guide](docs/REPRODUCE.md).

## 📊 Result

| Search | Unique mapper runs | Best estimated cycles/frame | Archived wall time |
| --- | ---: | ---: | ---: |
| Exhaustive reference | 36 | 39,154,344 | 38.71 s |
| MACO agents (12 model calls) | 18 | 39,154,344 | 210.43 s |

MACO used fewer mapper runs but more wall time. Frame cycles are estimated from mapper initiation intervals, not measured throughput. [Inspect the raw evidence.](chia-maco/results/README.md)

## 📂 Repository

| Path | Purpose |
| --- | --- |
| [`chia-maco/src/chia_maco/`](chia-maco/src/chia_maco/) | [Agent loop](chia-maco/src/chia_maco/agent_search.py), [CHIA evaluator](chia-maco/src/chia_maco/nodes.py), [mapper adapter](chia-maco/src/chia_maco/mapper.py), [frame model](chia-maco/src/chia_maco/report.py) |
| [`chia-maco/workload/`](chia-maco/workload/) | FMCW C reference and compiler-mapping views |
| [`chia-maco/results/`](chia-maco/results/) | Archived searches, raw tool evidence, and validation |
| [`gui/`](gui/) | Local browser demo and optional hardware-flow controls |
| [`paper/`](paper/) | Four-page IEEE-style paper and LaTeX source |

## 🔬 Evidence boundary

The paper's search varies **array size and five unroll factors**. FU placement, memory banking, RTL, and layout are experimental GUI extensions, not part of the reported search.

Mapper success does not certify candidate-hardware correctness. The native smoke test is separate, and exact NumPy/native CA-CFAR mask agreement holds in only **2 of 6** scenes. These results do not establish measured FPS, full-CGRA area, or total energy. See the [implementation status](chia-maco/IMPLEMENTATION_STATUS.md).

## 📄 License and credit

Zesong Jiang, Cheng Tan, and Jeff Zhang · Arizona State University. New integration code is BSD-3-Clause licensed. Original MACO agents are fetched from a pinned [upstream checkout](https://github.com/coredac/MACO); other dependencies retain their own terms. See the [third-party notices](gui/THIRD_PARTY.md).
