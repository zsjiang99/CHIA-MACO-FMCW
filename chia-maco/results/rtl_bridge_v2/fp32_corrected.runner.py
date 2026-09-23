"""Bit-exact FP32 FU regression in the pinned Neura image; not a CGRA executor."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

import numpy as np
from pymtl3 import Component, connect, mk_bits
from pymtl3.stdlib.test_utils import run_sim
from VectorCGRA.fu.float.FpAddRTL import FpAddRTL
from VectorCGRA.fu.float.FpMulRTL import FpMulRTL
from VectorCGRA.lib.basic.val_rdy.SourceRTL import SourceRTL
from VectorCGRA.lib.basic.val_rdy.SinkRTL import SinkRTL
from VectorCGRA.lib.messages import mk_data, mk_ctrl
from VectorCGRA.lib.opt_type import OPT_FADD, OPT_FSUB, OPT_FMUL

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "rtl"))
from fp32 import Fp32AddRTL, Fp32MulRTL


class Harness(Component):
    def construct(s, unit, opcode, a, b, expected, duplicate=False):
        Data, Ctrl = mk_data(32, 1), mk_ctrl(2, 1)
        bits = lambda x: x.view(np.uint32).tolist()
        s.a = SourceRTL(Data, [Data(x, 1) for x in bits(a)], interval_delay=1)
        s.b = SourceRTL(Data, [] if duplicate else [Data(x, 1) for x in bits(b)], initial_delay=3)
        s.ctrl = SourceRTL(Ctrl, [Ctrl(opcode, [mk_bits(2)(1), mk_bits(2)(1 if duplicate else 2)]) for _ in a])
        s.sink = SinkRTL(Data, [Data(x, 1) for x in bits(expected)], interval_delay=2)
        s.dut = unit(Data, Ctrl, 2, 1, 8)
        connect(s.a.send, s.dut.recv_in[0])
        connect(s.b.send, s.dut.recv_in[1])
        connect(s.ctrl.send, s.dut.recv_opt)
        connect(s.dut.send_out[0], s.sink.recv)
        s.dut.recv_const.val //= 0
        s.dut.recv_const.msg //= Data()

    def done(s):
        return s.a.done() and s.b.done() and s.ctrl.done() and s.sink.done()


class TileHarness(Component):
    """Explicit diagnostic tile program, not a lowered mapper schedule."""
    def construct(s, unit, opcode, a, b, expected, duplicate=False):
        from VectorCGRA.tile.TileRTL import TileRTL
        from VectorCGRA.fu.flexible.FlexibleFuRTL import FlexibleFuRTL
        from VectorCGRA.lib.messages import mk_cgra_payload, mk_intra_cgra_pkt
        from VectorCGRA.lib.cmd_type import CMD_CONFIG, CMD_LAUNCH, CMD_COMPLETE
        Data, Ctrl = mk_data(32, 1), mk_ctrl(4, 2, 4, 4, 8)
        Payload = mk_cgra_payload(Data, mk_bits(4), Ctrl, mk_bits(3))
        Packet = mk_intra_cgra_pkt(1, 1, 16, Payload)
        ctrl = Ctrl(opcode, [mk_bits(3)(x) for x in (1, 1 if duplicate else 2, 0, 0)],
                    [mk_bits(3)(x) for x in (0, 0, 0, 0, 1, 0 if duplicate else 2, 0, 0)],
                    [mk_bits(2)(x) for x in (1, 0, 0, 0, 0, 0, 0, 0)])
        packets = [Packet(payload=Payload(CMD_CONFIG, ctrl_addr=0, ctrl=ctrl)),
                   Packet(payload=Payload(CMD_LAUNCH))]
        s.ctrl = SourceRTL(Packet, packets)
        s.dut = TileRTL(Packet, 8, 16, 1, len(a), 4, 2, 4, 4, 1, 16,
                        8, FlexibleFuRTL, [unit])
        s.dut.cgra_id //= 0
        s.dut.tile_id //= 0
        s.sources = [SourceRTL(Data, [Data(int(x), 1) for x in values], initial_delay=i*3)
                     for i, values in enumerate((a.view(np.uint32), [] if duplicate else b.view(np.uint32), [], []))]
        s.sinks = [SinkRTL(Data, [Data(int(x), 1) for x in values], interval_delay=2)
                   for values in (expected.view(np.uint32), [], [], [])]
        s.complete = SinkRTL(Packet, [Packet(0, 16, payload=Payload(CMD_COMPLETE))])
        connect(s.ctrl.send, s.dut.recv_from_controller_pkt)
        connect(s.dut.send_to_controller_pkt, s.complete.recv)
        for i in range(4):
            connect(s.sources[i].send, s.dut.recv_data[i])
            connect(s.dut.send_data[i], s.sinks[i].recv)
        s.dut.to_mem_raddr.rdy //= 0
        s.dut.from_mem_rdata.val //= 0
        s.dut.from_mem_rdata.msg //= Data()
        s.dut.to_mem_waddr.rdy //= 0
        s.dut.to_mem_wdata.rdy //= 0

    def done(s):
        return s.ctrl.done() and s.complete.done() and all(x.done() for x in s.sources + s.sinks)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--original", action="store_true", help="negative control: unmodified upstream FP wrappers")
    parser.add_argument("--test-verilog", action="store_true")
    parser.add_argument("--tile", action="store_true", help="exercise control loading and routing on an isolated diagnostic tile")
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    rng = np.random.default_rng(37)
    # Include cancellation, ties, zeros, subnormal values and broad finite exponents.
    a = np.concatenate(([1.5, -1.5, 0, -0.0, 1, 1, 2**-149, 2**-126],
                        np.ldexp(rng.uniform(-1, 1, 256), rng.integers(-60, 61, 256)))).astype(np.float32)
    b = np.concatenate(([2, 1.5, 3, -0.0, 2**-24, 3*2**-24, 2, .5],
                        np.ldexp(rng.uniform(-1, 1, 256), rng.integers(-60, 61, 256)))).astype(np.float32)
    add, mul = (FpAddRTL, FpMulRTL) if args.original else (Fp32AddRTL, Fp32MulRTL)
    cases = [("add", add, OPT_FADD, a, b, a+b), ("sub", add, OPT_FSUB, a, b, a-b),
             ("mul", mul, OPT_FMUL, a, b, a*b), ("square_shared_port", mul, OPT_FMUL, a, a, a*a)]
    samples = rng.normal(size=512).astype(np.float32)
    window = np.tile(np.hanning(256).astype(np.float32), 2)
    cases.append(("window_256_complex_samples", mul, OPT_FMUL, samples, window, samples*window))
    opts = dict(dump_textwave=False, dump_vcd=False, test_verilog="zeros" if args.test_verilog else False,
                test_yosys_verilog=False, max_cycles=10000, dump_vtb="")
    results = []
    for name, unit, opcode, x, y, expected in cases:
        th = (TileHarness if args.tile else Harness)(unit, opcode, x, y, expected, name == "square_shared_port")
        try:
            run_sim(th, opts, print_line_trace=False, duts=["dut"])
            result = dict(name=name, status="passed", samples=len(x), comparison="bit-exact float32 including sign of zero")
        except Exception as error:
            result = dict(name=name, status="failed", samples=len(x), error=str(error))
        results.append(result)
        print(json.dumps(result), flush=True)
    report = dict(scope="isolated tile with diagnostic controls" if args.tile else "FP32 functional units only; window vectors are host-fed, not mapped CGRA execution",
                  status="passed" if all(r["status"] == "passed" for r in results) else "failed",
                  original_wrappers=args.original, translated_fu=args.test_verilog,
                  mapper_schedule_executed=False,
                  seed=37, numpy=np.__version__, cases=results, candidate_hardware_correctness="pending",
                  source_sha256={str(p.relative_to(Path(__file__).resolve().parents[1])): hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in [Path(__file__).resolve(), Path(__file__).resolve().parents[1] / "rtl/fp32.py"]})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(__file__, args.output.with_suffix(".runner.py"))
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    raise SystemExit(0 if report["status"] == "passed" else 1)


if __name__ == "__main__":
    main()
