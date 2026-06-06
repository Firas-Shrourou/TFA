# Settings Reference

`tfa-environment-settings.json` is the user-facing input contract for a TFA
run. It defines the scalar route, cosmological priors, acoustic anchor,
integration controls, export policy, physical guard thresholds, diagnostic
switches, and execution trace behavior.

In normal use, edit this file, then run one of the package-root launchers. At
runtime, TFA copies the exact settings file into the timestamped run folder as
`environment-settings.json`. That frozen copy is the audit record used by the
acoustic, guard, plot, BAO, and RSD stages.

## Location

The package-root contract is:

```text
tfa-environment-settings.json
```

The package-root launchers read this file:

```text
run_tfa.py
run_tfa.bat
run_tfa.sh
```

Outputs from package-root runs are written under:

```text
results/
```

The `sample-routes/` folders each contain their own
`tfa-environment-settings.json` file. Those files are fixed examples for the
preconfigured WLI/WQI markers. A sample launcher reads the settings file inside
its own sample folder and writes outputs to that sample folder's `results/`
subfolder.

## Top-level structure

The settings file has three top-level sections:

| Section | Runtime role |
|---|---|
| `user_adjustable` | The active input contract. Runtime code reads this section to define the run. |
| `read_only_hardcoded_defaults` | Reference mirror of expected fields and default values. It documents the contract but is not the active run input. |
| `schema` | Settings-file identity, package release, and compatible script versions. |

For a normal run, make scientific and numerical changes under
`user_adjustable`.

## Runtime sections

The `user_adjustable` object contains:

| Section | Purpose |
|---|---|
| `potential` | Defines the scalar route: route label, potential expression, derivative expression, parameters, initial field state, and notes. |
| `cosmology` | Defines flat-background present-day cosmological values. |
| `acoustic_priors` | Defines the early-time acoustic anchor used to solve for `H0_X`. |
| `planck_h0_bands` | Defines the band labels used to classify the derived `H0_X`. |
| `integration` | Defines the scalar ODE interval and solver tolerances. |
| `export` | Defines output-grid tolerances and run-folder naming behavior. |
| `export_gate` | Defines which acoustic bands are allowed to export normalized histories and downstream diagnostics. |
| `physics_guards` | Defines canonical, thawing, phantom-crossing, and BBN thresholds. |
| `execution` | Defines debug printing and trace-file behavior. |
| `bao_validator` | Enables or disables BAO diagnostics. |
| `rsd_validator` | Enables or disables RSD diagnostics. |

## Defining a scalar route

The most important block is `user_adjustable.potential`:

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
| `benchmark_id` | Human-readable route label copied into output metadata. |
| `V_of_phi` | Expression string for the scalar potential `V_X(phi)`. |
| `dV_dphi` | Expression string for `dV_X/dphi`; analytic derivatives are preferred. |
| `parameters` | Numeric parameters referenced by `V_of_phi` and `dV_dphi`. |
| `initial_phi` | Initial field value. |
| `initial_phi_N` | Initial derivative `dphi/dN`; thawing examples usually use `0.0`. |
| `user_remarks` | Optional note copied into the run summary. It does not affect physics. |

If `dV_dphi` is omitted or empty, the acoustic validator uses a central
finite-difference derivative.

## Expression namespace

Potential expressions are NumPy-compatible numeric strings. They may use:

| Name | Availability |
|---|---|
| `phi` | Current field value supplied by TFA during evaluation. |
| `Omega_DE` | Dark-energy fraction from `cosmology`; if `Omega_DE` is `null`, TFA uses flatness. |
| Parameter names | Every numeric key declared in `potential.parameters`. |
| Math functions | `exp`, `log`, `log10`, `sqrt`, `abs`, `sin`, `cos`, `tan`, `sinh`, `cosh`, `tanh`, `arcsin`, `arccos`, `arctan`, `pi`, and `e`. |

Python builtins are disabled during expression evaluation. Keep expressions as
plain numeric formulas in terms of `phi`, `Omega_DE`, declared parameters, and
the allowed math functions.

## WQI example

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

The bundled WQI markers are `WQI_F680` and `WQI_F765`.

## WLI example

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

The bundled WLI markers use `alpha = 1.0, 1.5, 2.0` crossed with
`phi_inf = 1.30, 1.35`.

These examples are demonstrations of the input and output contract. They are
not a statistical fit or a claim of physical ranking.

## Cosmology

```json
"cosmology": {
  "Omega_m0": 0.3152,
  "Omega_r0": 0.0000918,
  "Omega_DE": null,
  "H0_ref_kms": 67.36,
  "c_kms": 299792.458
}
```

`Omega_m0` and `Omega_r0` define the present matter and radiation fractions. If
`Omega_DE` is `null`, TFA enforces flatness:

```text
Omega_DE = 1 - Omega_m0 - Omega_r0
```

`H0_ref_kms` is the reference Hubble constant used for comparisons and
metadata. `c_kms` is the speed of light in km/s.

## Acoustic priors and H0 bands

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

The resulting `H0_X` is classified by `planck_h0_bands`:

```json
"planck_h0_bands": {
  "strict": [66.82, 67.9],
  "loose_2s": [66.28, 68.44],
  "loose_3s": [65.74, 68.98]
}
```

Band labels are assigned narrowest first:

```text
STRICT
LOOSE_2S
LOOSE_3S
EXCLUDED
```

## Integration

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

This controls the homogeneous scalar-field ODE solve. The default run evolves
from high redshift to the present using SciPy's `DOP853` solver with dense
output enabled.

## Export and gating

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
that `H_X(0) = H0_X`. The low-redshift output grid is controlled by
`low_z_step` and `low_z_max`. The naming fields define the run-folder prefix
and timestamp format.

The export gate is:

```json
"export_gate": {
  "enabled": true,
  "accepted_bands": ["STRICT", "LOOSE_2S", "LOOSE_3S"],
  "on_rejected": "failure_report_only"
}
```

When enabled, normalized-history products and downstream diagnostics are written
only for routes whose derived `H0_X` falls in an accepted band. Rejected routes
still produce summary and failure metadata.

## Physics guards

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

The guard validator checks canonical non-phantom behavior, late-time thawing
monotonicity, phantom-crossing status, and scalar density fraction at Big Bang
Nucleosynthesis. The BBN check is evaluated at `bbn_z` against
`bbn_omega_phi_bound`.

## BAO and RSD switches

```json
"bao_validator": {
  "enabled": true
},
"rsd_validator": {
  "enabled": true
}
```

These switches enable or disable downstream diagnostics. If disabled, the skip
is recorded and the hub can still return `OK` if the acoustic and guard stages
succeed.

The BAO validator uses bundled DESI DR2 data under:

```text
data/desi_bao_dr2/
```

It computes `D_H/r_d`, `D_M/r_d`, and `D_V/r_d` using the route's own
drag-epoch ruler from the acoustic summary.

The RSD validator uses the bundled 18-point `f_sigma8` compilation under:

```text
data/fsigma8_gold/
```

It integrates the linear growth equation against the same normalized `H_X(z)`
history and reports `f_sigma8`, `sigma8_X`, and residual summaries.

## Execution traces

```json
"execution": {
  "debug_print": false,
  "trace_enabled": true,
  "trace_dir": "../tfa-run-logs",
  "trace_filename_prefix": "tfa-run",
  "safe_runner_returns_error_object": true
}
```

`trace_dir` is resolved relative to the settings file location. Trace files
record execution phases and diagnostics for debugging. The run folder and
`run_results_summary.json` remain the primary scientific audit record.

## Reproducibility

Each run folder contains the exact frozen settings used by that run:

```text
environment-settings.json
```

Typical output products include:

```text
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

Some files are gated. For example, normalized histories and BAO/RSD products
are not emitted when the export gate rejects the route.

## Schema metadata

The `schema` block records the settings-file identity and script versions
expected by this release:

| Field | Meaning |
|---|---|
| `schema.settings_file_version` | Version of this JSON file's values and documented defaults. |
| `schema.tfa_package_release` | TFA package release associated with this settings file. |
| `schema.compatible_scripts` | Active script names and versions expected to consume this contract. |

Current values:

```text
settings_file_version = 1.0.2
tfa_package_release = 0.0.4
```
