# <img src="assets/maco-mark.svg" width="38" height="38" alt="MACO radar and CGRA icon"> MACO × CHIA

**Agent-guided CGRA co-design for FMCW radar.**

[Paper (PDF)](paper/paper.pdf) · [Quick start](#-quick-start) · [Results and logs](chia-maco/results/README.md) · [Browser demo](#-browser-demo)

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

The Fine-grained Judge predicts a winner; CHIA maps shortlisted plans that fit the budget. The reported frame estimate uses mapper II and fixed workload counts, not the agent's prediction.

## 📊 Findings

| Search | Unique mapper runs | Best estimated cycles/frame | Archived wall time |
| --- | ---: | ---: | ---: |
| Exhaustive reference | 36 | 39,154,344 | 38.71 s |
| MACO agents (12 model calls) | 18 | 39,154,344 | 210.43 s |

The agent run matched the best estimate with fewer mappings, but took longer because of model calls. Its best measured plan is **4×4 with unroll factors [4, 2, 4, 4, 1]**; CA-CFAR accounts for **89.7%** of modeled frame cycles. [Inspect the raw evidence.](chia-maco/results/README.md)

## 🚀 Quick start

Verify the archived paper results with a C compiler, `make`, and Python 3.10+:

```bash
git clone https://github.com/zsjiang99/CHIA-MACO-FMCW.git
cd CHIA-MACO-FMCW
make -C chia-maco artifact-check
```

This runs one native FMCW frame and checks the saved results. It does **not** run an LLM or CGRA-Mapper.

## ⚙️ Full reproduction

The following steps build on Quick start and run from the repository root. They require Docker and network access for installation. New runs do not overwrite the [paper's archived evidence](chia-maco/results/README.md).

### 🛠️ 1. Prepare the evaluator

Install the pinned mapper, CHIA, and this package. Expand for the setup commands.

<details>
<summary>Show setup commands</summary>

```bash
mkdir -p external
git clone https://github.com/tancheng/CGRA-Mapper.git external/CGRA-Mapper
git -C external/CGRA-Mapper checkout 5f8393acb6b3a17146806ec93a57f76f875be232
docker build -t cgramapper:v1 external/CGRA-Mapper/docker
python3.10 -m venv .venv
.venv/bin/python -m pip install 'git+https://github.com/ucb-bar/chia.git@16c35e92aaaf9511c6453bf94cd5cf589698f4e3'
.venv/bin/python -m pip install -e 'chia-maco[test]'
```

</details>

### 🧪 2. Run the mapper search

```bash
make -C chia-maco test PYTHON=../.venv/bin/python
make -C chia-maco mapper-smoke PYTHON=../.venv/bin/python
make -C chia-maco codesign-search PYTHON=../.venv/bin/python
```

`mapper-smoke` maps the five kernel views. `codesign-search` runs 36 CHIA mapping evaluations and writes `chia-maco/results/codesign_search.json`; the [reported archive](chia-maco/results/codesign_search_certified.json) is unchanged.

<details>
<summary>Recompute the summary from saved mappings (no mapper run)</summary>

```bash
.venv/bin/chia-maco summarize-search chia-maco/results/codesign_search_certified.json \
  --output chia-maco/results/my_summary.json
```

</details>

### 🤖 3. Run the MACO agents

Start an OpenAI-compatible model service, then expand the commands below. The reported run used locally served Qwen3.8-27B with NF4 double quantization; model weights and credentials are not included.

<details>
<summary>Show agent setup and run commands</summary>

```bash
git clone https://github.com/coredac/MACO.git external/MACO
git -C external/MACO checkout 31c02ce013838d89ef2a6d211acfdf639ecb178d
export MACO_AGENT_DIR="$PWD/external/MACO/agent"
export MACO_LLM_BASE_URL=http://127.0.0.1:18161/v1
export MACO_LLM_MODEL=your-served-model-id
.venv/bin/chia-maco agent-search --output-dir chia-maco/results/my_agent_run \
  --rounds 3 --mapping-budget 30 --seed 37
```

</details>

Use a new output directory. The [reported seed-37 run](chia-maco/results/agent_qwen38_27b_seed37_v3/) contains its model trace and mapper logs; a new model or sampling run may propose different designs.

## 💻 Browser demo

The GUI can display archived evidence without a model. After evaluator setup, install the GUI requirements and build the frontend (Node 20.19+):

```bash
.venv/bin/python -m pip install -r gui/requirements.txt
(cd gui/frontend && npm ci && npm run build)
bash gui/start.sh
```

Open `http://127.0.0.1:8765`, or forward port 8765 over SSH. The server binds to loopback and has no authentication; do not expose it publicly. **Run MACO exploration** starts the agent/mapper loop. RTL, synthesis, and layout are separate experimental paths requiring `cgra/neura-flow:20260114`, not prerequisites for the paper.

## 📂 Project structure

| Part | Where to look | What it contains |
| --- | --- | --- |
| 🤖 Agents | [agent_search.py](chia-maco/src/chia_maco/agent_search.py) | Four-role MACO loop and feedback history |
| ⚙️ Evaluation | [CHIA node](chia-maco/src/chia_maco/nodes.py) · [mapper](chia-maco/src/chia_maco/mapper.py) · [frame model](chia-maco/src/chia_maco/report.py) | Tool execution and frame estimate |
| 📡 Workload | [workload/](chia-maco/workload/) | Native FMCW C and mapping views |
| 📊 Evidence | [results/](chia-maco/results/) | Candidates, traces, logs, validation |
| 💻 Demo | [gui/](gui/) | Browser viewer and optional hardware-flow controls |
| 📄 Paper | [paper/](paper/) | Four-page PDF and LaTeX source |

## 🔬 What the evidence supports

- **Performance:** CGRA-Mapper reports mapping II; the full-frame cycle count is an analytical estimate, not measured FPS or energy. It omits loop setup, memory stalls, FFT bit reversal, and host–CGRA transfers. Archived wall times are not runtime guarantees.
- **Correctness:** The native smoke test is not a hardware test. The independent [NumPy comparison](chia-maco/results/validation_v1/) meets FFT and power error criteria, but exact CA-CFAR masks agree in only **2 of 6** scenes; a fresh `validate-native` exits nonzero. Mapper and component RTL tests do not certify full-frame execution.
- **Hardware:** Tile count is not synthesized area. FU/memory exploration and RTL/layout in the GUI are experimental, outside the paper's reported search. See the [implementation status](chia-maco/IMPLEMENTATION_STATUS.md).

## 📄 License and credit

Zesong Jiang, Cheng Tan, and Jeff Zhang · Arizona State University. New integration code is BSD-3-Clause licensed. Original MACO agents are fetched from a pinned [upstream checkout](https://github.com/coredac/MACO); other dependencies retain their own terms. See the [third-party notices](gui/THIRD_PARTY.md).
