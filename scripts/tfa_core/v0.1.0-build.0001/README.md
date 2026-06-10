# tfa_core 0.1.0 build 0001

Shared core utilities for the TFA package. Holds the generic logic every
specialist needs, so no specialist re-implements it. **Standalone in this build:
not yet imported by any other script.**

## Contents

| Area | Provided |
|---|---|
| Identity / errors | `script_identity`, `TFAError`, `PHASE_ERROR_CODES`, `phase_error` |
| Encoding policy | `ascii_safe`, `console_print`, `write_text_utf8`, `read_json`, `atomic_write_json` (UTF-8 **no BOM**) |
| Config objects | `CosmologyContext`, `AcousticConfig`, `AcousticBands`, `IntegrationConfig`, `PotentialRoute` |
| Settings | `_unified_settings_path`, `load_environment_settings`, and the `*_from_settings` builders |
| Potential builder | `build_potential_from_settings` (sandboxed expression strings; numerical `dV/dphi` fallback) |
| Scalar ODE | `eval_route_state`, `make_scalar_rhs`, `integrate_scalar_route`, `evaluate_raw_E_at_z` |
| FLRW helpers | `H_lcdm_kms`, `comoving_distance_Mpc` |
| Run record | `RunTrace` (JSON-lines, UTF-8 no BOM) |

## Scope boundary

Core holds only the **generic** physics: the canonical scalar ODE and the FLRW
distance integral. The **acoustic anchor** (z_star, r_s, theta matching, the
H0 solve) stays in `tfa_acoustic_validator`. The shared config object
`AcousticConfig` lives here so every script reads the same anchor inputs, but the
anchor functions do not.

## Intentional deviation from earlier engine builds

`make_scalar_rhs` uses the **exact** logarithmic Hubble derivative
`H_N/H = -3/2 (1 + w_eff)` (theoretical-foundations eq. 14). Earlier builds used
a numerator-only approximation that dropped the kinetic-denominator term. The
difference is numerically negligible (raw_E(0) shifts by ~1e-3, H0 by
~0.005 km/s/Mpc); this form is exact and matches the manuscript. The
normalization to `E_X(0) = 1` is **not** done here — it is an acoustic-validator
step; core returns the raw, un-normalized shape.

## Encoding policy

ASCII-only source. ASCII-only console output via `console_print` / `ascii_safe`.
All file writes are UTF-8 without a BOM. This removes the recurring
codepage / BOM / non-ASCII failures on Windows native runtimes.

## Tests

`test_tfa_core.py` - 27 unit tests, all passing. Coverage includes:

- the frozen-field = LCDM identity (ODE + FLRW agree to 1e-9),
- the sandbox blocking `__builtins__`,
- UTF-8-no-BOM file writes and JSON round-trip,
- settings resolution and builders against the real package settings,
- band classification, config validation, the kinetic bound, and the run trace.

Run:

```
python -m unittest test_tfa_core -v
```

Real-route smoke check (WQI_F765, z_ini=1e6): `raw_E(0)=0.981173`,
`raw_E(1100)=23570.54` matching LCDM to the printed precision (early inertness
reproduced).
