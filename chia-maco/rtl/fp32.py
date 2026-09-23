"""FP32 constructors for the pinned VectorCGRA/HardFloat interfaces.

VectorCGRA passes (exp_nbits + 1, sig_nbits) to HardFloat, whose parameters
are exponent width and significand width INCLUDING the hidden bit.
IEEE binary32 therefore needs (7, 24) at that wrapper, not (8, 23).
This adapter does not change the original VectorCGRA checkout.
"""
from pymtl3 import mk_bits
from VectorCGRA.fu.float.FpAddRTL import FpAddRTL
from VectorCGRA.fu.float.FpMulRTL import FpMulRTL


class Fp32AddRTL(FpAddRTL):
    def construct(s, DataType, CtrlType, num_inports, num_outports,
                  data_mem_size, ctrl_mem_size=4, data_bitwidth=32):
        assert data_bitwidth == 32
        super().construct(DataType, CtrlType, num_inports, num_outports,
                          data_mem_size, ctrl_mem_size, 32, 7, 24)
        s.FLOATING_ONE = mk_bits(32)(0x3f800000)


class Fp32MulRTL(FpMulRTL):
    def construct(s, DataType, CtrlType, num_inports, num_outports,
                  data_mem_size, ctrl_mem_size=4, data_bitwidth=32):
        assert data_bitwidth == 32
        super().construct(DataType, CtrlType, num_inports, num_outports,
                          data_mem_size, ctrl_mem_size, 32, 7, 24)
