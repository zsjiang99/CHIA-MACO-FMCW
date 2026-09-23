from types import SimpleNamespace

import pytest

from chia_maco import energy


def test_frame_energy_includes_core_routes_control_and_sram(monkeypatch, tmp_path):
    schedule = {"available": True,
                "placements": [{"instruction": "%1 = fmul float %a, %b"},
                               {"instruction": "%2 = fadd float %1, %c"}],
                "dfg_edges": [{"source": 1, "target": 2}],
                "links": [{"source": 0, "target": 1, "cycle": 0}]}
    monkeypatch.setattr(energy, "parse_schedule", lambda *_: schedule)
    log = tmp_path / "mapping.log"
    log.write_text("retained evidence")
    mapped = [SimpleNamespace(candidate={"kernel": "fmcw_window", "rows": 2, "columns": 2},
                              to_dict=lambda: {"success": True})]
    estimate = {"estimated_cycles": 50, "breakdown": {"fmcw_window": {"scheduled_loop_groups": 10}}}
    result = energy.frame_dynamic_energy(mapped, [log], estimate, {"dynamic_energy_uj": 2.0})
    assert result["total_dynamic_energy_uj"] > 2.0
    assert result["core_dynamic_energy_uj"] == pytest.approx(sum(
        result["components_uj"][name] for name in ("compute", "register_and_control", "interconnect")))
    assert result["components_uj"]["sram"] == 2.0
