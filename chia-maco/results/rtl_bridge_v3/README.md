# Compiler/RTL compatibility repair — component validation, not full FMCW

## Implemented and measured

- `rtl/fp32.py` adapts the pinned VectorCGRA wrappers to IEEE binary32.
  HardFloat expects exponent/significand widths `(8, 24)`, including the hidden
  significand bit. The upstream wrapper passes `(exp_nbits + 1, sig_nbits)`;
  its defaults therefore produce `(9, 23)`. The adapter corrects this without
  editing the upstream checkout.
- `src/chia_maco/rtl_bridge.py` joins original LLVM instructions to the successful
  PE/cycle schedule and checks against the exported configuration. It restores
  floating opcodes, handles repeated operands (`x*x` is not a constant multiply),
  and preserves the CFAR unsigned-less-than predicate (not equality).
- All five scalar 4x4 kernel exports were processed. There are 17 floating
  operations and one additional unsigned comparison correction. Transpose has
  no floating arithmetic and its configuration remains unchanged.
- `fp32_corrected.json`: translated FU tests pass **1,577 comparisons**: 1,568
  bit-exact FP32 results and nine exact unsigned comparisons.
- `fp32_tile.json`: the same 1,577 comparisons pass on a translated real
  VectorCGRA TileRTL, including configuration packets, routing, backpressure,
  repeated control execution and completion reporting.
- The window test feeds 256 complex samples (512 scalar products). The square
  test uses one shared operand port, not two independent copies of the input.

The test deliberately uses an **isolated diagnostic tile**, control memory 8,
eight registers per bank, and host-fed data. It does **not** execute the restored
mapper schedule or certify a 4x4 candidate. No candidate performance is inferred.
`fp32_original.json` is a negative control: the original FP wrappers fail the
floating tests. Failure is expected and retained.

## Reproduce

From the artifact root, with a NEW output name:

```bash
docker run --rm --network none --user "$(id -u):$(id -g)" \
  -v "$PWD/chia-maco:/artifact" --entrypoint bash cgra/neura-flow:20260114 -lc \
  'cd /tmp && PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/WORK_REPO/CGRA-Flow /WORK_REPO/venv/bin/python /artifact/scripts/check_fp32_rtl.py --tile --test-verilog --output /artifact/results/rtl_NEW/tile.json'

.venv/bin/python -m chia_maco.cli export-rtl-opcodes \
  --artifacts chia-maco/results/rtl_audit/window \
  --log chia-maco/results/rtl_audit/window.log \
  --mapping chia-maco/results/rtl_audit/window_result.json \
  --output-dir chia-maco/results/rtl_NEW/window
```

Omit `--tile` for FU tests. Add `--original` for the expected failing control.
The scripts save their source hash and a runner snapshot; opcode exports retain
an adapter snapshot and source hashes. No existing result directory is replaced.
The Docker image used was
`sha256:8c4fed3b0d751e8e53ef660fb502e42ca242514ce8ba3d2701186ef904cde8e5`,
VectorCGRA commit `40006affef482349ec9418021d23141f876259ed`.

## What is NOT implemented

The restored JSON is an intermediate export, not executable control packets.
The remaining compiler/RTL connection needs:

1. Ordered operands and register reads/writes, including the duplicated square
   input; the legacy config supplies routing selectors but no complete modern
   register-control program.
2. Constant and live-in loading. DFG `in_const` arrays are empty even for loop
   bounds, initial phi values and array bases. The unsigned LT requires its
   constant on an ordinary input because CompRTL has no `LT_CONST` operation.
3. Explicit lowering of the x86 LLVM 64-bit indices/pointers into bounded CGRA
   memory addresses, plus the memory map and timing model.
4. Loop prologues/epilogues, predicate behavior and inter-stage orchestration.
   Current mappings are representative kernel loops, not complete FMCW binaries.
5. Full-frame output comparison and cycle accounting, followed by synthesis of
   those same verified configurations and matched-budget search comparisons.

The native CFAR specification is unchanged: strict detection equality remains
2/6. No power floor or relaxed acceptance threshold was introduced.

The v3 exports supersede earlier diagnostic snapshots and should be used for
further compiler integration.
