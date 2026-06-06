# CSV Outputs Reference

TFA writes CSV files into each timestamped run folder. The exact set depends on
the export gate and on which diagnostics are enabled.

A fully accepted run can contain:

```text
trajectory.csv
expansion_history_shape.csv
expansion_history_h0x_normalized.csv
w_of_z.csv
physics_guards.csv
bao_results_per_datum.csv
rsd_results_per_datum.csv
```

A gated or diagnostic-disabled run may contain only the always-written products,
such as `trajectory.csv` and `physics_guards.csv`.

## Product map

| File | Written by | Availability | Read by |
|---|---|---|---|
| `trajectory.csv` | `tfa_acoustic_validator` | Always written after a successful acoustic integration. | Physics guards and plot exporter. |
| `expansion_history_shape.csv` | `tfa_acoustic_validator` | Written only when the export gate accepts the route. | Readers and external analysis. |
| `expansion_history_h0x_normalized.csv` | `tfa_acoustic_validator` | Written only when the export gate accepts the route. | Plot exporter, BAO validator, RSD validator. |
| `w_of_z.csv` | `tfa_acoustic_validator` | Written only when the export gate accepts the route. | Readers and external analysis. |
| `physics_guards.csv` | `tfa_physics_guard_validator` | Written after successful guard validation. | Readers. |
| `bao_results_per_datum.csv` | `tfa_bao_validator` | Written when BAO is enabled and the normalized history exists. | Readers and plotting/audit workflows. |
| `rsd_results_per_datum.csv` | `tfa_rsd_validator` | Written when RSD is enabled and the normalized history exists. | Readers and plotting/audit workflows. |

The summary file `run_results_summary.json` names the CSV files that were
written by each module. See `docs/run-summary-reference.md`.

## Comment metadata rows

Some CSV files begin with metadata rows whose first cell starts with `#`, for
example:

```text
# quantity,H_X
# units,km s^-1 Mpc^-1
z,H_X
0,67.5821638057
```

These rows are part of the file contract. When loading such files with Python,
Pandas, R, or spreadsheet software, skip or parse leading `#` rows before
reading the tabular header.

Files with leading metadata rows:

- `expansion_history_shape.csv`
- `expansion_history_h0x_normalized.csv`
- `w_of_z.csv`
- `physics_guards.csv`

Files without leading metadata rows:

- `trajectory.csv`
- `bao_results_per_datum.csv`
- `rsd_results_per_datum.csv`

## `trajectory.csv`

Written by `tfa_acoustic_validator`.

This is the full scalar trajectory on the solver grid. It is the numerical
backbone for the physical guards and the always-available plots.

Columns:

| Column | Meaning |
|---|---|
| `N` | E-fold variable, with `N = -ln(1+z)`. |
| `z` | Redshift. |
| `a` | Scale factor, `a = 1 / (1+z)`. |
| `phi` | Scalar field value. |
| `dphi_dN` | Derivative of the field with respect to `N`. |
| `E_X` | Dimensionless route expansion shape normalized so `E_X(0) = 1`. |
| `H_X` | Acoustic-normalized Hubble history in km/s/Mpc. |
| `w_phi` | Scalar equation of state. |
| `Omega_phi` | Scalar-field density fraction along the route. |

Used by:

- `tfa_physics_guard_validator` for `z` and `w_phi`.
- `tfa_plot_exporter` for `w_of_z`, `Omega_phi`, `phase_portrait`, and
  `energy_fractions` plots.

## `expansion_history_shape.csv`

Written by `tfa_acoustic_validator` when the export gate accepts the route.

This file records the exported low-redshift and acoustic-scale shape grid for
the dimensionless expansion history.

Metadata rows:

| Metadata | Meaning |
|---|---|
| `# quantity` | `E_X`. |
| `# units` | `dimensionless`. |
| `# normalization_mode` | `shape_only`. |
| `# H0_X` | Route-specific acoustic-preserving Hubble constant. |
| `# H0_Lambda` | Reference Hubble constant from settings. |
| `# delta_X` | Relative Hubble offset `(H0_X - H0_Lambda) / H0_Lambda`. |
| `# shape_residual` | Residual of the `E_X(0) = 1` check. |
| `# shape_check` | `PASS` or `FAIL`. |

Columns:

| Column | Meaning |
|---|---|
| `z` | Redshift on the exported grid. |
| `E_X` | Dimensionless normalized expansion shape. |

This file is mainly for external analysis and audit. Downstream TFA validators
use the normalized-history file instead.

## `expansion_history_h0x_normalized.csv`

Written by `tfa_acoustic_validator` when the export gate accepts the route.

This is the main downstream history file. It contains:

```text
H_X(z) = H0_X * E_X(z)
```

Metadata rows:

| Metadata | Meaning |
|---|---|
| `# quantity` | `H_X`. |
| `# units` | `km s^-1 Mpc^-1`. |
| `# normalization_mode` | `h0x_normalized`. |
| `# H0_X` | Route-specific acoustic-preserving Hubble constant. |
| `# H0_Lambda` | Reference Hubble constant from settings. |
| `# delta_X` | Relative Hubble offset `(H0_X - H0_Lambda) / H0_Lambda`. |
| `# normalization_residual` | Residual of the `H_X(0) = H0_X` check. |
| `# normalization_tolerance` | Tolerance used for the normalization check. |
| `# normalization_check` | `PASS` or `FAIL`. |

Columns:

| Column | Meaning |
|---|---|
| `z` | Redshift on the exported grid. |
| `H_X` | Acoustic-normalized route Hubble history in km/s/Mpc. |

Used by:

- `tfa_plot_exporter` for `H_of_z` and `delta_H`.
- `tfa_bao_validator` for distance integrals.
- `tfa_rsd_validator` for growth integration.

If this file is absent, BAO and RSD are skipped and the gated plots are skipped.

## `w_of_z.csv`

Written by `tfa_acoustic_validator` when the export gate accepts the route.

Metadata rows:

| Metadata | Meaning |
|---|---|
| `# quantity` | `w_phi`. |
| `# units` | `dimensionless`. |
| `# H0_X` | Route-specific acoustic-preserving Hubble constant. |
| `# H0_Lambda` | Reference Hubble constant from settings. |
| `# delta_X` | Relative Hubble offset. |
| `# band` | Acoustic band assigned to the route. |

Columns:

| Column | Meaning |
|---|---|
| `z` | Redshift on the exported grid. |
| `w_phi` | Scalar equation of state at that redshift. |

Use this file for low-redshift equation-of-state inspection. For the full
solver-grid equation-of-state history, use `trajectory.csv`.

## `physics_guards.csv`

Written by `tfa_physics_guard_validator`.

This is the row-level record behind
`results.physics_guard_validator` in `run_results_summary.json`.

Metadata rows:

| Metadata | Meaning |
|---|---|
| `# product` | `physics_guards`. |
| `# benchmark_id` | Route label. |
| `# overall_pass` | Whether all guard verdicts passed. |
| `# guard_script` | Script version and build that wrote the file. |

Columns:

| Column | Meaning |
|---|---|
| `guard` | Guard family, such as `canonical`, `thawing`, `phantom_crossing`, or `BBN`. |
| `field` | Specific verdict, diagnostic, or threshold name. |
| `value` | Value for that field. |
| `category` | `verdict`, `diagnostic`, or `threshold`. |

Typical fields include:

- `canonical_ok`
- `minimum_w_phi`
- `canonical_w_floor`
- `canonical_thawing_ok`
- `minimum_delta_w`
- `late_sample_count`
- `phantom_crossing_ok`
- `BBN_OK`
- `Omega_phi_BBN`

Use the summary JSON for compact guard verdicts and this CSV for row-level
inspection.

## `bao_results_per_datum.csv`

Written by `tfa_bao_validator`.

This file stores one row per BAO datum. It is written only when BAO is enabled,
the route passes the export gate, and `expansion_history_h0x_normalized.csv`
exists.

Columns:

| Column | Meaning |
|---|---|
| `datum_index` | Row index in the bundled BAO data vector. |
| `z_eff` | Effective redshift of the datum. |
| `observable` | BAO observable type: `DV_over_rs`, `DM_over_rs`, or `DH_over_rs`. |
| `observed` | Observed BAO value from the bundled data. |
| `sigma` | Per-datum uncertainty used for the pull column. |
| `model` | Route model value for the same observable. |
| `residual` | `model - observed`. |
| `pull` | Residual divided by `sigma`. |
| `datum_status` | Pull classification: `PASS_1SIGMA`, `PASS_2SIGMA`, `PASS_3SIGMA`, or `OUTSIDE_3SIGMA`. |
| `D_H_Mpc` | Route radial Hubble distance at `z_eff`. |
| `D_M_Mpc` | Route transverse comoving distance at `z_eff`. |
| `D_V_Mpc` | Route volume-averaged BAO distance at `z_eff`. |
| `rd_X_Mpc` | Route drag-epoch sound horizon used as the BAO ruler. |
| `interpolation_method` | Interpolation method used for `H_X(z)`, currently `PchipInterpolator`. |

The run-level BAO chi-squared summary is stored in
`run_results_summary.json`. This CSV is the per-datum residual table behind
that summary.

## `rsd_results_per_datum.csv`

Written by `tfa_rsd_validator`.

This file stores one row per redshift-space distortion datum. It is written
only when RSD is enabled, the route passes the export gate, and
`expansion_history_h0x_normalized.csv` exists.

Columns:

| Column | Meaning |
|---|---|
| `datum_index` | Row index in the bundled RSD compilation. |
| `z_eff` | Effective redshift of the measurement. |
| `survey` | Survey or source label for the datum. |
| `observed` | Observed `f_sigma8` value. |
| `sigma` | Per-datum uncertainty. |
| `model` | Route model value for `f_sigma8(z_eff)`. |
| `residual` | `model - observed`. |
| `pull` | Residual divided by `sigma`. |
| `datum_status` | Pull classification: `PASS_1SIGMA`, `PASS_2SIGMA`, `PASS_3SIGMA`, or `OUTSIDE_3SIGMA`. |
| `f_X` | Route growth rate `f = dlnD/dlna` at the datum. |
| `sigma8_X` | Route sigma8 normalization used for the model value. |
| `D_X_norm` | Route growth factor normalized for the RSD calculation. |
| `growth_ratio` | Route-to-reference growth amplitude ratio. |

The run-level RSD chi-squared summary is stored in
`run_results_summary.json`. This CSV is the per-datum growth-residual table
behind that summary.

## Gating behavior

The acoustic validator always writes `trajectory.csv` after a successful scalar
integration. It writes the exported history CSVs only when the export gate
accepts the route's acoustic band.

When the export gate rejects a route:

- `trajectory.csv` is still written.
- `physics_guards.csv` can still be written.
- `expansion_history_shape.csv` is absent.
- `expansion_history_h0x_normalized.csv` is absent.
- `w_of_z.csv` is absent.
- BAO and RSD CSVs are absent because their validators are skipped.
- `H_of_z` and `delta_H` plots are skipped.

Check `results.acoustic_validator.export_gate` in
`run_results_summary.json` to explain which outputs should exist for a run.

## Loading tips

For quick inspection:

- Use `run_results_summary.json` first to see which CSVs were written.
- Use `trajectory.csv` for full scalar-history work.
- Use `expansion_history_h0x_normalized.csv` for distance or growth work.
- Use `bao_results_per_datum.csv` and `rsd_results_per_datum.csv` for
  per-observation residual analysis.

For scripts, read metadata-comment CSVs by skipping leading rows whose first
cell begins with `#`, then parse the first non-comment row as the header.
