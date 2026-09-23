#!/usr/bin/env bash
set -euo pipefail
project_gui="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec bash "${project_gui}/../../gui/start.sh" maco
