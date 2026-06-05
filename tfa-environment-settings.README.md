# TFA Environment Settings Input Contract

The package-root `tfa-environment-settings.json` is the user-owned input
contract for a TFA run. It lives at the repository root and defines the
scalar route, cosmological priors, acoustic anchor, numerical integration
controls, export policy, physical-guard thresholds, diagnostic switches, and
execution trace settings.

In normal use, the researcher edits this file, then runs TFA. At run time,
`tfa_common` freezes a copy of the exact settings file into the run folder as
`environment-settings.json`. That frozen copy is the audit record used by the
acoustic, guard, plot, BAO, and RSD stages.

## Location Rule

The package-level user contract is:

```text
tfa-environment-settings.json
```

The package-root launchers (`run_tfa.py`, `run_tfa.bat`, and `run_tfa.sh`) read
this file and write outputs under `results/`.

The `sample-routes/` folders intentionally carry separate
`tfa-environment-settings.json` files. These are preconfigured route contracts
for fixed WLI/WQI markers, with their own Python, Windows, and Unix launchers.
A sample launcher reads the settings file inside its own sample folder and
writes outputs to that sample folder's `results/` subfolder.

Approved script folders under `scripts/` do not carry their own settings copy.
A different settings file may also be supplied explicitly through the
programmatic `settings_path` argument.

## File Layout

The settings file has three top-level sections:

| Section | Runtime role |
|---|---|
| `schema` | File identity and compact compatibility metadata: settings file version, TFA package release, and the active compatible script list. |
| `read_only_hardcoded_defaults` | Reference mirror of default values and expected fields. It documents the contract but is not consumed by runtime builders. |
| `user_adjustable` | The active input contract. Runtime code reads this section to define the run. |

All scientific and numerical changes for a run should be made under
`user_adjustable`.

## Active Runtime Sections

The `user_adjustable` object contains these sections:

| Section | Purpose |
|---|---|
| `potential` | Defines the scalar route: route identifier, potential expression, derivative expression, route parameters, initial field state, and optional user remarks. |
| `cosmology` | Defines flat-background present-day cosmological values used by the route and diagnostics. |
| `acoustic_priors` | Defines the early-time acoustic anchor and numerical tolerance for theta matching. |
| `planck_h0_bands` | Defines the admissibility bands used to classify the derived `H0_X`. |
| `integration` | Defines the scalar ODE integration interval and solver tolerances. |
| `export` | Defines history-grid tolerances and run-folder naming behavior. |
| `export_gate` | Defines which acoustic bands are allowed to export normalized histories and downstream products. |
| `physics_guards` | Defines thresholds for canonical, thawing, phantom-crossing, and BBN checks. |
| `execution` | Defines debug printing and JSON-lines trace behavior. |
| `bao_validator` | Enables or disables the bundled DESI DR2 BAO diagnostic. |
| `rsd_validator` | Enables or disables the bundled f-sigma8 RSD diagnostic. |

## Scalar Route Contract

The most important user-edited block is:

```json
"potential": {
  "benchmark_id": "WQI_F765",
  "V_of_phi": "3 * Omega_DE * (phi_F**4 + M_Mp**4) / (phi**4 + M_Mp**4)",
  "dV_dphi": "-4 * phi**3 * 3 * Omega_DE * (phi_F**4 + M_Mp**4) / (phi**4 + M_Mp**4)**2",
  "parameters": {
    "phi_F": 7.65,
    "M_Mp": 1.794e-13
  },
  "initial_phi": 7.65,
  "initial_phi_N": 0.0,
  "user_remarks": ""
}
```

Field meanings:

| Field | Meaning |
|---|---|
| `benchmark_id` | Human-readable route label copied into the run summary and output metadata. |
| `V_of_phi` | Expression string for the scalar potential `V_X(phi)`. |
| `dV_dphi` | Expression string for `dV_X/dphi`. Supplying the analytic derivative is preferred. If omitted or empty, the acoustic validator uses a central finite-difference derivative. |
| `parameters` | JSON object containing numeric parameters referenced by the expression strings. |
| `initial_phi` | Initial field value used to start the scalar evolution. |
| `initial_phi_N` | Initial derivative `dphi/dN`; thawing examples usually use `0.0`. |
| `user_remarks` | Optional free-text note copied into the run summary; useful for local comments, source notes, or run intent. It does not affect physics. |

The expression namespace provides:

| Name | Availability |
|---|---|
| `phi` | Current field value, supplied by TFA during evaluation. |
| `Omega_DE` | Derived from the cosmology block; if `Omega_DE` is `null`, TFA uses flatness: `1 - Omega_m0 - Omega_r0`. |
| Parameters | Every key in `potential.parameters`, converted to float. |
| Math functions | `exp`, `log`, `log10`, `sqrt`, `abs`, `sin`, `cos`, `tan`, `sinh`, `cosh`, `tanh`, `arcsin`, `arccos`, `arctan`, plus `pi` and `e`. |

Expression strings are evaluated with Python builtins disabled. They should be
plain numeric expressions in terms of `phi`, `Omega_DE`, declared parameters,
and the allowed math functions.

## Source-Backed Route Examples

The current demonstration set uses two source-backed route families:

### WQI marker example

```json
"potential": {
  "benchmark_id": "WQI_F680",
  "V_of_phi": "3 * Omega_DE * (phi_F**4 + M_Mp**4) / (phi**4 + M_Mp**4)",
  "dV_dphi": "-4 * phi**3 * 3 * Omega_DE * (phi_F**4 + M_Mp**4) / (phi**4 + M_Mp**4)**2",
  "parameters": {
    "phi_F": 6.80,
    "M_Mp": 1.794e-13
  },
  "initial_phi": 6.80,
  "initial_phi_N": 0.0,
  "user_remarks": ""
}
```

The WQI family uses markers `WQI_F680` and `WQI_F765`, corresponding to
`phi_F = 6.80` and `7.65`.

### WLI marker example

```json
"potential": {
  "benchmark_id": "WLI_3",
  "V_of_phi": "3 * Omega_DE * (phi_inf / phi) ** alpha",
  "dV_dphi": "-alpha * 3 * Omega_DE * (phi_inf / phi) ** alpha / phi",
  "parameters": {
    "alpha": 2.0,
    "phi_inf": 1.30
  },
  "initial_phi": 1.30,
  "initial_phi_N": 0.0,
  "user_remarks": ""
}
```

The WLI family uses six markers: `alpha = 1.0, 1.5, 2.0` crossed with
`phi_inf = 1.30, 1.35`.

These marker routes are package demonstrations. They exercise the input and
output contract; they are not a statistical fit or ranking of the source
families.

## Cosmology Contract

```json
"cosmology": {
  "Omega_m0": 0.3152,
  "Omega_r0": 0.0000918,
  "Omega_DE": null,
  "H0_ref_kms": 67.36,
  "c_kms": 299792.458
}
```

`Omega_m0` and `Omega_r0` define the present matter and radiation fractions.
When `Omega_DE` is `null`, TFA enforces flatness and sets
`Omega_DE = 1 - Omega_m0 - Omega_r0`. `H0_ref_kms` is the reference Hubble
constant used for comparisons and metadata. `c_kms` is the speed of light in
km/s.

## Acoustic Anchor Contract

```json
"acoustic_priors": {
  "OBH2": 0.02237,
  "OMH2": 0.143,
  "T0_K": 2.7255,
  "NEFF": 3.046,
  "OGH2": 0.000024728,
  "theta_star_target": 0.010411,
  "z_integral_max": 100000000.0,
  "theta_tolerance": 1e-10
}
```

This block defines the early-time physical anchor used to solve for the
route-specific acoustic-preserving `H0_X`. TFA computes the route-generated
shape `E_X(z)`, then solves for the `H0_X` that matches `theta_star_target`.

The derived `H0_X` is classified using:

```json
"planck_h0_bands": {
  "strict": [66.82, 67.9],
  "loose_2s": [66.28, 68.44],
  "loose_3s": [65.74, 68.98]
}
```

Band labels are assigned narrowest first: `STRICT`, `LOOSE_2S`, `LOOSE_3S`,
or `EXCLUDED`.

## Integration Contract

```json
"integration": {
  "z_ini": 1000000.0,
  "z_final": 0.0,
  "method": "DOP853",
  "rtol": 1e-10,
  "atol": 1e-12,
  "max_step": 0.01,
  "dense_output": true
}
```

This block controls the homogeneous scalar-field ODE solve. The default
integration runs from high redshift to the present using SciPy's `DOP853`
solver with dense output enabled.

## Export Contract

```json
"export": {
  "shape_tolerance": 1e-10,
  "normalization_tolerance": 1e-10,
  "low_z_step": 0.05,
  "low_z_max": 2.5,
  "add_prefix": true,
  "prefix": "tfa",
  "add_timestamp": true,
  "timestamp_format": "%Y%m%d_%H%M%S",
  "add_guid": false
}
```

`shape_tolerance` checks that `E_X(0) = 1`. `normalization_tolerance` checks
that the normalized history satisfies `H_X(0) = H0_X`. The low-redshift output
grid is controlled by `low_z_step` and `low_z_max`, with additional high-z
samples reaching the acoustic scale. The naming fields define the run-folder
prefix and timestamp format.

The export gate is:

```json
"export_gate": {
  "enabled": true,
  "accepted_bands": ["STRICT", "LOOSE_2S", "LOOSE_3S"],
  "on_rejected": "failure_report_only"
}
```

When enabled, the gate allows normalized-history products only for routes whose
derived `H0_X` falls in one of the accepted bands. Rejected routes still produce
the run summary and failure/report metadata, but gated products and downstream
diagnostics are skipped.

## Physical Guard Contract

```json
"physics_guards": {
  "canonical_w_floor": -1.0,
  "canonical_tolerance": 1e-8,
  "thawing_late_z_max": 5.0,
  "thawing_monotonic_tolerance": 1e-8,
  "phantom_crossing_tolerance": 1e-8,
  "bbn_z": 1000000000.0,
  "bbn_omega_phi_bound": 0.045
}
```

The guard validator uses this block to check canonical non-phantom behavior,
late-time thawing monotonicity, phantom-crossing status, and the scalar density
fraction at BBN. The BBN check is evaluated at `bbn_z` against
`bbn_omega_phi_bound`.

## Diagnostic Switches

```json
"bao_validator": {
  "enabled": true
},
"rsd_validator": {
  "enabled": true
}
```

These switches enable or disable non-fatal downstream diagnostics. If disabled,
the corresponding validator records a skip and the hub can still return `OK` if
the acoustic and guard stages succeed.

The BAO validator uses the bundled DESI DR2 ALL GCcomb data vector and full
covariance matrix under `data/desi_bao_dr2/`. It computes
`D_H/r_d`, `D_M/r_d`, and `D_V/r_d` using the route's own drag-epoch ruler
`r_drag_Mpc` from the acoustic summary.

The RSD validator uses the bundled 18-point f-sigma8 gold compilation under
`data/fsigma8_gold/`. It integrates the linear growth equation
against the same normalized `H_X(z)` history and reports `f*sigma8`,
`sigma8_X`, and residual summaries.

## Execution and Trace Contract

```json
"execution": {
  "debug_print": false,
  "trace_enabled": true,
  "trace_dir": "../tfa-run-logs",
  "trace_filename_prefix": "tfa-run",
  "safe_runner_returns_error_object": true
}
```

`trace_dir` is resolved relative to the settings file location. The default
path writes JSON-lines traces to the repository-level `tfa-run-logs/`
directory. Trace files record execution phases and diagnostics useful for
debugging; the run folder and `run_results_summary.json` remain the primary
scientific audit record.

## Reproducibility Behavior

Each run folder contains:

```text
environment-settings.json
run_results_summary.json
trajectory.csv
expansion_history_shape.csv
expansion_history_h0x_normalized.csv
w_of_z.csv
physics_guards.csv
bao_results_per_datum.csv
rsd_results_per_datum.csv
plots and diagnostic figures
```

Some files are gated. For example, normalized histories and BAO/RSD products are
not emitted when the export gate rejects the route.

The frozen `environment-settings.json` is the exact input contract for that
run. The `run_results_summary.json` file links the contract to derived values:
`H0_X`, band label, acoustic quantities, guard verdicts, BAO summaries, RSD
summaries, and specialist call status.

## Settings Metadata

The `schema` block records the settings-file identity and the script versions
expected by this release:

| Version field | Meaning |
|---|---|
| `schema.settings_file_version` | Version of this JSON file's values and documented defaults. |
| `schema.tfa_package_release` | TFA package release associated with this settings file. |
| `schema.compatible_scripts` | Compact list of active script names and versions expected to consume this contract. |

Current file values:

```text
settings_file_version = 1.0.0
tfa_package_release = 0.0.2
```
