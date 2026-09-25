"""CGRA-Flow-compatible parameterizable mapper topology and FU assignment."""

FU_PROFILES = ("uniform", "checkerboard", "column")
BASE_FUS = ["Add", "Br", "Cmp", "Logic", "Phi", "Ret", "Sel", "Shift"]
SPECIALIZED_FUS = frozenset(("Ld", "St", "Mul", "Div", "FAdd", "FMul", "FDiv"))
FU_TYPES = frozenset((*BASE_FUS, *SPECIALIZED_FUS))
WORKLOAD_FUS = frozenset(("Ld", "St", "Mul"))


def _mesh_links(rows, columns):
    links = []
    for i in range(rows * columns):
        for j in (i + 1 if i % columns < columns - 1 else -1, i + columns):
            if 0 <= j < rows * columns:
                links.extend(({"srcTile": i, "dstTile": j}, {"srcTile": j, "dstTile": i}))
    return links


def custom_architecture(rows, columns, tile_fus, config_mem, banks, data_spm_kib):
    """Build the exact per-tile architecture proposed by MACO."""
    expected = {str(i) for i in range(rows * columns)}
    if set(tile_fus) != expected:
        raise ValueError("Per-tile FU assignment is incomplete")
    if data_spm_kib % banks:
        raise ValueError("Data SPM must divide evenly across memory banks")
    tiles = {}
    for key in sorted(expected, key=int):
        fus = list(dict.fromkeys(tile_fus[key]))
        if not fus or any(fu not in FU_TYPES for fu in fus):
            raise ValueError(f"Unsupported functional units for tile {key}")
        missing = set(BASE_FUS) - set(fus)
        if missing:
            raise ValueError(
                f"Tile {key} is missing fixed base FUs: {', '.join(sorted(missing))}"
            )
        tiles[key] = {"disabled": False, "supportAllFUs": False, "supportedFUs": fus,
                      "accessMem": "Ld" in fus or "St" in fus}
    available = set().union(*(set(tile["supportedFUs"]) for tile in tiles.values()))
    missing = WORKLOAD_FUS - available
    if missing:
        raise ValueError(
            "Custom architecture is missing workload FUs: " + ", ".join(sorted(missing))
        )
    interfaces = [int(key) for key, tile in tiles.items() if tile["accessMem"]]
    if not interfaces:
        raise ValueError("At least one tile must provide Ld or St")
    bank_kib = data_spm_kib // banks
    return {"tiles": tiles, "links": _mesh_links(rows, columns), "control_memory": config_mem,
            "memory": {"banks": banks, "bank_kib": bank_kib, "capacity_kib": data_spm_kib,
                       "interface_tiles": interfaces,
                       "model": "ideal bank interfaces; no address-conflict or spill simulation"},
            "fu_profile": "custom", "multiplier_tiles": sum(
                bool({"Mul", "FMul"}.intersection(tile["supportedFUs"])) for tile in tiles.values()),
            "scope": "mapper operation classes; not precision-verified RTL"}


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
    return {"tiles": tiles, "links": _mesh_links(rows, columns), "control_memory": 32,
            "memory": {"banks": banks, "bank_kib": bank_kib,
            "capacity_kib": banks * bank_kib, "interface_tiles": memory_tiles,
            "model": "ideal bank interfaces; no address-conflict or spill simulation"},
            "fu_profile": profile, "multiplier_tiles": sum("Mul" in t["supportedFUs"] for t in tiles.values()),
            "scope": "mapper operation classes; not precision-verified RTL"}
