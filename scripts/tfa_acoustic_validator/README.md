# tfa_acoustic_validator Approved Versions

This folder contains approved package copies of the
`tfa_acoustic_validator` script.

| Version | Build | API | TFA release | Folder | Status |
|---|---:|---:|---:|---|---|
| `0.1.5` | `0001` | `0.1` | `0.0.4` | `v0.1.5-build.0001/` | approved |
| `0.1.4` | `0001` | `0.1` | `0.0.2` | `v0.1.4-build.0001/` | superseded |
| `0.1.3` | `0001` | `0.1` | `0.0.2` | `v0.1.3-build.0001/` | superseded |
| `0.1.2` | `0001` | `0.1` | `0.0.2` | `v0.1.2-build.0001/` | superseded |
| `0.1.1` | `0001` | `0.1` | `0.0.2` | `v0.1.1-build.0001/` | superseded |
| `0.1.0` | `0001` | `0.1` | `0.0.2` | `v0.1.0-build.0001/` | superseded |

`0.1.5` adds the **energy_fractions summary block**. A new helper
`_compute_energy_fractions(z, Omega_phi, H0_X_kms, cosmology)` computes five
values from the in-memory ODE trajectory immediately after the ODE completes.
These are written into `run_results_summary.json` under
`results["acoustic_validator"]["energy_fractions"]`:
- `Omega_phi_0` — Ω_φ at z=0 (tail of the ODE trajectory)
- `Omega_m_0` — 1 − Ω_φ(0) − Ω_r_route(0); route matter fraction at z=0
- `z_eq_lcdm` — (Ω_DE / Ω_m0)^(1/3) − 1; ΛCDM matter-DE equality redshift
- `z_eq_route` — redshift where Ω_φ(z) = 0.5 (equivalently Ω_φ = Ω_m for
  flat universe); found by linear interpolation in the in-memory arrays
- `delta_z_eq` — z_eq_route − z_eq_lcdm; ≤ 0 for thawing routes; measures
  how much the equality is delayed relative to ΛCDM

If no crossing is found, `z_eq_route` and `delta_z_eq` are `null` and a
`z_eq_note` string is added. Non-gated: the block is always written, including
for EXCLUDED routes. Physics verdicts (H0_X, band) are unchanged.
Required by `tfa_plot_exporter v0.1.1` for the `energy_fractions` plot.

`0.1.4` adds the **drag-epoch sound horizon** to the acoustic anchor. The
Eisenstein-Hu (1998) fitting formula (`compute_z_drag`) gives z_drag ≈ 1063
(slightly below z_star ≈ 1092). The same `rs_calibration` factor is applied so
both scales share a consistent sound-speed normalisation. The new fields
`z_drag` and `r_drag_Mpc` (≈ 146.9 Mpc) are written into
`run_results_summary.json` under `results["acoustic_validator"]["acoustic_anchor"]`.
The BAO validator (`tfa_bao_validator v0.1.1`) reads `r_drag_Mpc` as its ruler;
`r_s_Mpc` (≈ 144.4 Mpc, z_star horizon) remains available for H0X
normalisation and regression. Physics verdicts (H0_X, band) are unchanged.

`0.1.2` is a strict superset of `0.1.1` (identical physics + the in-memory
`validate_h0x` API) plus the **file-based engine entry point** for the run-folder
architecture (see `system-design.md`):

- `run_acoustic_validator(run_folder) -> (Code, Desc)` — reads the contract +
  frozen settings from the run folder, rebuilds `V` from the named form via
  `build_potential_from_form`, integrates once, solves H0X, writes
  `trajectory.csv`, and — when the band passes the export gate — writes the
  three contract output CSVs: `expansion_history_shape.csv` (`z, E_X`),
  `expansion_history_h0x_normalized.csv` (`z, H_X`), and `w_of_z.csv`
  (`z, w_phi`). Enriches `run_results_summary.json` under
  `results["acoustic_validator"]`. It is the **first specialist** in the chain
  and the only one that integrates the ODE.
- `build_potential_from_settings(settings, cosmology)` — evaluates
  `V_of_phi` / `dV_dphi` expression strings from settings; universal, no
  catalog. `potential_from_settings(settings)` returns the spec mapping.

The `0.1.1`-pinned builds (`tfa_normalized_history_generator`,
`tfa_physics_guard_validator`, `tfa_csv_exporter`) still import the `v0.1.1`
folder; they will be repointed when they are reworked for the file-based flow.

Use this script when only the H0X acoustic verdict is needed, or as the engine
behind the hub.

`0.1.1` aligns `compute_r_s_raw_Mpc` with the canonical `tfa_common`/`wli_run`/
appendix form (matter+radiation-only integrand, `31500` R-form, `ln(1+z)`
substitution). `0.1.0` had a rewritten `r_s` integrand (dark energy included,
different R form, direct-z) that reported the wrong `r_s_raw` (144.262 vs
144.1050) and `rs_calibration` (1.00093 vs 1.00202084). `H0_X` is unchanged by
the fix (the raw sound horizon cancels in the self-calibration). `0.1.0` is
retained un-patched for comparison.

