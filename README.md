<h1 align="center"><img src="assets/maco-mark.svg" width="42" height="42" alt="MACO radar and CGRA icon"> MACO × CHIA</h1>

<p align="center"><em>Agent-guided CGRA co-design for FMCW radar</em></p>

<p align="center"><a href="paper/paper.pdf">Paper</a> · <a href="#-quick-start">Quick start</a> · <a href="chia-maco/results/README.md">Results and logs</a> · <a href="#-browser-demo">Browser demo</a></p>

---

## 🧭 What this artifact explores

The **reported paper experiment** explores one CGRA architecture shared by five FMCW kernels: **2×2, 4×4, or 6×6 arrays**, with a legal compiler unroll factor for each kernel. Functional-unit placement and memory parameters remain fixed in that comparison. CHIA maps the kernels and returns tool feedback for the next agent round. Its objective is **estimated cycles/frame**.

Live exploration uses a broader MACO design schema: **2×2–8×8 arrays, per-tile functional units, configuration memory, total scratchpad capacity, memory banks, per-kernel unroll from 1–6, and one global vectorization mode**. The user selects either **Performance** (estimated cycles/frame) or **Energy** (estimated CGRA-core + SRAM dynamic energy/frame). Every proposed design is retained in the trace; only successfully mapped designs can become the best measured result. This extension is outside the paper's reported array/unroll experiment.

The workload has **256 samples/chirp × 128 chirps/frame × 4 RX channels** of FP32 complex data. Its mapping views cover window, FFT (range and Doppler), transpose, power, and CA-CFAR.

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

The archived paper experiment evaluates the array/unroll slice of this larger design space.

| Search | Unique mapper runs | Best estimated cycles/frame | Archived wall time |
| --- | ---: | ---: | ---: |
| Exhaustive reference | 36 | 39,154,344 | 38.71 s |
| MACO agents (12 model calls) | 18 | 39,154,344 | 210.43 s |

The agent run matched the best estimate with fewer mappings, but took longer because of model calls. Its best measured plan is **4×4 with unroll factors [4, 2, 4, 4, 1]**; CA-CFAR accounts for **89.7%** of modeled frame cycles. [Inspect the raw evidence.](chia-maco/results/README.md)

## 🚀 Quick start

On Linux, verify the archived paper results with Git, a C compiler, `make`, and Python 3.10+:

```bash
git clone https://github.com/zsjiang99/CHIA-MACO-FMCW.git
cd CHIA-MACO-FMCW
make -C chia-maco artifact-check
```

This runs one native FMCW frame and checks the saved results. It does **not** run an LLM or CGRA-Mapper.

## 🧰 Environment

The following combinations are supported:

| Use | Required environment |
| --- | --- |
| Archived result check | Linux x86-64, Git, `make`, a C compiler, Python 3.10+ |
| Browser archive | The above, plus Node.js 20.19+ or 22.12+ and npm |
| Live MACO search | Python 3.10, Docker Engine, `cgramapper:v1`, the pinned MACO checkout, and an OpenAI-compatible model endpoint |
| RTL generation, verification and synthesis | The live-search environment plus `cgra/neura-flow:20260114` |
| Optional layout | The same CGRA-Flow image; layout is launched separately after synthesis |

Archive checking, Python installation, tests, and the browser build were verified in a clean **Ubuntu 22.04 x86-64** container. A pinned mapper image was also built and used for a real mapping. A complete fresh live-model-to-layout run has not been certified, so the README does not claim that result.

The Docker images contain the required LLVM/Clang and EDA tools; they are not required on the host. The CGRA-Flow image occupies about 17 GB, so allow at least 25 GB of free Docker storage. A remote model endpoint does not require a local GPU. If authentication is required, set `MACO_LLM_API_KEY` in addition to `MACO_LLM_BASE_URL` and `MACO_LLM_MODEL`.

## 📂 Project structure

| Part | Where to look | What it contains |
| --- | --- | --- |
| 🤖 Agents | [agent_search.py](chia-maco/src/chia_maco/agent_search.py) | Four-role MACO loop and feedback history |
| ⚙️ Evaluation | [CHIA node](chia-maco/src/chia_maco/nodes.py) · [mapper](chia-maco/src/chia_maco/mapper.py) · [frame model](chia-maco/src/chia_maco/report.py) · [energy model](chia-maco/src/chia_maco/energy.py) | Tool execution and measured-activity estimates |
| 📡 Workload | [workload/](chia-maco/workload/) | Native FMCW C and mapping views |
| 📊 Evidence | [results/](chia-maco/results/) | Candidates, traces, logs, validation |
| 💻 Demo | [gui/](gui/) | Browser viewer and optional hardware-flow controls |
| 📄 Paper | [paper/](paper/) | Four-page PDF and LaTeX source |

## ⚙️ Full reproduction

The following steps build on Quick start and run from the repository root. They require Docker and network access for installation. New runs do not overwrite the [paper's archived evidence](chia-maco/results/README.md).

### 1. 🛠️ Prepare the evaluator

Install the pinned mapper, CHIA, and this package.

CGRA-Mapper and its Docker image (built from the checked-out commit, not upstream's moving default branch):

```bash
mkdir -p external
git clone https://github.com/tancheng/CGRA-Mapper.git external/CGRA-Mapper
git -C external/CGRA-Mapper checkout 5f8393acb6b3a17146806ec93a57f76f875be232
docker build -t cgramapper:v1 -f chia-maco/docker/mapper.Dockerfile external/CGRA-Mapper
```

Python environment. Install the pinned CHIA checkout locally: `pip install git+...` fails because one of that commit's optional submodules is no longer fetchable.

```bash
python3.10 -m venv .venv
git clone https://github.com/ucb-bar/chia.git external/chia
git -C external/chia checkout 16c35e92aaaf9511c6453bf94cd5cf589698f4e3
.venv/bin/python -m pip install ./external/chia
.venv/bin/python -m pip install -e 'chia-maco[test]'
```

Fetch the pinned MACO agent classes before running the test suite:

```bash
git clone https://github.com/coredac/MACO.git external/MACO
git -C external/MACO checkout 31c02ce013838d89ef2a6d211acfdf639ecb178d
```

### 2. 🧪 Run the mapper search

```bash
MACO_AGENT_DIR="$PWD/external/MACO/agent" make -C chia-maco test PYTHON=../.venv/bin/python
make -C chia-maco mapper-smoke PYTHON=../.venv/bin/python
make -C chia-maco codesign-search PYTHON=../.venv/bin/python
```

`mapper-smoke` maps the five kernel views. `codesign-search` runs 36 CHIA mapping evaluations and writes `chia-maco/results/codesign_search.json`; the [reported archive](chia-maco/results/codesign_search_certified.json) is unchanged.

To regenerate only the summary from archived mappings, without running the mapper:

```bash
.venv/bin/chia-maco summarize-search chia-maco/results/codesign_search_certified.json \
  --output chia-maco/results/my_summary.json
```

### 3. 🤖 Run the MACO agents

Start an OpenAI-compatible model service. The reported run used locally served Qwen3.8-27B with NF4 double quantization; model weights and credentials are not included.

Point to your model service and run the loop:

```bash
export MACO_AGENT_DIR="$PWD/external/MACO/agent"
export MACO_LLM_BASE_URL=http://127.0.0.1:18161/v1
export MACO_LLM_MODEL=your-served-model-id
.venv/bin/chia-maco agent-search --output-dir chia-maco/results/my_agent_run \
  --rounds 3 --mapping-budget 30 --seed 37
```

Use a new output directory. The [reported seed-37 run](chia-maco/results/agent_qwen38_27b_seed37_v3/) contains its model trace and mapper logs; a new model or sampling run may propose different designs.

## 💻 Browser demo

The GUI opens directly on the frozen paper experiment without starting a model or mapper. To view the archive, you can skip Full reproduction and run these commands from the repository root:

```bash
python3.10 -m venv .venv
.venv/bin/python -m pip install -r gui/requirements.txt
(cd gui/frontend && npm ci && npm run build)
bash gui/start.sh
```

Open `http://127.0.0.1:8765/`, or forward port 8765 over SSH. Set `A3_GUI_PORT` before `bash gui/start.sh` to use another local port. The default **Paper result** tab shows the seed-37 agent trace, exhaustive reference, per-kernel mapping evidence and scope limits. Follow the [three-minute walkthrough](chia-maco/DEMO.txt). **Live exploration** (`/?mode=live`) runs architecture search, generates and verifies RTL, then synthesizes the selected design. Layout remains an explicit optional action after that flow completes.

The server binds to loopback and has no authentication; do not expose it publicly.

For architecture-aware live search, RTL generation and verification, synthesis, or optional layout, install the CGRA-Flow image:

```bash
docker pull cgra/neura-flow:20260114
```

These hardware paths are experimental and are not required to reproduce the paper's archived results.

## 🔬 What the evidence supports

- **Performance:** CGRA-Mapper reports mapping II; the full-frame cycle count is an analytical estimate, not measured FPS. It omits loop setup, memory stalls, FFT bit reversal, and host–CGRA transfers. Archived wall times are not runtime guarantees.
- **Energy:** the live objective combines scheduled compute, register/control, routed-link activity, and CACTI SRAM access energy. It is a reproducible first-order dynamic-energy estimate, not post-layout power; leakage and host transfers are excluded.
- **Correctness:** The native smoke test is not a hardware test. The independent [NumPy comparison](chia-maco/results/validation_v1/) meets FFT and power error criteria, but exact CA-CFAR masks agree in only **2 of 6** scenes; a fresh `validate-native` exits nonzero. Mapper and component RTL tests do not certify full-frame execution.
- **Hardware:** Tile count is not synthesized area. FU/memory exploration and RTL/layout in the GUI are experimental, outside the paper's reported search. See the [implementation status](chia-maco/IMPLEMENTATION_STATUS.md).

## 📄 License and credit

Zesong Jiang, Cheng Tan, and Jeff Zhang · Arizona State University. New integration code is BSD-3-Clause licensed. Original MACO agents are fetched from a pinned [upstream checkout](https://github.com/coredac/MACO); other dependencies retain their own terms. See the [third-party notices](gui/THIRD_PARTY.md).
