from chia_maco.memory import parse_cacti


def test_parse_cgra_flow_cacti_metrics():
    result = parse_cacti("""
Access time (ns): 0.451259
Total dynamic read energy per access (nJ): 0.0141894
Total dynamic write energy per access (nJ): 0.00994142
Data array: Area (mm2): 0.231095
""")
    assert result == {"read_nj": .0141894, "write_nj": .00994142,
                      "area_mm2": .231095, "access_ns": .451259}
