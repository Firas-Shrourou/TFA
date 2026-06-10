# tfa_rsd_validator Approved Versions

| Version | Build | API | TFA release | Folder | Status |
|---|---:|---:|---:|---|---|
| `0.1.0` | `0001` | `0.1` | `0.0.2` | `v0.1.0-build.0001/` | approved |

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

H_X(z) is read from `expansion_history_h0x_normalized.csv` and interpolated
with `PchipInterpolator`. For z beyond the CSV range (z > 2.5), a
matter+radiation-only extension is applied.

---

## Gating (three gates, all non-fatal)

1. `user_adjustable.rsd_validator.enabled` — if false, skip
2. `expansion_history_h0x_normalized.csv` must exist (export gate accepted route)
3. `results["acoustic_validator"]["acoustic_anchor"]["r_s_Mpc"]` must be present
   (sentinel confirming acoustic validator ran; r_s_Mpc not used in computation)

Silent skip on any condition; recorded under `results["rsd_validator"]`.

---

## Verified results (v0.1.0, 18-point gold compilation)

ΛCDM baseline: **chi² ≈ 18 (reduced ≈ 1.0)** for a perfectly calibrated route.
σ₈ anchor: 0.8111 (Planck 2018).

| Route | H0_X | Band | RSD chi² | χ²/dof | Within 2σ | sigma8_X | growth_ratio |
|---|---|---|---|---|---|---|---|
| WQI_F765 (φ_F=7.65) | 67.4780 | STRICT | **27.2** | **1.51** | 16/18 | 0.7052 | 0.8694 |
| WQI_F680 (φ_F=6.80) | 67.5085 | STRICT | **29.8** | **1.66** | 16/18 | 0.6988 | 0.8615 |
| WLI_4 (α=1.0, φ∞=1.35) | 67.5822 | STRICT | 36.5 | 2.03 | 15/18 | 0.6850 | 0.8445 |
| WLI_1 (α=1.0, φ∞=1.30) | 67.5981 | STRICT | 38.2 | 2.12 | 15/18 | 0.6820 | 0.8408 |
| WLI_5 (α=1.5, φ∞=1.35) | 67.8331 | STRICT | 67.1 | 3.73 | 11/18 | 0.6413 | 0.7906 |
| WLI_2 (α=1.5, φ∞=1.30) | 67.8653 | STRICT | 71.4 | 3.97 | 11/18 | 0.6363 | 0.7845 |
| WLI_6 (α=2.0, φ∞=1.35) | 68.1505 | LOOSE_2S | 113.5 | 6.30 | 10/18 | 0.5956 | 0.7343 |
| WLI_3 (α=2.0, φ∞=1.30) | 68.2009 | LOOSE_2S | 120.9 | 6.72 | 9/18 | 0.5893 | 0.7266 |

**Key finding:** WQI routes are competitive (chi² ≈ 27-30, reduced ≈ 1.5-1.7),
consistent with the S8 tension. WLI routes show increasing tension with steeper
potentials (higher α), matching the BAO pattern. The RSD validator confirms and
strengthens the BAO ranking.

---

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
  "growth_z_start": 10.0,  "ode_solver": "DOP853"
}
```

---

## Entry point

```python
from tfa_rsd_validator import run_rsd_validator

code, desc = run_rsd_validator(run_folder)
```

Called by `tfa_common` v0.9.0 as the fifth specialist. Failure is **non-fatal**.

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
