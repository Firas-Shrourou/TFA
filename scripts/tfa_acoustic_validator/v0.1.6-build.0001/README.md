# tfa_acoustic_validator 0.1.6 build 0001

The TFA engine, redesigned per T004 deliverables item 1. Computes H0_X, delta_X,
the band verdict, the gated normalized history, the energy budget, and a
self-consistency field. Only specialist that integrates the scalar ODE.

## What changed from 0.1.5

1. **Depends on `tfa_core`.** The generic logic (ODE, settings, potential
   builder, FLRW helpers, I/O, trace, errors, encoding) comes from `tfa_core`.
   No specialist is imported. The acoustic anchor physics (z_star, z_drag, the
   r_s integral, sound speed) stays here, as agreed.

2. **Normalization fix (load-bearing).** H0_X is solved from the **normalized**
   shape `E_X` with `E_X(0)=1`:

       I_X  = integral_0^z* dz / E_X ,   E_X = raw_E / raw_E(0)
       H0_X = c * I_X / D_target

   Build 0.1.5 used the raw shape in the distance integral, inflating H0_X by
   `1/raw_E(0)`. The output history `H_X = H0_X * E_X` now has
   `D_M(z*) = D_target` **by construction**, so it reproduces the observed
   acoustic angle. Verified: `D_M_X == D_target`.

3. **rs_calibration removed.** `D_target = r_star / theta_obs` is built from a
   **sourced** sound horizon (Planck `r_* = 144.39 Mpc`, overridable via
   `acoustic_priors.r_star_Mpc`) and the observed angle. The EH-fit `r_s` is
   still computed and reported (`r_s_computed_Mpc`) for transparency, and
   `theta_lcdm = r_star / D_M_LCDM` is reported as an anchor cross-check.
   `calibration_applied = false`.

4. **delta_X** is an audit signature only (`H0_X / H0_ref - 1`), not consumed
   downstream.

5. **Self-consistency field** added to `energy_fractions`:
   `omega_m_out = Omega_m_0 * (H0_X/100)^2`, `omega_m_input_OMH2`, and
   `omega_m_residual_pct = omega_m_out/OMH2 - 1`.

6. **Drag ruler** `r_drag` is sourced (Planck `147.05 Mpc`, overridable via
   `acoustic_priors.r_drag_Mpc`); the EH-fit value is reported alongside.

## Verification (WLI_1, full z_ini=1e6, temp copy of the real run)

| quantity | value | note |
|---|---|---|
| H0_X | **65.151** | corrected (0.1.5 gave 67.598) |
| D_M_X == D_target | True (13868.985) | normalization fix |
| delta_X | -0.033 | audit, negative |
| raw_E0 | 0.96376 | un-normalized shape at z=0 |
| omega_m_out / residual | 0.14404 / **+0.73%** | self-consistency field |
| r_star / source | 144.39 / Planck2018_r_star | no calibration |
| theta_lcdm vs theta_obs | 0.0104106 vs 0.010411 | anchor consistent |

With the gate disabled, `shape_check` and `normalization_check` both PASS and the
shape / normalized-history / w_of_z CSVs are written. Under the active DESI
w0waCDM bands, mild thawers are admitted and strong thawers are EXCLUDED; the
export gate skips downstream histories only for the excluded routes unless the
gate is deliberately disabled for audit runs.

## Scope notes

- The in-memory `validate_h0x` API of 0.1.5 is dropped: downstream specialists
  read trajectory.csv / the summary, not this module. The file-based
  `run_acoustic_validator(run_folder) -> (Code, Desc)` is the entry point.
- ASCII source, UTF-8 no BOM. Resolves `tfa_core` from
  `../../tfa_core/v0.1.0-build.0001`.
- Wired into `tfa_common 0.9.2` as part of the approved T004 stack.
