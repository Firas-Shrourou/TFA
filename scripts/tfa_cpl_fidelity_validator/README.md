# tfa_cpl_fidelity_validator

CPL compression audit. **CPL is audited here, never adopted.** TFA's rule
stands: no (w0, wa) parametrization ever represents a route. This specialist
exists because the community (and CPL-fed pipelines such as CLASS) routinely
consume CPL summaries — so the researcher needs to know, per route, whether
such a summary can be trusted at all, and where it breaks. No TFA component
consumes the fitted (w0, wa); they appear in outputs only with the error
report attached.

## Role

| Aspect | Value |
|---|---|
| Entry point | `run_cpl_fidelity_validator(run_folder) -> (Code, Desc)` |
| Inputs | `run_results_summary.json`, `trajectory.csv`, frozen `environment-settings.json` |
| Gating | **Non-gated** — runs for every completed engine run, including EXCLUDED routes |
| Fatal? | No (non-fatal in the hub chain) |
| Dependency | `tfa_core` only |

## What it computes

1. **Best-fit CPL** to the route's exact w(z): unweighted least squares of
   w(a) on basis {1, (1−a)}, resampled uniformly in a over 0 ≤ z ≤ `fit_z_max`.
   The full sampling strategy is specified in the next section.

## CPL best-fit sampling strategy (specification)

The fit is a deterministic, closed-form linear regression — no iterative
optimizer, no randomness, no data weighting. Reproducible to machine precision
from `trajectory.csv` alone.

1. **Fit variable: the scale factor a, not z.** CPL is *defined* as linear in
   a: `w(a) = w0 + wa (1 − a)`. Fitting in the variable where the model is
   linear makes the least-squares problem exact (2-parameter linear regression
   on basis {1, (1 − a)}), solved in closed form via `np.linalg.lstsq`.
2. **Fit range: 0 ≤ z ≤ `fit_z_max`** (default 3.0), i.e.
   a ∈ [1/(1+`fit_z_max`), 1]. This brackets the redshift range where dark
   energy is dynamically relevant and where the survey data that motivate CPL
   summaries live; the audit then *separately* reports how the fit behaves
   outside the range (the a → 0 asymptote `cpl_w_asymptote = w0 + wa`).
3. **Resampling: 400 points uniform in a** across the fit range, with w
   obtained by linear interpolation of the trajectory's exact w_phi(z). The
   raw trajectory grid is (near-)uniform in e-folds N = ln a — the ODE
   solver's natural variable — which is a *biased* sample density in a-space.
   Fitting on the raw grid would silently weight some epochs more than others;
   uniform-in-a resampling weights the fit evenly across the expansion history,
   in the same variable the CPL basis uses.
4. **Unweighted.** No data covariance enters the fit. Weighting by any survey's
   covariance would make the fitted (w0, wa) dataset-dependent; the audit wants
   the best CPL *the route itself admits*, a route property.
5. **Unconstrained — deliberately.** No w ≥ −1 prior is imposed on the fit.
   The point of the audit is to expose what an unconstrained best fit does
   (this is what a standard CPL pipeline produces): for thawing routes it
   crosses into the phantom sector, which the phantom audit then reports in
   closed form.
6. **Error scans after the fit:** Δw and Δrho_DE are scanned on a dense
   2000-point grid uniform in z over the fit range; the D_M(z*) error is
   integrated on a 2000-point grid uniform in u = ln(1+z) from 0 to z*, with
   the route's 1/E interpolated in log space. The CPL stand-in for the D_M
   comparison shares the route's **own** z = 0 density fractions (Omega_phi(0)
   from the trajectory, radiation rescaled to H0_X, matter by flat closure), so
   the distance error isolates the DE evolution law — the only thing CPL
   changes — rather than a background-budget mismatch.

**Conventions deliberately not used:** fitting in z (CPL is not linear in z);
fitting on the raw e-fold grid (sample-density bias, point 3); covariance-
weighted fits (dataset-dependent, point 4); the tangent expansion
w0 = w(0), wa = −dw/da at a=1 (that is a *route property*, not a global fit —
it is reported by `tfa_density_validator` as `wa_tangent` and serves the
source-paper provenance check).
2. **Infidelity report:** `cpl_dw_max` (max |w_CPL − w_phi|, grows with z and
   thawing strength), `cpl_df_de_max` (max relative rho_DE error), and
   `cpl_dDM_star_pct` — the percent error in D_M(z*) under the CPL stand-in,
   i.e. the acoustic-distance error a CPL-fed pipeline inherits (the per-route
   explainer for the observed CLASS-vs-TFA H0 offset).
3. **Phantom audit (closed form):** the canonical route satisfies w ≥ −1
   always (guard-certified); the best-fit CPL inherits no such protection.
   `w_CPL(a) = w0 + wa(1−a)` crosses w = −1 at `a_c = 1 + (1+w0)/wa`
   (`cpl_z_cross = 1/a_c − 1` if 0 < a_c < 1); the a→0 limit is
   `cpl_w_asymptote = w0 + wa` (< −1 means phantom-in-the-past guaranteed).
   Also `cpl_w_min`, `cpl_phantom_fraction`, `cpl_phantom_flag`. For context,
   `desi_reference_z_cross` reports the DESI reference posterior's own crossing
   (~0.41), computed from the settings `desi_reference` block.
4. **Verdict:** FAITHFUL / MARGINAL / UNFAITHFUL on the `dw_*` / `ddm_*`
   thresholds; any phantom crossing appends `_PHANTOM` and caps the verdict at
   MARGINAL_PHANTOM — a crossing fit can never be FAITHFUL.

Naming: every CPL-derived key is `cpl_*`-prefixed. The physics guard's
`phantom_crossing_ok` certifies the **field**; the `cpl_*` audit exposes the
field's **CPL shadow**. Same criterion, applied to the approximation.

## Outputs

- `cpl_fidelity_results.csv`
- `cpl_fidelity.png/pdf` — top: exact w_phi(z) vs the CPL fit, w = −1 line,
  phantom excursion shaded red, z_cross annotated; bottom: residual
  w_CPL − w_phi showing the growth with z.
- Summary enrichment under `results["cpl_fidelity_validator"]`

## Settings block (`user_adjustable.cpl_fidelity_validator`)

```json
{ "enabled": true, "fit_z_max": 3.0,
  "dw_faithful": 0.01, "dw_marginal": 0.05,
  "ddm_faithful_pct": 0.1, "ddm_marginal_pct": 0.5 }
```

Missing block defaults to the values above (back-compat with frozen settings
older than file version 1.2.0).

## Version history

| Version | Build | Notes |
|---|---|---|
| 0.1.0 | 0001 | Initial release (T004 deliverable 5c: CPL audited-not-adopted). |
