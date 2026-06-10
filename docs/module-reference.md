# TFA Module Reference

This document summarizes the public behavior of the active TFA pipeline
modules. Release history and superseded builds are documented separately in
`RELEASE-NOTES.md`.

## Pipeline overview

The package-root launcher calls the approved `tfa_common` build. That hub reads
the package-root `tfa-environment-settings.json`, creates a timestamped run
folder, freezes the input settings into that folder, initializes
`run_results_summary.json`, and runs the active specialist modules in sequence.

The current pipeline is:

```text
tfa_common
-> tfa_acoustic_validator         (fatal on failure)
-> tfa_physics_guard_validator    (fatal on failure)
-> tfa_plot_exporter              (non-fatal)
-> tfa_bao_validator              (non-fatal, gated)
-> tfa_rsd_validator              (non-fatal, gated)
-> tfa_density_validator          (non-fatal, non-gated)
-> tfa_cpl_fidelity_validator     (non-fatal, non-gated)
```

Every specialist imports the shared `tfa_core` module and never another
specialist. Each specialist reads the files its predecessors wrote, performs
one job, writes its products, and returns a `(code, desc)` tuple to the hub
before the next specialist starts. The physics verdict (`H0_X`, band) belongs
to the first two modules alone; the remaining modules are diagnostics whose
failure is recorded without changing the verdict.

Two execution policies shape what a run produces. *Gated* modules (BAO, RSD,
and two of the plots) require the normalized-history CSV, which the export
gate skips by default for routes classified `EXCLUDED`; disabling the gate in
the input contract yields full diagnostics for any route. *Non-gated* modules
(density, CPL audit) need only `trajectory.csv` and the summary, which every
completed run possesses, so they run for excluded routes too -- where their
content is most informative.

The run folder is the unit of reproducibility: it contains the frozen input
contract, all numerical products, the summary record, and the plots.

## tfa_core

`tfa_core` is the shared utility module: the canonical scalar ODE and
integrator, settings resolution, the sandboxed potential builder, FLRW
distance helpers, JSON I/O with atomic writes, the run trace, structured
errors, and the encoding policy (ASCII console, UTF-8 without BOM on disk).
It has no entry point of its own; every specialist imports it.

Current approved build:

```text
scripts/tfa_core/v0.1.0-build.0001/
```

## tfa_common

`tfa_common` is the pipeline hub. It resolves approved specialist builds,
creates the run folder, freezes settings, calls each specialist in-process,
and records the call log in `run_results_summary.json`.

Current approved build:

```text
scripts/tfa_common/v0.9.3-build.0001/
```

Primary entry point:

```python
import tfa_common as tfa

result = tfa.run()
# result is a dict: result["code"], result["desc"], result["run_folder"],
# result["calls"], result["summary_path"]
```

The package-root launchers call this entry point automatically.

## tfa_acoustic_validator

`tfa_acoustic_validator` is the scalar-field engine and acoustic normalizer.
It rebuilds the potential from the frozen settings (via `tfa_core`),
integrates the homogeneous scalar route once, normalizes the dimensionless
expansion shape to `E_X(0) = 1`, and computes the required normalization
`H0_X` in closed form -- the value of `H0` the route requires in order to
reproduce the observed CMB acoustic angle under the sourced early-universe
anchor (Planck `r_star = 144.39 Mpc`, `100*theta_star = 1.0411`). The
normalized history `H_X(z) = H0_X * E_X(z)` reproduces the acoustic target
distance by construction.

Current approved build:

```text
scripts/tfa_acoustic_validator/v0.1.6-build.0001/
```

Public entry point:

```python
from tfa_acoustic_validator import run_acoustic_validator

code, desc = run_acoustic_validator(run_folder)
```

Main outputs:

| File | Gated | Contents |
|---|---|---|
| `trajectory.csv` | no | Full scalar trajectory and state history (`N`, `z`, `a`, `phi`, `dphi_dN`, `E_X`, `H_X`, `w_phi`, `Omega_phi`). |
| `expansion_history_shape.csv` | yes | Dimensionless route shape `E_X(z)`. |
| `expansion_history_h0x_normalized.csv` | yes | Normalized Hubble history `H_X(z)`. |
| `w_of_z.csv` | yes | Scalar equation-of-state history on the export grid. |
| `run_results_summary.json` | no | Acoustic anchor, `H0_X`, band, energy fractions, and the `omega_m` self-consistency residual. |

The summary block also records the sourced drag-epoch ruler
`r_drag_Mpc = 147.05` consumed by the BAO validator, the computed
Eisenstein--Hu cross-check values for both horizons, and the
`energy_fractions` block (present-day budget, equality redshifts, and
`omega_m_residual_pct`).

## tfa_physics_guard_validator

`tfa_physics_guard_validator` checks whether the integrated route satisfies
the package's physical-admissibility guards. It reads `trajectory.csv`,
rebuilds the potential via `tfa_core`, applies the configured thresholds,
writes a long-form guard table, and enriches the summary JSON.

Current approved build:

```text
scripts/tfa_physics_guard_validator/v0.1.5-build.0001/
```

Public entry point:

```python
from tfa_physics_guard_validator import run_physics_guard_validator

code, desc = run_physics_guard_validator(run_folder)
```

Guards:

| Guard | Purpose |
|---|---|
| `canonical` | Checks that `w_phi >= -1` everywhere (canonical floor). |
| `thawing` | Checks late-time thawing monotonicity (`z <= 5`). |
| `phantom_crossing` | Records phantom-crossing status of the field. |
| `BBN` | Checks the scalar density fraction at `z = 1e9` against the bound (frozen-field evaluation). |

Main output: `physics_guards.csv`.

## tfa_plot_exporter

`tfa_plot_exporter` generates diagnostic plots from run-folder products. It is
a consumer module: it does not recompute the scalar dynamics.

Current approved build:

```text
scripts/tfa_plot_exporter/v0.1.1-build.0001/
```

Public entry point:

```python
from tfa_plot_exporter import run_plot_exporter

code, desc = run_plot_exporter(run_folder)
```

Plot products:

| File | Source data | Gated |
|---|---|---|
| `w_of_z.png/pdf` | `trajectory.csv` | no |
| `Omega_phi.png/pdf` | `trajectory.csv` | no |
| `phase_portrait.png/pdf` | `trajectory.csv` | no |
| `energy_fractions.png/pdf` | `trajectory.csv` + summary block | no |
| `H_of_z.png/pdf` | `expansion_history_h0x_normalized.csv` | yes |
| `delta_H.png/pdf` | `expansion_history_h0x_normalized.csv` | yes |

## tfa_bao_validator

`tfa_bao_validator` evaluates BAO distance diagnostics for a completed run. It
reads the normalized expansion history and the drag-epoch ruler from the
summary, computes the distance ratios, and compares them against the bundled
DESI DR2 ALL GCcomb data (13 points) with the full 13x13 covariance.

Current approved build:

```text
scripts/tfa_bao_validator/v0.1.1-build.0001/
```

Public entry point:

```python
from tfa_bao_validator import run_bao_validator

code, desc = run_bao_validator(run_folder)
```

Computed ratios:

```text
D_H(z) / r_drag      D_M(z) / r_drag      D_V(z) / r_drag
```

Outputs: `bao_results_per_datum.csv`, `bao_pulls.png/pdf`, BAO summary
statistics in the summary JSON. Gated: skips with an explanatory note when the
export gate rejected the route. The bundled BAO data live in
`data/desi_bao_dr2/`.

## tfa_rsd_validator

`tfa_rsd_validator` evaluates growth-rate diagnostics. It reads
`expansion_history_h0x_normalized.csv`, evolves the linear growth factor
inside the route's normalized history, computes `f_sigma8(z)`, and compares
the route against the bundled 18-point compilation (diagonal covariance,
`sigma8_ref = 0.8111`).

Current approved build:

```text
scripts/tfa_rsd_validator/v0.1.0-build.0001/
```

Public entry point:

```python
from tfa_rsd_validator import run_rsd_validator

code, desc = run_rsd_validator(run_folder)
```

Outputs: `rsd_results_per_datum.csv`, `rsd_pulls.png/pdf`,
`rsd_growth.png/pdf`, RSD summary statistics. Gated. The bundled RSD data
live in `data/fsigma8_gold/`.

## tfa_density_validator

`tfa_density_validator` provides CPL-free density-sector diagnostics. It is
non-gated: it reads `trajectory.csv` and the summary, both present for every
completed run, so it also runs for `EXCLUDED` routes -- where its primary
output quantifies *how* excluded they are.

The only pull it computes is `H0_X` against the `desi_reference` block of the
input contract (DESI DR2 w0waCDM, DESI+CMB+DESY5: `66.74 +/- 0.56`), reported
as a z-score with a sigma class. The DESI `Omega_m` is quoted reference-only:
an `Omega_m` pull would double-count the `H0` pull because the route, Planck,
and DESI all share the same physical matter density. The module also echoes
the engine's energy budget (never recomputing `Omega_m` by a new convention),
rechecks flat closure at `z = 0`, reports the exact dark-energy density
evolution `f_DE(z) = rho_phi(z)/rho_phi(0)` with distance-from-Lambda markers
(LCDM is `f_DE = 1`), reports thawing-strength route properties (`1 + w(0)`,
the thaw redshift, and `-dw/da` at `a = 1` -- a derivative of the exact route,
not a fit), and cross-checks that the contract's `h0_bands` still equal the
`desi_reference` mean +/- 1/2/3 sigma (`bands_consistent`).

Current approved build:

```text
scripts/tfa_density_validator/v0.1.0-build.0001/
```

Public entry point:

```python
from tfa_density_validator import run_density_validator

code, desc = run_density_validator(run_folder)
```

Outputs: `density_results.csv`, `density_fde.png/pdf`, summary block
`results["density_validator"]`.

## tfa_cpl_fidelity_validator

`tfa_cpl_fidelity_validator` audits the CPL compression of a route. CPL is
audited here, never adopted: no TFA component consumes the fitted
`(w0, wa)`, which appear in the outputs only with their error report
attached. Non-gated.

The module fits the best CPL to the route's exact `w(z)` (unweighted least
squares in the scale factor over `0 <= z <= fit_z_max`), then measures the
errors of that stand-in: the maximum `w(z)` error and where it occurs, the
maximum relative `rho_DE` error, and the percent error in the comoving
distance to recombination -- the acoustic-distance error a CPL-fed pipeline
inherits. It also performs the closed-form phantom audit: the best-fit CPL of
a thawing route crosses `w = -1` at `a_c = 1 + (1 + w0)/wa`, entering the
phantom sector the canonical field can never reach. Reported fields include
`cpl_z_cross`, `cpl_w_min`, `cpl_phantom_fraction`, the `a -> 0` asymptote
`cpl_w_asymptote = w0 + wa`, and `cpl_phantom_flag`. The verdict is
`FAITHFUL` / `MARGINAL` / `UNFAITHFUL` on configurable thresholds; any
phantom crossing appends `_PHANTOM` and caps the verdict at
`MARGINAL_PHANTOM`. The physics guard certifies that the *field* never
crosses; this module exposes whether the field's *CPL shadow* does.

Current approved build:

```text
scripts/tfa_cpl_fidelity_validator/v0.1.0-build.0001/
```

Public entry point:

```python
from tfa_cpl_fidelity_validator import run_cpl_fidelity_validator

code, desc = run_cpl_fidelity_validator(run_folder)
```

Outputs: `cpl_fidelity_results.csv`, `cpl_fidelity.png/pdf`, summary block
`results["cpl_fidelity_validator"]`.

## tfa_combined_csv_results

`tfa_combined_csv_results` is the approved standalone multi-run utility
(Python standard library only; outside the specialist chain). Given a JSON
config or CSV manifest listing run folders, it reads each
`run_results_summary.json`, flattens every nested field, takes the union of
columns across all runs, and writes one combined CSV plus a schema-audit
sidecar. See `docs/summary-combiner.md`.

Current approved build:

```text
scripts/tfa_combined_csv_results/v0.1.0-build.0001/
```
