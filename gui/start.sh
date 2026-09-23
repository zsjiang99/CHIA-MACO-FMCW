#!/usr/bin/env bash
set -euo pipefail
gui_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "${gui_dir}/.."
if [[ "${1:-maco}" != "maco" ]]; then
  echo 'This release contains only MACO' >&2
  exit 1
fi
if [[ ! -f "${gui_dir}/../chia-maco/gui/dist/index.html" ]]; then
  echo 'Build the frontend first: cd gui/frontend && npm ci && npm run build' >&2
  exit 1
fi
export PYTHONPATH="${gui_dir}${PYTHONPATH:+:${PYTHONPATH}}"
exec "${A3_PYTHON:-${gui_dir}/../.venv/bin/python}" -m uvicorn backend.app:app \
  --host 127.0.0.1 --port "${A3_GUI_PORT:-8765}"
