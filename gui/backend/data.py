"""Read the authoritative artifact files without altering them."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ARCHIVES = {
    "maco": ROOT / "chia-maco/results/codesign_search_certified.json",
}


def read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def array_model(size: int) -> dict:
    # These three upstream model files are reused byte-for-byte. No Tk/RTL imports.
    sys.path.insert(0, str(ROOT / "gui/vendor/cgra_flow"))
    from common.cgra_param_tile import ParamTile
    tiles = [ParamTile(y * size + x, x, y, x * 70, y * 70, 52, 52)
             for y in range(size) for x in range(size)]
    return {
        "source": "CGRA-Flow ParamTile", "rows": size, "columns": size,
        "note": "Array geometry only; not a per-tile mapping or utilization trace.",
        "tiles": [{"id": t.ID, "x": t.dimX, "y": t.dimY} for t in tiles],
    }
