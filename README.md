# CHIA-MACO-FMCW artifact

Public release: https://github.com/zsjiang99/CHIA-MACO-FMCW

This MACO-only repository contains the CHIA loop, FMCW C workload, compiler
mapping views, archived tool/model evidence, tests, and a local browser demo
for the four-page paper in `paper/paper.pdf`.

The reported experiment searches array size and per-kernel unroll factors with
CGRA-Mapper feedback. Memory-bank/FU exploration and RTL/layout controls are
experimental extensions in the GUI; their outputs are not substituted for the
paper's mapper-only results.

## Reproduce the reported result

Requires Python 3.10, Docker, and a C compiler. CHIA, CGRA-Mapper, and MACO
source revisions are pinned below. The original MACO agent files are fetched
from upstream rather than redistributed here because its checkout has no
explicit license.

```bash
git clone https://github.com/tancheng/CGRA-Mapper.git external/CGRA-Mapper
git -C external/CGRA-Mapper checkout 5f8393acb6b3a17146806ec93a57f76f875be232
docker build -t cgramapper:v1 external/CGRA-Mapper/docker
git clone https://github.com/coredac/MACO.git external/MACO
git -C external/MACO checkout 31c02ce013838d89ef2a6d211acfdf639ecb178d
export MACO_AGENT_DIR="$PWD/external/MACO/agent"
python3 -m venv .venv
.venv/bin/pip install 'git+https://github.com/ucb-bar/chia.git@16c35e92aaaf9511c6453bf94cd5cf589698f4e3'
.venv/bin/pip install -e 'chia-maco[test]'
make -C chia-maco smoke
make -C chia-maco test PYTHON=../.venv/bin/python
make -C chia-maco codesign-search PYTHON=../.venv/bin/python
```

The last command performs 36 real mapper evaluations; its output is separate
from the archived `chia-maco/results/codesign_search_certified.json` used in
the paper. `make -C chia-maco mapper-smoke PYTHON=../.venv/bin/python` is a smaller
five-kernel check.

## Reproduce the agent loop

The upstream MACO checkout and `MACO_AGENT_DIR` are set up above. To run a new
agent search, provide an OpenAI-compatible model endpoint:

```bash
export MACO_LLM_BASE_URL=http://127.0.0.1:18161/v1
export MACO_LLM_MODEL=your-openai-compatible-model-id
.venv/bin/chia-maco agent-search --output-dir chia-maco/results/my_run \
  --rounds 3 --mapping-budget 30 --seed 37
```

An OpenAI-compatible model server must already be running; model weights and
API credentials are not included. The paper's Qwen run is preserved at
`chia-maco/results/agent_qwen38_27b_seed37_v3/`, including its model trace,
mapper logs, and evaluated candidates. A new model/backend may produce
different proposals.

## Browser demo

The archived evidence can be viewed without running a model. In this release,
**Run MACO exploration** launches the agent/mapper loop only. RTL generation,
synthesis, and CGRA-core layout are separate optional actions and require the
`cgra/neura-flow:20260114` image. Node 20.19+ is needed to build the frontend:

```bash
.venv/bin/pip install -r gui/requirements.txt
cd gui/frontend && npm ci && npm run build && cd ../..
bash chia-maco/gui/start.sh
```

Open `http://127.0.0.1:8765` locally. For a remote server, forward port 8765
over SSH; the demo is intentionally bound to loopback and is not authenticated.

## Scope of the evidence

The reported 39.15-million-cycle frame value is a mapper-II analytical estimate,
not measured throughput. The native FMCW reference passes its smoke test, but
strict NumPy/native CFAR-mask equality passes only 2 of 6 validation scenes.
Mapper success does not certify candidate hardware correctness. The optional
RTL/layout path is under development; no area, power, FPS, or full hardware
correctness claim follows from the archived search.

`chia-maco/results/README.md` indexes the authoritative data. The repository's
BSD-3-Clause license covers the new integration code; third-party components
retain their own terms. See `gui/THIRD_PARTY.md` and
`chia-maco/src/chia_maco/vendor/maco/NOTICE.md` before redistribution.
