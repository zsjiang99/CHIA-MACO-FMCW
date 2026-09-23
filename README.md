# <img src="assets/maco-mark.svg" width="38" height="38" alt="MACO radar and CGRA icon"> MACO × CHIA

**Agent-guided CGRA co-design for FMCW radar.**

[Paper (PDF)](paper/paper.pdf) · [Run the artifact](#-run-the-artifact) · [Results and logs](chia-maco/results/README.md) · [Browser demo](#browser-demo)

## 🧭 What this artifact explores

The FMCW range–Doppler workload uses **256 samples/chirp × 128 chirps/frame × 4 RX channels** of FP32 complex data. Its five C mapping views are window, FFT (range and Doppler), transpose, power, and CA-CFAR.

One candidate uses a **single CGRA array for all five kernels**: a 2×2, 4×4, or 6×6 array plus one compiler unroll factor per kernel. The reported objective is **minimum estimated cycles/frame**; FU mix, memory banks, and interconnect are fixed in this search.

## 🔁 Agent–tool loop

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

The Fine-grained Judge predicts a winner; CHIA maps the shortlisted plans that fit the budget. **Only mapper results**, not the agent's prediction, enter the reported frame estimate.

## 📊 Findings

| Search | Unique mapper runs | Best estimated cycles/frame | Archived wall time |
| --- | ---: | ---: | ---: |
| Exhaustive reference | 36 | 39,154,344 | 38.71 s |
| MACO agents (12 model calls) | 18 | 39,154,344 | 210.43 s |

The agent run matched the best estimate with fewer mappings, but took longer because of model calls. Its best measured plan is **4×4 with unroll factors [4, 2, 4, 4, 1]**; CA-CFAR accounts for **89.7%** of modeled frame cycles. [Inspect the raw evidence.](chia-maco/results/README.md)

## 🚀 Run the artifact

After cloning, run commands from the repository root. New runs write separate output files; they do not replace the [archived paper evidence](chia-maco/results/README.md).

### 1. Check the archive

Requires a C compiler, `make`, and Python 3.10+. This runs one native FMCW frame and checks the saved results; it does **not** run an LLM or CGRA-Mapper.

```bash
git clone https://github.com/zsjiang99/CHIA-MACO-FMCW.git
cd CHIA-MACO-FMCW
make -C chia-maco artifact-check
```

### 2. Re-run the mapper search

Requires Python 3.10, Docker, a C compiler, and network access during setup. After step 1:

```bash
mkdir -p external
git clone https://github.com/tancheng/CGRA-Mapper.git external/CGRA-Mapper
git -C external/CGRA-Mapper checkout 5f8393acb6b3a17146806ec93a57f76f875be232
docker build -t cgramapper:v1 external/CGRA-Mapper/docker
python3.10 -m venv .venv
.venv/bin/python -m pip install 'git+https://github.com/ucb-bar/chia.git@16c35e92aaaf9511c6453bf94cd5cf589698f4e3'
.venv/bin/python -m pip install -e 'chia-maco[test]'
make -C chia-maco test PYTHON=../.venv/bin/python
make -C chia-maco mapper-smoke PYTHON=../.venv/bin/python
make -C chia-maco codesign-search PYTHON=../.venv/bin/python
```

`mapper-smoke` maps the five kernel views. `codesign-search` runs the 36-mapping CHIA search and writes `chia-maco/results/codesign_search.json`, leaving the [reported archive](chia-maco/results/codesign_search_certified.json) unchanged. To recompute a summary *from saved mappings* without running the mapper:

```bash
.venv/bin/chia-maco summarize-search chia-maco/results/codesign_search_certified.json \
  --output chia-maco/results/my_summary.json
```

### 3. Re-run the MACO agents

Use the evaluator setup above and an OpenAI-compatible model service. The reported run used locally served Qwen3.8-27B with NF4 double quantization; model weights and credentials are not included.

```bash
git clone https://github.com/coredac/MACO.git external/MACO
git -C external/MACO checkout 31c02ce013838d89ef2a6d211acfdf639ecb178d
export MACO_AGENT_DIR="$PWD/external/MACO/agent"
export MACO_LLM_BASE_URL=http://127.0.0.1:18161/v1
export MACO_LLM_MODEL=your-served-model-id
.venv/bin/chia-maco agent-search --output-dir chia-maco/results/my_agent_run \
  --rounds 3 --mapping-budget 30 --seed 37
```

Use a new output directory. The [reported seed-37 run](chia-maco/results/agent_qwen38_27b_seed37_v3/) contains its model trace and mapper logs; a new model or sampling run may propose different designs.

### Browser demo

The GUI can display archived evidence without a model. With the Python environment above and Node 20.19+:

```bash
.venv/bin/python -m pip install -r gui/requirements.txt
(cd gui/frontend && npm ci && npm run build)
bash gui/start.sh
```

Open `http://127.0.0.1:8765`, or forward port 8765 over SSH. The server binds to loopback and has no authentication; do not expose it publicly. **Run MACO exploration** starts the agent/mapper loop. RTL, synthesis, and layout are separate experimental paths requiring `cgra/neura-flow:20260114`, not prerequisites for the paper.

## 📂 Repository map

| Path | Purpose |
| --- | --- |
| [`chia-maco/src/chia_maco/`](chia-maco/src/chia_maco/) | [Agent loop](chia-maco/src/chia_maco/agent_search.py), [CHIA evaluator](chia-maco/src/chia_maco/nodes.py), [mapper adapter](chia-maco/src/chia_maco/mapper.py), [frame model](chia-maco/src/chia_maco/report.py) |
| [`chia-maco/workload/`](chia-maco/workload/) | FMCW C reference and compiler-mapping views |
| [`chia-maco/results/`](chia-maco/results/) | Archived searches, raw tool evidence, and validation |
| [`gui/`](gui/) | Local browser demo and optional hardware-flow controls |
| [`paper/`](paper/) | Four-page IEEE-style paper and LaTeX source |

## 🔬 What the evidence supports

Mapping II comes from CGRA-Mapper; full-frame cycles are an **analytical estimate**, not measured FPS or energy. Tile count is not synthesized area.

The frame model excludes loop setup, memory stalls, FFT bit reversal, and host–CGRA transfers. The archived 38.71 s and 210.43 s are original-host wall times, not runtime guarantees.

The native smoke test is separate from candidate-hardware correctness. The independent [NumPy comparison](chia-maco/results/validation_v1/) passes the FFT and power criteria, but exact CA-CFAR masks agree in only **2 of 6** scenes. A fresh `validate-native` therefore exits nonzero; mapper success and component RTL tests do not certify full-frame hardware execution. FU/memory exploration and RTL/layout in the GUI are outside the paper's reported search. See the [implementation status](chia-maco/IMPLEMENTATION_STATUS.md).

## 📄 License and credit

Zesong Jiang, Cheng Tan, and Jeff Zhang · Arizona State University. New integration code is BSD-3-Clause licensed. Original MACO agents are fetched from a pinned [upstream checkout](https://github.com/coredac/MACO); other dependencies retain their own terms. See the [third-party notices](gui/THIRD_PARTY.md).
