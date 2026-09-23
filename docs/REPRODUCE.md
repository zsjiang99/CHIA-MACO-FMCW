# Reproduce the MACO FMCW experiment

Run commands from the repository root. The [results index](../chia-maco/results/README.md)
identifies the archived data used by the paper; new runs write separate files.

## 1. Fast check: no Docker or model

Requires a C compiler, `make`, and Python 3.10 or newer.

```bash
git clone https://github.com/zsjiang99/CHIA-MACO-FMCW.git
cd CHIA-MACO-FMCW
make -C chia-maco artifact-check
```

This compiles and runs a synthetic-target FMCW frame, then checks the saved
reference, agent, and validation JSON against the paper's reported numbers.
It reads archived results; it does **not** run CGRA-Mapper or an LLM.

## 2. Run the compiler/CGRA search

Requires Python 3.10, Docker access, a C compiler, and network access during
setup. The commands below start from a fresh clone; skip the first two lines
if the repository is already checked out.

```bash
git clone https://github.com/zsjiang99/CHIA-MACO-FMCW.git
cd CHIA-MACO-FMCW
mkdir -p external
git clone https://github.com/tancheng/CGRA-Mapper.git external/CGRA-Mapper
git -C external/CGRA-Mapper checkout 5f8393acb6b3a17146806ec93a57f76f875be232
docker build -t cgramapper:v1 external/CGRA-Mapper/docker
git clone https://github.com/coredac/MACO.git external/MACO
git -C external/MACO checkout 31c02ce013838d89ef2a6d211acfdf639ecb178d
export MACO_AGENT_DIR="$PWD/external/MACO/agent"
python3.10 -m venv .venv
.venv/bin/python -m pip install 'git+https://github.com/ucb-bar/chia.git@16c35e92aaaf9511c6453bf94cd5cf589698f4e3'
.venv/bin/python -m pip install -e 'chia-maco[test]'
make -C chia-maco test PYTHON=../.venv/bin/python
make -C chia-maco mapper-smoke PYTHON=../.venv/bin/python
make -C chia-maco codesign-search PYTHON=../.venv/bin/python
```

`mapper-smoke` maps the five hotspots. `codesign-search` runs the 36-point
CHIA search and writes `chia-maco/results/codesign_search.json`; it does not
overwrite the [certified archive](../chia-maco/results/codesign_search_certified.json).
The archived run took 38.71 s on its original host, not a time guarantee for
other machines. Its frame-cost model excludes loop setup, memory stalls, FFT
bit reversal, and host–CGRA transfers.

To recompute the search summary from saved raw mapping records rather than
rerun the mapper:

```bash
.venv/bin/chia-maco summarize-search chia-maco/results/codesign_search_certified.json \
  --output chia-maco/results/my_summary.json
```

## 3. Optional: run the MACO agents

Use the setup above and provide an OpenAI-compatible model service. The
original run used a locally served Qwen3.8-27B raw base model with NF4 double
quantization; model weights and credentials are not included.

```bash
export MACO_LLM_BASE_URL=http://127.0.0.1:18161/v1
export MACO_LLM_MODEL=your-served-model-id
.venv/bin/chia-maco agent-search --output-dir chia-maco/results/my_agent_run \
  --rounds 3 --mapping-budget 30 --seed 37
```

Choose a new output directory. The reported seed-37 run is archived at
[`agent_qwen38_27b_seed37_v3/`](../chia-maco/results/agent_qwen38_27b_seed37_v3/);
other model services or sampling runs may yield different proposals. Its 18
unique mappings took 210.43 s end-to-end on the original host.

## Browser demo

The demo can open archived evidence without starting a model. It needs the
Python environment above, plus Node 20.19 or newer for frontend build:

```bash
.venv/bin/python -m pip install -r gui/requirements.txt
(cd gui/frontend && npm ci && npm run build)
bash gui/start.sh
```

Open `http://127.0.0.1:8765`. On a remote server, forward port 8765 over SSH.
The server binds to loopback and has no authentication; do not expose it
directly to the public internet. **Run MACO exploration** starts the agent and
mapper loop only. RTL, synthesis, and layout buttons are separate experimental
paths requiring `cgra/neura-flow:20260114`, not prerequisites for the paper.

## Validation scope

`make smoke` checks one synthetic target. The independent NumPy comparison is
saved in [`validation_v1/`](../chia-maco/results/validation_v1/): FFT and power
stages meet their numerical error criterion, while exact CA-CFAR masks match
in only 2 of 6 scenes. A fresh `validate-native` run returns nonzero when
those strict failures remain; this is expected, not a passed hardware test.
Mapper success and component RTL tests do not certify full-frame execution.
