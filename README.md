<h1 align="center"><img src="assets/raco-mark.svg" width="42" height="42" alt="RACO radar and CGRA icon"> RACO: Agentic CGRA Hardware/Software Co-Design for FMCW Radar with CHIA</h1>

<p align="center"><a href="paper/paper.tex">Paper source</a> · <a href="#-quick-start">Quick start</a> · <a href="chia-maco/results/README.md">Results and logs</a> · <a href="#-browser-demo">Browser demo</a></p>

---

## RACO Demonstration

The interface presents the selected CGRA architecture, FMCW kernel mappings, agent trace, generated RTL, verification status, and synthesis results.

[![RACO interface showing CGRA architecture, kernel mapping, RTL verification, and synthesis results](assets/live-flow-synthesis-passed.png)](assets/live-flow-synthesis-passed.png)

*Recorded RACO run. Cycle figures are mapper-based estimates; layout was not run.*

## 🧭 Overview

RACO explores a shared CGRA architecture and kernel-specific compiler settings for five FMCW mapping views: Window, FFT, Transpose, Power, and CA-CFAR. CHIA maps each view, and a frame model ranks complete designs by estimated CGRA cycles/frame.

The live interface also shows RTL verification and synthesis; layout is optional. These hardware steps are outside the paper's matched-budget cycle comparison.

## 🔁 Agent–tool loop

```text
┌──────────────┐   ┌──────────────┐   ┌──────────────────┐   ┌──────────────────┐
│ CGRA         │ → │ Design       │ → │ Shortlist        │ → │ Final            │
│ Co-designer  │   │ Checker      │   │ Reviewer         │   │ Reviewer         │
│ propose      │   │ repair       │   │ shortlist        │   │ predict best     │
└──────────────┘   └──────────────┘   └──────────────────┘   └─────────┬────────┘
       ↑                                                               │ shortlist
       │                                                               ▼
       │                 ┌─────────────────────────────────────────────────────────┐
       └── II + cycles ──┤ CHIA → LLVM 12 → CGRA-Mapper → frame-cycle model        │
                         │ Map shortlisted plans within the evaluation budget     │
                         └─────────────────────────────────────────────────────────┘
```

The final reviewer predicts a winner; CHIA maps shortlisted plans that fit the budget. The reported frame estimate uses mapper II and fixed workload counts, not the agent's prediction.

## 📊 Findings

The reported runs use one seed (37), the same FMCW workload and evaluator, and 10 unique kernel-mapper evaluations per method—not 10 complete CGRA designs.

| Method | Successful mappings | Best estimated cycles/frame |
| --- | ---: | ---: |
| RACO | 10/10 | **38,728,360** |
| Hardware-only | 10/10 | 42,136,232 |
| Single-agent one-shot | 9/10 | 41,448,104 |

RACO's estimate is **8.1%** below hardware-only and **6.6%** below single-agent in these recorded runs. Its two evaluated designs cost 38,728,360 and 40,202,920 cycles/frame; the selected design uses a 4×4 array, 4 × 16 KiB SRAM, and unroll factors [4, 4, 4, 4, 1]. A separate 20-evaluation run records a second design round, but its additional proposal did not improve the first-round incumbent. [Inspect the run records and raw logs.](chia-maco/results/README.md)

## 🚀 Quick start

On Linux, verify the reported mapping results with Git, a C compiler, `make`, and Python 3.10+:

```bash
git clone https://github.com/zsjiang99/RACO.git
cd RACO
make -C chia-maco artifact-check
```

This runs one native FMCW frame and checks the saved results. It does **not** run an LLM or CGRA-Mapper.

## 🧰 Environment

The following combinations are supported:

| Use | Required environment |
| --- | --- |
| Archived result check | Linux x86-64, Git, `make`, a C compiler, Python 3.10+ |
| Browser archive | The above, plus Node.js 20.19+ or 22.12+ and npm |
| Live agent search | Python 3.10, Docker Engine, `cgramapper:v1`, the pinned upstream agent checkout, and an OpenAI-compatible model endpoint |
| RTL generation, verification and synthesis | The live-search environment plus `cgra/neura-flow:20260114` |
| Optional layout | The same CGRA-Flow image; layout is launched separately after synthesis |

Archive checking, Python installation, tests, and the browser build were verified in a clean **Ubuntu 22.04 x86-64** container. A pinned mapper image was also built and used for a real mapping. A complete fresh live-model-to-layout run has not been certified, so the README does not claim that result.

The Docker images contain the required LLVM/Clang and EDA tools; they are not required on the host. The CGRA-Flow image occupies about 17 GB, so allow at least 25 GB of free Docker storage. A remote model endpoint does not require a local GPU. If authentication is required, set `RACO_LLM_API_KEY` in addition to `RACO_LLM_BASE_URL` and `RACO_LLM_MODEL`.

## 📂 Project structure

| Part | Where to look | What it contains |
| --- | --- | --- |
| 🤖 Agents | [agent_search.py](chia-maco/src/chia_maco/agent_search.py) | Four-role RACO loop and feedback history |
| ⚙️ Evaluation | [CHIA node](chia-maco/src/chia_maco/nodes.py) · [mapper](chia-maco/src/chia_maco/mapper.py) · [frame model](chia-maco/src/chia_maco/report.py) · [energy model](chia-maco/src/chia_maco/energy.py) | Tool execution and measured-activity estimates |
| 📡 Workload | [workload/](chia-maco/workload/) | Native FMCW C and mapping views |
| 📊 Evidence | [results/](chia-maco/results/) | All four runs discussed in the paper, with traces and mapper logs; earlier experiments are marked separately |
| 💻 Demo | [gui/](gui/) | Browser viewer and optional hardware-flow controls |
| 📄 Paper | [paper/](paper/) | Current LaTeX source; PDF requires the paper's missing figure and bibliography files |

## ⚙️ Run a new exploration

The following steps run the current RACO workflow from the repository root. They require Docker, a model endpoint, and network access for installation. The [recorded paper results](chia-maco/results/matched_budget_10/) remain unchanged; a new model run can produce different candidates and costs.

### 1. 🛠️ Prepare the evaluator

Install the pinned mapper, CHIA, and this package.

CGRA-Mapper and its Docker image (built from the checked-out commit, not upstream's moving default branch):

```bash
mkdir -p external
git clone https://github.com/tancheng/CGRA-Mapper.git external/CGRA-Mapper
git -C external/CGRA-Mapper checkout 5f8393acb6b3a17146806ec93a57f76f875be232
docker build -t cgramapper:v1 -f chia-maco/docker/mapper.Dockerfile external/CGRA-Mapper
docker pull cgra/neura-flow:20260114
```

Python environment. Install the pinned CHIA checkout locally: `pip install git+...` fails because one of that commit's optional submodules is no longer fetchable.

```bash
python3.10 -m venv .venv
git clone https://github.com/ucb-bar/chia.git external/chia
git -C external/chia checkout 16c35e92aaaf9511c6453bf94cd5cf589698f4e3
.venv/bin/python -m pip install ./external/chia
.venv/bin/python -m pip install -e 'chia-maco[test]'
```

Fetch the pinned upstream agent classes before running the test suite:

```bash
git clone https://github.com/coredac/MACO.git external/upstream-agents
git -C external/upstream-agents checkout 31c02ce013838d89ef2a6d211acfdf639ecb178d
```

### 2. 🧪 Check the evaluator

```bash
RACO_AGENT_DIR="$PWD/external/upstream-agents/agent" make -C chia-maco test PYTHON=../.venv/bin/python
make -C chia-maco mapper-smoke PYTHON=../.venv/bin/python
```

`mapper-smoke` maps the five kernel views. The separate `codesign-search` command in the package is an earlier array/unroll study, not the paper's budget-matched comparison.

### 3. 🤖 Start the RACO workflow

Start an OpenAI-compatible model service that permits at least 4096 completion tokens. The recorded runs used locally served Qwen3.8-27B with NF4 double quantization; model weights and credentials are not included. Then launch the browser workflow:

```bash
export RACO_AGENT_DIR="$PWD/external/upstream-agents/agent"
export RACO_LLM_BASE_URL=http://127.0.0.1:18161/v1
export RACO_LLM_MODEL=your-served-model-id
.venv/bin/python -m pip install -r gui/requirements.txt
(cd gui/frontend && npm ci && npm run build)
bash gui/start.sh
```

Open `http://127.0.0.1:8765/?mode=live`, select Multi-agent, Hardware only, or Single agent, and run one exploration at a time. Each one-round run has a budget of 10 unique kernel-mapper evaluations. The standalone `agent-search` CLI without a workload uses the earlier study; it does **not** reproduce the current comparison. For exact paper numbers without rerunning the model, use `make -C chia-maco artifact-check` and inspect the saved results.

## 💻 Browser demo

The GUI opens on an earlier archived experiment without starting a model or mapper. To view it, you can skip the live setup and run these commands from the repository root:

```bash
python3.10 -m venv .venv
.venv/bin/python -m pip install -r gui/requirements.txt
(cd gui/frontend && npm ci && npm run build)
bash gui/start.sh
```

Open `http://127.0.0.1:8765/`, or forward port 8765 over SSH. Set `A3_GUI_PORT` before `bash gui/start.sh` to use another local port. **Earlier demo** shows the older search, not the paper's 38.73M result; the [paper run records](chia-maco/results/matched_budget_10/) contain that result and both baselines. **Live exploration** (`/?mode=live`) runs architecture search, generates and verifies RTL, then synthesizes the selected design. Layout remains an explicit optional action after that flow completes.

The server binds to loopback and has no authentication; do not expose it publicly.

Live RTL generation, verification, synthesis, and optional layout use the CGRA-Flow image installed above. These hardware paths are experimental and are not required to check the paper's saved mapping results.

## 🔬 What the evidence supports

- **Performance:** CGRA-Mapper reports mapping II; the full-frame cycle count is an analytical estimate, not measured FPS. It omits loop setup, memory stalls, FFT bit reversal, and host–CGRA transfers. Archived wall times are not runtime guarantees.
- **Energy:** the live objective combines scheduled compute, register/control, routed-link activity, and CACTI SRAM access energy. It is a reproducible first-order dynamic-energy estimate, not post-layout power; leakage and host transfers are excluded.
- **Correctness:** The native smoke test is not a hardware test. The independent [NumPy comparison](chia-maco/results/validation_v1/) meets FFT and power error criteria, but exact CA-CFAR masks agree in only **2 of 6** scenes; a fresh `validate-native` exits nonzero. Mapper and component RTL tests do not certify full-frame execution.
- **Hardware:** Tile count is not synthesized area. FU/memory exploration and RTL/layout in the GUI are experimental, outside the paper's reported search. See the [implementation status](chia-maco/IMPLEMENTATION_STATUS.md).

## 📄 License and credit

Zesong Jiang, Cheng Tan, and Jeff Zhang · Arizona State University. New integration code is BSD-3-Clause licensed. The agent modules are fetched from a pinned [upstream checkout](https://github.com/coredac/MACO); other dependencies retain their own terms. See the [third-party notices](gui/THIRD_PARTY.md).
