from chia_maco.cgra_flow import architecture_yaml
from chia_maco.architecture import architecture_config


def test_maco_architecture_exports_west_only_cgra_flow_memory():
    architecture = architecture_config(4, 4, "column", 8, 8)
    result = architecture_yaml({"design": {"tile_size": "4x4"}, "architecture": architecture})
    assert result["cgra_defaults"]["rows"] == 4
    assert result["maco_memory"] == {"banks": 8, "bank_kib": 8}
    assert len(result["tile_overrides"]) == 16
    assert len(result["link_overrides"]) == 6
    assert "mem" in result["tile_overrides"][0]["fu_types"]
    assert "mem" not in result["tile_overrides"][1]["fu_types"]
