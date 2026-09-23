"""Run inside the pinned Neura image: demonstrate OPT_MUL is not float32 FMUL.

This is a functional-unit probe, NOT an FMCW or whole-candidate RTL test.
"""
import json
import struct

from pymtl3 import mk_bits, clog2
from VectorCGRA.fu.single.MulRTL import MulRTL
from VectorCGRA.fu.single.test.MulRTL_test import TestHarness, run_sim
from VectorCGRA.lib.messages import mk_data, mk_ctrl
from VectorCGRA.lib.opt_type import OPT_MUL


def bits(value):
    return struct.unpack("<I", struct.pack("<f", value))[0]


data, ctrl = mk_data(32, 1), mk_ctrl(4, 1)
port = mk_bits(clog2(5))
a, b = bits(1.5), bits(2.0)
integer_result = (a * b) & 0xffffffff
harness = TestHarness(MulRTL, data, ctrl, 4, 1, 8,
                      [data(a, 1)], [data(b, 1)], [data(0, 1)],
                      [ctrl(OPT_MUL, [port(1), port(3), port(0), port(0)])],
                      [data(integer_result, 1)])
run_sim(harness)
print(json.dumps({"scope": "MulRTL functional unit, pure PyMTL simulation",
                  "inputs_float32": [1.5, 2.0], "opcode": "OPT_MUL",
                  "observed_payload": integer_result, "expected_float32_payload": bits(3.0),
                  "matches_float32": integer_result == bits(3.0),
                  "candidate_correctness": "not tested"}))
