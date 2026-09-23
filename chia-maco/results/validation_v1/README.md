# Native correctness investigation — not a hardware certificate

Run: `chia-maco validate-native --output-dir results/validation_v1`.
Exit code **1** is expected for this recorded suite: strict detection equality
fails in four of six scenes. Nothing was relaxed after observing the results.

All range-FFT, Doppler-FFT and power arrays satisfy the predefined normalized
maximum error bound of 2e-5. Observed nonzero-reference errors are below 1.5e-7.
The noisy-target and zero-input cases also have identical complete CFAR masks.

| Scene | CFAR mask differences | Maximum golden power at differing bins / frame peak |
|---|---:|---:|
| Single target | 1343 | 1.35e-17 |
| Multiple targets | 693 | 5.59e-19 |
| Noisy targets | 0 | — |
| Zero input | 0 | — |
| Edge target | 1813 | 2.07e-25 |
| Large amplitude | 1275 | 7.80e-18 |

This localizes mismatches to near-zero-power bins in noiseless scenes. It does
not justify hiding them: the strict detection criterion remains failed. A new
power floor or a different numerical acceptance rule requires a separately
versioned specification and rerun, retaining this evidence.

NPZ bundles retain the identical input, both intermediate FFT arrays, power
maps, masks and golden thresholds. Display maps share a color scale and clamp
below -100 dB for visualization only; comparisons use full-precision arrays.

The native shared library is generated from unchanged workload C with explicit
non-fast-math/no-FMA-contraction flags. This suite validates neither mapper
views nor a CGRA candidate. Model/array/compiler hashes and test criteria are
in `validation.json`.
