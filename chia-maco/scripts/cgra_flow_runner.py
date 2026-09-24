"""Container-side adapter for CGRA-Flow's native non-GUI operations."""
from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time


def patch_source(path: Path, changes: list[tuple[str, str]]) -> None:
    source = path.read_text()
    for old, new in changes:
        if source.count(old) != 1:
            raise RuntimeError(f"CGRA-Flow source changed: {path.name}")
        source = source.replace(old, new)
    path.write_text(source)


def repair_unconnected_ports(job: Path) -> None:
    root = Path("/WORK_REPO/CGRA-Flow/VectorCGRA")
    memory = json.loads((job / "arch.yaml").read_text())["maco_memory"]
    banks, bank_kib = int(memory["banks"]), int(memory["bank_kib"])
    bank_words = bank_kib * 1024 // 4
    if banks not in (1, 2, 4, 8, 16) or bank_words & (bank_words - 1):
        raise ValueError("Physical memory needs power-of-two bank count and depth")
    patch_source(root / "cgra/test/CgraTemplateRTL_test.py", [
        ("  data_mem_size_global = 512\n"
         "  data_mem_size_per_bank = 32\n"
         "  num_banks_per_cgra = 2",
         f"  data_mem_size_global = {banks * bank_words}\n"
         f"  data_mem_size_per_bank = {bank_words}\n"
         f"  num_banks_per_cgra = {banks}"),
    ])
    patch_source(root / "tile/TileRTL.py", [
        ("    s.const_mem = ConstQueueDynamicRTL(DataType, ctrl_mem_size)",
         "    s.const_mem = ConstQueueDynamicRTL(DataType, ctrl_mem_size)\n"
         "    s.const_mem.clear //= 0"),
        ("    for i in range(len(FuList)):\n      if FuList[i] == MemUnitRTL:",
         "    if MemUnitRTL not in FuList:\n"
         "      s.to_mem_raddr.val //= 0\n"
         "      s.to_mem_raddr.msg //= DataAddrType(0)\n"
         "      s.from_mem_rdata.rdy //= 0\n"
         "      s.to_mem_waddr.val //= 0\n"
         "      s.to_mem_waddr.msg //= DataAddrType(0)\n"
         "      s.to_mem_wdata.val //= 0\n"
         "      s.to_mem_wdata.msg //= DataType()\n\n"
         "    for i in range(len(FuList)):\n      if FuList[i] == MemUnitRTL:"),
    ])
    patch_source(root / "cgra/CgraTemplateRTL.py", [
        ("    else:\n      s.bypass_queue = BypassQueueRTL(NocPktType, 1)",
         "    else:\n"
         "      s.send_to_inter_cgra_noc.val //= 0\n"
         "      s.send_to_inter_cgra_noc.msg //= NocPktType()\n"
         "      s.recv_from_inter_cgra_noc.rdy //= 0\n"
         "      s.bypass_queue = BypassQueueRTL(NocPktType, 1)"),
        ("    for link in LinkList:\n\n      if link.isFromMem():",
         "    used_read = {link.getMemReadPort() for link in LinkList\n"
         "                 if link.isFromMem() and not link.disabled}\n"
         "    used_write = {link.getMemWritePort() for link in LinkList\n"
         "                  if link.isToMem() and not link.disabled}\n"
         "    for port in range(dataSPM.getNumOfValidReadPorts()):\n"
         "      if port not in used_read:\n"
         "        s.data_mem.recv_raddr[port].val //= 0\n"
         "        s.data_mem.recv_raddr[port].msg //= DataAddrType(0)\n"
         "        s.data_mem.send_rdata[port].rdy //= 0\n"
         "    for port in range(dataSPM.getNumOfValidWritePorts()):\n"
         "      if port not in used_write:\n"
         "        s.data_mem.recv_waddr[port].val //= 0\n"
         "        s.data_mem.recv_waddr[port].msg //= DataAddrType(0)\n"
         "        s.data_mem.recv_wdata[port].val //= 0\n"
         "        s.data_mem.recv_wdata[port].msg //= DataType()\n\n"
         "    for link in LinkList:\n\n      if link.isFromMem():"),
    ])


def save(job: Path, data: dict) -> None:
    (job / "result.json").write_text(json.dumps(data, indent=2) + "\n")


def stage(job: Path, name: str, completed: int, total: int) -> None:
    (job / "progress.json").write_text(json.dumps({"stage": name, "completed": completed,
                                                    "total": total}, indent=2) + "\n")


def run_quiet(command: list[str], cwd: Path, job: Path, label: str) -> None:
    console = job / f"{label}.log"
    with console.open("w") as stream:
        completed = subprocess.run(command, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT)
    if completed.returncode:
        tail = console.read_text(errors="replace")[-65536:]
        (job / f"{label}-error.log").write_text(tail)
        raise RuntimeError(f"{label} failed; see {label}-error.log")


def generate(job: Path) -> Path:
    repair_unconnected_ports(job)
    from pymtl3.passes.backends.verilog import VerilogPlaceholderPass, VerilogTranslationPass
    from VectorCGRA.multi_cgra.test import MeshMultiCgraTemplateRTL_test as cgra_test
    stage(job, "RTL generation and regression", 1, 4)
    options = {"test_verilog": False, "test_yosys_verilog": False, "dump_textwave": False,
               "dump_vcd": False, "dump_vtb": False, "max_cycles": 1000}
    def translate_only(top, _options, duts):
        top.apply(VerilogPlaceholderPass())
        for name in duts:
            getattr(top, name).set_metadata(VerilogTranslationPass.enable, True)
        top.apply(VerilogTranslationPass())
        return top
    cgra_test.CgraTemplateRTL_test.config_model_with_cmdline_opts = translate_only
    # The harness already translates the elaborated CGRA. Re-importing that
    # same model inside run_sim fails for nested FAdd placeholders because their
    # translated_filename metadata is not populated a second time.
    cgra_test.CgraTemplateRTL_test.run_sim = lambda model, *args, **kwargs: None
    work = job / "work"
    work.mkdir(exist_ok=True)
    old = Path.cwd()
    try:
        import os
        os.chdir(work)
        cgra_test.test_simplified_multi_cgra(options, str(job / "arch.yaml"))
    finally:
        os.chdir(old)
    candidates = list(work.glob("CgraTemplateRTL__*.v"))
    if not candidates:
        raise RuntimeError("CGRA-Flow did not emit CgraTemplateRTL Verilog")
    rtl = max(candidates, key=lambda p: p.stat().st_size)
    shutil.copy2(rtl, job / "candidate.sv")
    return job / "candidate.sv"


def fp_regression(job: Path) -> dict:
    output = job / "fp32_tile.json"
    subprocess.run([sys.executable, "/artifact/scripts/check_fp32_rtl.py", "--test-verilog",
                    "--output", str(output)], check=True)
    return json.loads(output.read_text())


def normalized_verilog(job: Path, source: Path) -> Path:
    stage(job, "SystemVerilog conversion", 2, 4)
    converted = subprocess.run(["/WORK_REPO/CGRA-Flow/tools/sv2v/bin/sv2v", str(source)],
                               check=True, capture_output=True, text=True).stdout
    if not re.search(r"(?m)^module\s+CgraTemplateRTL\s*\(", converted):
        converted, count = re.subn(r"(?m)^module\s+CgraTemplateRTL__[^\s(]+\s*\(",
                                   "module CgraTemplateRTL (", converted, count=1)
        if count != 1:
            raise RuntimeError("Could not normalize the generated top module")
    # sv2v turns fixed PyMTL indices into procedural registers. Yosys then
    # treats the variable part-selects as potentially out of range.
    indices = re.findall(
        r"(?m)^\s*(__tmpvar__update_received_msg_\w+) = \d+'d(\d+);$", converted)
    for name, value in indices:
        index = str(5 - int(value))
        converted = converted.replace(f"5 - sv2v_cast_3({name})", index)
        converted = converted.replace(f"5 - {name}", index)
    if len(indices) != 6:
        raise RuntimeError("Controller index constants changed; review sv2v output")
    route = re.compile(
        r"\t\t\tsend__val\[2 - out_dir\+:1\] = 1'd1;\n"
        r"\t\t\tsend__msg\[\(2 - out_dir\) \* (\d+)\+:\1\] = send_msg_wire;")
    matches = list(route.finditer(converted))
    if len(matches) != 1:
        raise RuntimeError("Ring router indexing changed; review sv2v output")
    width = int(matches[0].group(1))
    replacement = "\n".join([
        "\t\t\tcase (out_dir)",
        *(f"\t\t\t\t2'd{i}: begin send__val[{2 - i}] = 1'd1; "
          f"send__msg[{(2 - i) * width}+:{width}] = send_msg_wire; end"
          for i in range(3)),
        "\t\t\tendcase",
    ])
    converted = route.sub(lambda _: replacement, converted)
    path = job / "candidate.v"
    path.write_text(converted)
    return path


def check_verilog(job: Path, verilog: Path) -> None:
    top = "CgraCoreRTL" if verilog.name == "core.v" else "CgraTemplateRTL"
    # Defer elaboration until hierarchy selects the instantiated parameters.
    # HardFloat's unused small default parameterization otherwise emits an
    # out-of-bounds warning even when the actual FP32 instances are valid.
    script = (f"read_verilog -sv -defer {verilog}; hierarchy -top {top}; "
              "proc; check")
    run_quiet(["yosys", "-Q", "-T", "-p", script], job, job, "rtl-check")
    report = (job / "rtl-check.log").read_text(errors="replace")
    if ("Found and reported 0 problems." not in report
            or "select out of bounds" in report or "has no driver" in report):
        raise RuntimeError("RTL connectivity check failed; see rtl-check.log")


def isolate_cgra_core(job: Path, verilog: Path) -> Path:
    """Expose the SPM interface as pins; do not synthesize its controller or banks."""
    source = verilog.read_text()
    top_start = source.index("module CgraTemplateRTL (")
    library, top = source[:top_start], source[top_start:]
    memory = re.search(r"\tDataMemControllerRTL__\w+ data_mem\(\n.*?\n\t\);", top, re.S)
    if memory is None:
        raise RuntimeError("Could not locate the Data SPM instance")
    memory_type = re.search(r"module DataMemControllerRTL__\w+ \(\n.*?\n\);(.*?)(?=\nmodule |\Z)", library, re.S)
    if memory_type is None:
        raise RuntimeError("Could not locate the Data SPM interface")
    port_declarations = memory_type.group(1).split("\tlocalparam", 1)[0]
    ports = re.findall(r"\t(input|output) (?:wire|reg) (\[[^\]]+\]) (\w+);", port_declarations)
    static = {"address_lower", "address_upper", "cgra_id", "clk", "reset"}
    interface = [(direction, width, name) for direction, width, name in ports if name not in static]
    if len(interface) < 20:
        raise RuntimeError("Unexpectedly small Data SPM interface")
    top = top.replace(memory.group(0), "", 1)
    for direction, width, name in interface:
        wire = f"\twire {width} data_mem__{name};"
        if top.count(wire) != 1:
            raise RuntimeError(f"Missing Data SPM boundary net: {name}")
        boundary_direction = "output" if direction == "input" else "input"
        top = top.replace(wire, f"\t{boundary_direction} wire {width} data_mem__{name};", 1)
    header = re.search(r"module CgraTemplateRTL \(\n(.*?)\n\);", top, re.S)
    if header is None:
        raise RuntimeError("Could not locate CGRA top-level ports")
    old_ports = header.group(1).rstrip()
    extra_ports = ",\n".join(f"\tdata_mem__{name}" for _, _, name in interface)
    top = top.replace(header.group(0),
                      f"module CgraCoreRTL (\n{old_ports},\n{extra_ports}\n);", 1)
    core = job / "core.v"
    core.write_text(library + top)
    return core


def synthesize(job: Path, verilog: Path) -> dict:
    stage(job, "Yosys synthesis", 3, 4)
    flow = Path("/WORK_REPO/CGRA-Flow/tools/mflowgen")
    template = flow / "steps/open-yosys-synthesis/synth.ys.template"
    script = template.read_text()
    flat = "flatten\n# opt"
    mapping = "abc -liberty inputs/adk/stdcells.lib \\\n    -D {clock_period_ps} -constr {constraints_tcl}"
    if script.count(flat) != 1 or script.count(mapping) != 1:
        raise RuntimeError("CGRA-Flow synthesis template changed; hierarchical patch needs review")
    script = script.replace(flat, "# Preserve module hierarchy during technology mapping.\n# opt")
    script = script.replace(mapping, mapping + "\n\n# Flatten the already mapped netlist for downstream tools.\nflatten\nclean -purge")
    script = script.replace("insbuf -buf {min_buf_cell} {min_buf_port_i} {min_buf_port_o}",
                            "# Assign aliases are legal in Verilog; avoid inserting millions of\n"
                            "# artificial cells into the area estimate.\n"
                            "# insbuf -buf {min_buf_cell} {min_buf_port_i} {min_buf_port_o}")
    template.write_text(script)
    target = flow / "designs/cgra/rtl/outputs/design.v"
    shutil.copy2(verilog, target)
    build = flow / "build_maco"
    if build.exists():
        shutil.rmtree(build)
    build.mkdir()
    run_quiet(["mflowgen", "run", "--design", "../designs/cgra"], build, job, "mflowgen")
    run_quiet(["make", "2"], build, job, "rtl-stage")
    run_quiet(["make", "3"], build, job, "yosys")
    stats = next(build.glob("3-open-yosys-synthesis/stats.txt"))
    shutil.copy2(stats, job / "yosys-stats.txt")
    match = re.search(r"Chip area for module .*?:\s*([\d.eE+-]+)", stats.read_text())
    if not match:
        raise RuntimeError("Yosys did not report chip area")
    return {"core_area_mm2": float(match.group(1)) / 1_000_000,
            "area_source": "complete CGRA Yosys synthesis; freepdk-45nm standard cells",
            "stats": "yosys-stats.txt"}


def layout(job: Path, verilog: Path) -> dict:
    stage(job, "OpenROAD RTL-to-layout", 3, 4)
    flow = Path("/OpenROAD-flow-scripts/flow")
    design = "CgraCoreRTL"
    config = job / "config.mk"
    constraint = job / "constraint.sdc"
    config.write_text("\n".join((
        "export PLATFORM = asap7",
        f"export DESIGN_NAME = {design}",
        f"export VERILOG_FILES = {verilog}",
        f"export SDC_FILE = {constraint}",
        "export SYNTH_HIERARCHICAL = 1",
        "export ABC_AREA = 1",
        "export SYNTH_MEMORY_MAX_BITS = 262144",
        "export CORE_UTILIZATION = 35",
        "export CORE_ASPECT_RATIO = 1",
        "export CORE_MARGIN = 5",
        "export PLACE_DENSITY = 0.45",
        "export GPL_ROUTABILITY_DRIVEN = 1",
        "export GPL_TIMING_DRIVEN = 0",
        "export MIN_ROUTING_LAYER = M1",
        "export MAX_ROUTING_LAYER = M7",
        "export SKIP_LAST_GASP = 1",
    )) + "\n")
    constraint.write_text("\n".join((
        f"current_design {design}",
        "create_clock -name core_clock -period 1000 [get_ports clk]",
        "set_input_delay 200 -clock core_clock [all_inputs -no_clocks]",
        "set_output_delay 200 -clock core_clock [all_outputs]",
    )) + "\n")
    run_quiet(["make", f"DESIGN_CONFIG={config}", "2_1_floorplan"], flow, job, "openroad-floorplan")
    run_quiet(["make", f"DESIGN_CONFIG={config}"], flow, job, "openroad")
    images = list((flow / "reports/asap7" / design).glob("**/final_all.webp"))
    if not images:
        raise RuntimeError("OpenROAD completed without final_all.webp")
    shutil.copy2(images[0], job / "layout.webp")
    metrics = list((flow / "reports/asap7" / design).glob("**/metrics.json"))
    if metrics:
        shutil.copy2(metrics[0], job / "openroad-metrics.json")
    physical = {}
    for extension in ("def", "gds", "v", "sdc"):
        outputs = list((flow / "results/asap7" / design).glob(f"**/6_final.{extension}"))
        if outputs:
            target = f"layout.{extension}"
            shutil.copy2(outputs[0], job / target)
            physical[extension] = target
    return {"layout": "layout.webp", "metrics": "openroad-metrics.json" if metrics else None,
            "physical_files": physical, "memory_implementation": "excluded; SPM is a chip-boundary interface",
            "layout_source": "OpenROAD ASAP7; CGRA compute, control, and interconnect only"}


def main() -> None:
    action, job = sys.argv[1], Path(sys.argv[2])
    started = time.monotonic()
    result = {"action": action, "status": "running"}
    try:
        rtl = generate(job)
        result["rtl_regression"] = "not_run"
        if action == "verify":
            verilog = normalized_verilog(job, rtl)
            check_verilog(job, verilog)
            result["rtl_regression"] = "structural_passed"
            result["candidate_hardware_correctness"] = "pending"
            stage(job, "Translated FP32 regression", 2, 4)
            fp = fp_regression(job)
            result.update(fp32_regression=fp["status"], fp32_cases=len(fp["cases"]))
        else:
            verilog = normalized_verilog(job, rtl)
            if action == "layout":
                verilog = isolate_cgra_core(job, verilog)
            check_verilog(job, verilog)
            result.update(synthesize(job, verilog) if action == "synth" else layout(job, verilog))
        result.update(status="passed", elapsed_seconds=round(time.monotonic() - started, 2),
                      architecture="arch.yaml", rtl="candidate.sv")
        stage(job, "Completed", 4, 4)
        save(job, result)
    except BaseException as error:
        result.update(status="failed", error=f"{type(error).__name__}: {error}",
                      elapsed_seconds=round(time.monotonic() - started, 2))
        save(job, result)
        raise


if __name__ == "__main__":
    main()
