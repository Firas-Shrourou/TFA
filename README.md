# Thawing Field Analyzer (TFA)

*A Python package for analyzing thawing scalar-field routes after acoustic
normalization.*

Thawing Field Analyzer (TFA) is an open-source Python package for reproducible,
route-level analysis of canonical thawing scalar-field dark energy.

A thawing route is specified by a scalar potential `V_X(phi)`, its field-space
derivative, and frozen initial field data. TFA integrates the homogeneous
Klein-Gordon system in a flat FLRW background, derives the scalar trajectory
and dimensionless expansion shape, computes the route's required Hubble
normalization from the CMB acoustic scale, and then evaluates physical and
observational diagnostics on the same normalized history.

The package is intended for model exploration, benchmark generation, and the
preparation of traceable diagnostic material for thawing scalar-field studies.

## Why TFA exists

Thawing scalar-field backgrounds are not defined by a closed-form equation of
state. Their trajectory, equation of state, scalar density fraction, and
expansion history arise together from the scalar potential, initial field state,
Klein-Gordon evolution, and Friedmann closure. A route therefore has to be
integrated before its observational consequences can be assessed.

That integration produces a dimensionless expansion shape `E_X(z)`, but not yet
an observation-ready Hubble history. Distance measures, acoustic quantities,
BAO ratios, growth histories, and plots all require an absolute Hubble scale.
If that scale is imported externally, downstream calculations can become
internally inconsistent: the same scalar-generated `E_X(z)` evaluated with
different Hubble constants can imply different distances, sound horizons, and
growth predictions.

TFA addresses this by computing, in closed form, the route-specific Hubble
constant `H0_X` that the route requires in order to reproduce the observed
CMB acoustic angle under a fixed, sourced early-universe anchor. The
normalized history

```text
H_X(z) = H0_X * E_X(z)
```

then becomes the single background used by all downstream modules.

## What the pipeline does

For each route, TFA performs the following chain:

```text
V_X(phi), initial field data
-> scalar ODE integration
-> E_X(z)
-> required normalization H0_X
-> H_X(z)
-> physics guards
-> BAO diagnostics
-> RSD diagnostics
-> density-sector diagnostics
-> CPL fidelity audit
-> CSV, JSON, and plot exports
```

The physics-guard layer checks canonical thawing behavior, including
non-phantom evolution, thawing monotonicity, phantom-crossing status, and the
scalar density fraction at Big Bang Nucleosynthesis.

The BAO validator computes distance quantities from the route's own normalized
history and drag-epoch sound horizon, then compares the resulting ratios with
the bundled DESI DR2 BAO data vector.

The RSD validator evolves the linear growth factor inside the same `H_X(z)`,
computes `f_sigma8(z)`, and evaluates residuals against an 18-point
redshift-space distortion compilation.

The density validator is strictly CPL-free and non-gated: it scores the
route's `H0_X` against the DESI DR2 w0waCDM reference (the band verdict as a
continuous z-score), reports the exact dark-energy density evolution
`f_DE(z) = rho_phi(z)/rho_phi(0)`, and records thawing-strength route
properties. It runs for excluded routes too, where the pull quantifies how
excluded they are.

The CPL fidelity validator audits CPL without adopting it: it fits the best
`(w0, wa)` to the route's exact `w(z)` and reports that stand-in's errors,
including the closed-form phantom audit -- the best-fit CPL of every thawing
route crosses `w = -1`, entering a sector the canonical field can never
reach. No TFA component consumes the fitted values.

Every completed run is written as a timestamped folder containing the frozen
input configuration, trajectory and expansion tables, per-datum residual
tables, a machine-readable summary JSON record, and exported plots.

## Repository contents

This repository contains the public TFA package:

- `run_tfa.py`, `run_tfa.bat`, and `run_tfa.sh`: package-root launchers.
- `tfa-environment-settings.json`: the user-facing input contract.
- `sample-routes/`: eight preconfigured WLI/WQI benchmark routes.
- `scripts/`: approved specialist scripts and utilities.
- `data/`: local BAO and RSD reference data used by the validators.
- `figures/`: sample plot outputs used by the paper examples.
- `docs/`: public module and utility documentation.
- `RELEASE-NOTES.md`: release history and script-build changes.

Clone or archive the repository as a complete folder so that launchers,
settings, sample routes, documentation, scripts, and validator data remain
together.

## Documentation

- `docs/settings-reference.md`: complete guide to
  `tfa-environment-settings.json`.
- `docs/run-summary-reference.md`: field-by-field guide to
  `run_results_summary.json`.
- `docs/csv-outputs-reference.md`: guide to the CSV files written into each run
  folder.
- `docs/plots-reference.md`: guide to plot products and the sample plot
  gallery.
- `docs/module-reference.md`: public behavior of the active TFA modules.
- `docs/summary-combiner.md`: how to combine many run summaries into one CSV.
- `RELEASE-NOTES.md`: release history and approved script-build changes.

## Requirements

TFA requires Python 3 and:

- `numpy`
- `scipy`
- `matplotlib`

The launchers check for these packages and attempt to install missing
dependencies before a run starts. In managed or offline environments, install
the dependencies in advance.

On Windows, set UTF-8 mode before running TFA:

```powershell
$env:PYTHONUTF8 = "1"
```

## Quick start

From the repository/package root:

```powershell
$env:PYTHONUTF8 = "1"
python run_tfa.py
```

On Windows, you can also run:

```powershell
.\run_tfa.bat
```

On Unix-like shells:

```bash
./run_tfa.sh
```

The package-root launcher reads `tfa-environment-settings.json` and writes a
timestamped run folder under `results/`.

## Configure a route

Edit `tfa-environment-settings.json`, especially the
`user_adjustable.potential` block:

- `benchmark_id`
- `V_of_phi`
- `dV_dphi`
- `parameters`
- `initial_phi`
- `initial_phi_N`
- `user_remarks`

Potential expressions are NumPy-compatible expression strings. The settings
contract is documented in `docs/settings-reference.md`.

## Run a sample route

The `sample-routes/` directory contains self-contained preconfigured routes.
Each sample has its own settings file and matching launchers, so it can be run
without modifying the package-root settings file.

Example from the package root on Windows:

```powershell
.\sample-routes\WLI_3\windows_run_WLI_3.bat
```

On Unix-like shells:

```bash
./sample-routes/WLI_3/unix_run_WLI_3.sh
```

Sample outputs are written to that sample folder's own `results/` subfolder.

## Demonstration routes

The release includes eight source-backed demonstration routes: two Warm
Quintessential Inflation markers and six Warm Little Inflaton markers.

| Benchmark | Family | V(phi) | Key parameters |
|---|---|---|---|
| `WQI_F765` | WQI | `3*Omega_DE*(phi_F**4+M_Mp**4)/(phi**4+M_Mp**4)` | `phi_F=7.65`, `M_Mp=1.794e-13` |
| `WQI_F680` | WQI | same as above | `phi_F=6.80`, `M_Mp=1.794e-13` |
| `WLI_1` | WLI | `3*Omega_DE*(phi_inf/phi)**alpha` | `alpha=1.0`, `phi_inf=1.30` |
| `WLI_2` | WLI | same as above | `alpha=1.5`, `phi_inf=1.30` |
| `WLI_3` | WLI | same as above | `alpha=2.0`, `phi_inf=1.30` |
| `WLI_4` | WLI | same as above | `alpha=1.0`, `phi_inf=1.35` |
| `WLI_5` | WLI | same as above | `alpha=1.5`, `phi_inf=1.35` |
| `WLI_6` | WLI | same as above | `alpha=2.0`, `phi_inf=1.35` |

For all WLI routes:

```text
dV_dphi = -alpha*3*Omega_DE*(phi_inf/phi)**alpha/phi
initial_phi = phi_inf
initial_phi_N = 0.0
```

For all WQI routes:

```text
dV_dphi = -4*phi**3*3*Omega_DE*(phi_F**4+M_Mp**4)/(phi**4+M_Mp**4)**2
initial_phi = phi_F
initial_phi_N = 0.0
```

## Output products

Each completed run can include:

- `run_results_summary.json`: compact machine-readable audit record.
- frozen `environment-settings.json`: the exact input contract used by the run.
- `trajectory.csv`: full scalar integration history.
- `expansion_history_shape.csv`: dimensionless `E_X(z)`.
- `expansion_history_h0x_normalized.csv`: normalized `H_X(z)`.
- `w_of_z.csv`: scalar equation-of-state history.
- `physics_guards.csv`: row-level physical guard record.
- `bao_results_per_datum.csv`: BAO residual table when BAO is enabled.
- `rsd_results_per_datum.csv`: RSD residual table when RSD is enabled.
- `density_results.csv`: CPL-free density-sector indicators (non-gated).
- `cpl_fidelity_results.csv`: CPL audit indicators and verdict (non-gated).
- PNG/PDF diagnostic plots.

The run folder is the unit of reproducibility. The frozen settings record what
was requested, the summary JSON records what completed, and the CSV and plot
files provide the numerical and visual products behind reported values.

## Combine run summaries

The `tfa_combined_csv_results` utility combines multiple
`run_results_summary.json` files into one CSV and writes a schema-audit sidecar.
It uses only the Python standard library.

From its approved version folder:

```powershell
cd .\scripts\tfa_combined_csv_results\v0.1.0-build.0001
python tfa_combined_csv_results.py examples\tfa_combined_csv_results_config.example.json
```

The utility accepts a JSON config or CSV manifest, flattens nested summary
objects, builds union columns across valid inputs, and records skipped inputs
and schema details in the audit output.

See `docs/summary-combiner.md` for the full utility reference.

## Verification snapshot

The current stack has been verified against all eight bundled benchmark
routes. All runs returned `code=OK` through the full seven-module chain, and
all physics guards passed. `H0_X` is the required normalization; the band is
the classification against the DESI DR2 w0waCDM evaluation bands
(`66.74 +/- 0.56`, mean +/- 1/2/3 sigma); the `H0` pull is the same verdict
as a continuous z-score. BAO/RSD values for the four routes outside the bands
(marked `*`) come from gate-disabled runs of the same contracts; their
degraded BAO fit shows that the acoustic verdict carries real downstream
weight. The table was produced with `tfa_combined_csv_results`.

| Benchmark | H0_X (km/s/Mpc) | DESI band | H0 pull | BAO chi2/dof | RSD chi2/dof | sigma8_X |
|---|---:|---|---:|---:|---:|---:|
| `WQI_F765` | 66.210 | STRICT | -0.95 | 3.69 | 1.12 | 0.726 |
| `WQI_F680` | 65.921 | LOOSE_2S | -1.46 | 4.11 | 1.13 | 0.724 |
| `WLI_1` | 65.151 | LOOSE_3S | -2.84 | 5.49 | 1.15 | 0.720 |
| `WLI_2` | 62.916 | EXCLUDED | -6.83 | 11.12* | 1.24* | 0.709* |
| `WLI_3` | 60.390 | EXCLUDED | -11.34 | 21.20* | 1.38* | 0.697* |
| `WLI_4` | 65.289 | LOOSE_3S | -2.59 | 5.23 | 1.15 | 0.721 |
| `WLI_5` | 63.167 | EXCLUDED | -6.38 | 10.33* | 1.23* | 0.710* |
| `WLI_6` | 60.741 | EXCLUDED | -10.71 | 19.48* | 1.36* | 0.698* |

These values are demonstration outputs, not a claim that TFA is a full
parameter-inference framework or a replacement for Boltzmann solvers.

## Engine validation

TFA's engine has been validated against two independent codes. ScalPy, a
dedicated scalar-field cosmology code that integrates the same physics
through a different formulation and solver, reproduces TFA's `w(z)`,
`Omega_phi(z)`, and normalized shape `E(z)` to better than 0.01 percent on
all eight demonstration routes, and the required `H0_X` to within
0.005 km/s/Mpc, with an identical band classification. CLASS, a full
Boltzmann solver fed each route's CPL summary, corroborates the same
admissible/excluded split; its remaining 0.5-2.7 km/s/Mpc offset is located
in the `omega_m` self-consistency convention and is tracked, route by route,
by the `omega_m_residual_pct` field that the engine reports on every run --
the CPL fidelity audit shows the CPL shape itself contributes only
0.002-0.009 km/s/Mpc to the distance scale.

## Scope

TFA occupies a specific niche in the cosmology-tools landscape. General-purpose
Boltzmann solvers and inference frameworks provide broad functionality for CMB
power spectra and posterior sampling. TFA instead provides a compact assessment
layer for researchers who have a specific thawing scalar potential and need to
know, reproducibly, what normalized expansion history it implies, whether that
history satisfies basic canonical-thawing checks, and how its distance and
growth diagnostics compare against late-time data sets.

The current release is scoped to canonical thawing scalar-field histories that
can be expressed through the settings contract. It does not sample posterior
distributions, fit nuisance parameters, or replace a full inference pipeline.

## Versioning

TFA tracks project releases, script versions, script builds, settings schema,
and settings-file versions independently. A project release is a snapshot of
the approved script builds and package files that belong together.

Current approved script stack (TFA project release 0.0.5):

| Script | Version | Build | Role |
|---|---:|---:|---|
| `tfa_common` | `0.9.3` | `0001` | Pipeline orchestration (7-specialist chain) |
| `tfa_core` | `0.1.0` | `0001` | Shared scalar ODE, settings, FLRW, I/O, encoding core |
| `tfa_acoustic_validator` | `0.1.6` | `0001` | ODE integration, required normalization, CSV exports |
| `tfa_physics_guard_validator` | `0.1.5` | `0001` | Canonical thawing guard checks |
| `tfa_plot_exporter` | `0.1.1` | `0001` | Diagnostic plot generation |
| `tfa_bao_validator` | `0.1.1` | `0001` | DESI DR2 BAO diagnostics |
| `tfa_rsd_validator` | `0.1.0` | `0001` | RSD growth diagnostics |
| `tfa_density_validator` | `0.1.0` | `0001` | CPL-free density-sector diagnostics (non-gated) |
| `tfa_cpl_fidelity_validator` | `0.1.0` | `0001` | CPL audit: error report and phantom audit (non-gated) |
| `tfa_combined_csv_results` | `0.1.0` | `0001` | Summary aggregation utility |

See `RELEASE-NOTES.md` for the full release history.

## Archive

Zenodo DOI for all versions:

```text
10.5281/zenodo.20572379
```

## License

TFA is released under the MIT license. See `LICENSE`.
