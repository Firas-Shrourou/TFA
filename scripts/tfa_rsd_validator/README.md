# tfa_rsd_validator Approved Versions

| Version | Build | API | TFA release | Folder | Status |
|---|---:|---:|---:|---|---|
| `0.1.1` | `0001` | `0.1` | `0.0.6` | `v0.1.1-build.0001/` | candidate |
| `0.1.0` | `0001` | `0.1` | `0.0.2` | `v0.1.0-build.0001/` | previous build |

`0.1.0` — initial release. Integrates the linear growth ODE against each
route's H_X(z), computes f·σ₈(z), and compares against an 18-point gold
compilation of RSD measurements. Complements the BAO validator: BAO tests
geometry (distances), RSD tests dynamics (structure growth).

---

## What it computes

For each datum at z_eff from the gold compilation:

```
omega_m_x   = Omega_m0 * (H0_ref / H0_X)^2      [route's physical matter density]

Growth ODE:   D'' + (3/a + d lnH/da) D' = 1.5 * omega_m_x * (H0_X/H(a))^2 / a^5 * D
Initial cond: D(a_ini) = a_ini,  dD/da = 1.0   [EdS approximation at z_start = 10]
Solver:       DOP853, rtol=1e-10, atol=1e-12, dense_output=True

Two integrations: branch H_X(z) and ΛCDM reference H_ΛCDM(z) = H0_X*sqrt(...)

growth_ratio   = D_X(a=1) / D_ΛCDM(a=1)
sigma8_X       = 0.8111 * growth_ratio              [Planck 2018 σ₈ anchor]

f_X(z)         = a * (dD/da) / D                    [growth rate at z_eff]
fsigma8_model  = f_X(z) * 0.8111 * D_X(z) / D_ΛCDM(a=1)

chi²           = sum( (model_i - obs_i)^2 / sigma_i^2 )   [diagonal cov]
```

The validator interpolates `log(H_X)` against `log1p(z)` with PCHIP using
`trajectory.csv`. The trajectory must agree with the acoustic normalization
and cover the derivative stencil through `z=10.00110011`. The maximum
supported gap around the growth interval is 0.04 in `log1p(z)`. The
interpolation stays within the saved trajectory.

## Gating and failures

RSD skips when disabled in settings or when the recorded acoustic export
decision rejects the route. For accepted routes the normalized-history CSV
provides a normalization check. It must have at least two data rows, including
a row at `z=0`. The acoustic anchor must contain `r_s_Mpc`. Missing or invalid required inputs produce a non-fatal RSD error.

## Bundled sample verification

Four bundled routes produce RSD outputs under their supplied settings.
The [package verification table](../../README.md#verification-snapshot)
reports the candidate results.

## Outputs written to run folder

| File | Description |
|---|---|
| `rsd_results_per_datum.csv` | 18 rows: z_eff, survey, observed, sigma, model, residual, pull, datum_status, f_X, sigma8_X, D_X_norm, growth_ratio |
| `rsd_pulls.png` + `.pdf` | Pull bar chart (same style as `bao_pulls`) |
| `rsd_growth.png` + `.pdf` | Continuous (f·σ₈)_X(z) curve + ΛCDM reference + data points |

---

## run_results_summary.json enrichment

Under `results["rsd_validator"]`:

```json
{
  "status": "OK",  "script": {...},
  "dataset_label": "fsigma8_gold_compilation",  "datum_count": 18,
  "sigma8_reference": 0.8111,
  "sigma8_X": <float>,
  "growth_ratio_D_X_over_D_LCDM": <float>,
  "chi2": <float>,  "dof": 18,  "reduced_chi2": <float>,
  "max_abs_pull": <float>,
  "n_within_1sigma": <int>,  "n_within_2sigma": <int>,
  "n_within_3sigma": <int>,  "n_outside_3sigma": <int>,
  "rsd_results_per_datum_csv": "rsd_results_per_datum.csv",
  "rsd_pulls_plot": "rsd_pulls.png",
  "rsd_growth_plot": "rsd_growth.png",
  "growth_z_start": 10.0,
  "growth_history_file": "trajectory.csv",
  "growth_history_interpolation": "PCHIP(log1p(z), log(H_X))",
  "growth_history_z_required": 10.001100110011,
  "ode_solver": "DOP853"
}
```

---

## Entry point

```python
from tfa_rsd_validator import run_rsd_validator

code, desc = run_rsd_validator(run_folder)
```

Called by `tfa_common` as the fifth specialist. Failure is **non-fatal**.

---

## Settings

```json
"user_adjustable": {
  "rsd_validator": {
    "enabled": true
  }
}
```

---

## Dependencies

`numpy`, `scipy` (DOP853, PchipInterpolator), `matplotlib`. No TFA specialist
imports beyond reading run folder files.

---

## Bundled data

18-point f·σ₈ gold compilation (Perivolaropoulos & Skara 2020, PRD 102, 063542):

```
TFA-package/data/fsigma8_gold/
    fsigma8_gold_mean.txt     18 rows: z_eff, fsigma8_obs, sigma, survey
    fsigma8_gold_cov.txt      18×18 diagonal covariance (sigma_i^2 on diagonal)
```

Located at runtime by walking up from `__file__` until `TFA-package/data/fsigma8_gold/`
is found — same walk-up pattern as the BAO validator.

Surveys: 2MTF, 6dFGRS, SDSS velocities, SDSS-MGS, 2dFGRS, GAMA, WiggleZ (4 bins),
SDSS-LRG, BOSS-DR12 (3 bins), SDSS-CMASS, eBOSS-ELG, FastSound, eBOSS-QSO.
All measurements are from independent surveys → diagonal covariance.
