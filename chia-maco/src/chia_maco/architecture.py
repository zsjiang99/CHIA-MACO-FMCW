"""CGRA-Flow-compatible parameterizable mapper topology and FU assignment."""

FU_PROFILES = ("uniform", "checkerboard", "column")
BASE_FUS = ["Add", "Br", "Cmp", "Logic", "Phi", "Ret", "Sel", "Shift"]


def architecture_config(rows, columns, profile, banks, bank_kib):
    """Model one LD/ST interface per bank, capped by west-edge PE count.

    Banks are evaluated with CACTI; mapper ports are idealized interfaces and
    do not simulate address conflicts, arbitration, or capacity spills.
    """
    ports = min(rows, banks)
    memory_tiles = [i * rows // ports * columns for i in range(ports)]
    tiles = {}
    for i in range(rows * columns):
        row, col = divmod(i, columns)
        multiply = profile == "uniform" or (profile == "checkerboard" and (row + col) % 2 == 0) or (profile == "column" and col == 0)
        fus = BASE_FUS + (["Mul"] if multiply else []) + (["Ld", "St"] if i in memory_tiles else [])
        tiles[str(i)] = {"disabled": False, "supportAllFUs": False, "supportedFUs": fus, "accessMem": i in memory_tiles}
    links = []
    for i in range(rows * columns):
        for j in (i + 1 if i % columns < columns - 1 else -1, i + columns):
            if 0 <= j < rows * columns:
                links.extend(({"srcTile": i, "dstTile": j}, {"srcTile": j, "dstTile": i}))
    return {"tiles": tiles, "links": links, "control_memory": 32,
            "memory": {"banks": banks, "bank_kib": bank_kib,
            "capacity_kib": banks * bank_kib, "interface_tiles": memory_tiles,
            "model": "ideal bank interfaces; no address-conflict or spill simulation"},
            "fu_profile": profile, "multiplier_tiles": sum("Mul" in t["supportedFUs"] for t in tiles.values()),
            "scope": "mapper operation classes; not precision-verified RTL"}
