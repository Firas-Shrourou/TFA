# tfa_bao_validator Approved Versions

| Version | Build | API | TFA release | Folder | Status |
|---|---:|---:|---:|---|---|
| `0.1.1` | `0001` | `0.1` | `0.0.2` | `v0.1.1-build.0001/` | approved |
| `0.1.0` | `0001` | `0.1` | `0.0.2` | `v0.1.0-build.0001/` | superseded |

`0.1.1` fixes the BAO ruler: uses `r_drag_Mpc` (drag-epoch sound horizon,
Eisenstein-Hu 1998, z_drag ≈ 1063, ≈ 146.9 Mpc) instead of `r_s_Mpc`
(z_star sound horizon, ≈ 144.4 Mpc). DESI DR2 reports D_X/r_d ratios
normalised to the drag-epoch ruler; using r_s introduced a systematic ~1.75%
bias that inflated chi² for all routes and produced spurious "good fits"
through accidental cancellation. With r_drag the pure Planck 2018 ΛCDM
baseline gives chi²=33.6 (reduced=2.59), reflecting the known Planck–DESI
tension rather than a ruler artefact.

`0.1.0` is retained for regression comparison. Do not use it for new analyses.

---

## What it computes

For each datum at z_eff:

```
D_H(z) = c / H_X(z)
D_M(z) = c * integral_0^z dz' / H_X(z')   [flat, Omega_K = 0 by TFA construction]
D_V(z) = [z * D_M(z)^2 * D_H(z)]^(1/3)

model_ratio = D_X(z_eff) / r_drag_Mpc
residual    = model_ratio - observed
pull        = residual / sigma
chi2        = r^T C^-1 r    (full 13×13 DESI DR2 covariance)
```

H_X(z) is read from `expansion_history_h0x_normalized.csv` and interpolated
with `PchipInterpolator`. r_drag_Mpc is read from the acoustic anchor in
`run_results_summary.json` — the route's own drag-epoch sound horizon, not an
external constant.

---

## Physical meaning of r_d sources

| | FEU blind test (v16.T013) | tfa_bao_validator v0.1.0 | tfa_bao_validator v0.1.1 |
|---|---|---|---|
| r_d | Fixed external 144.4006 Mpc | `acoustic_anchor.r_s_Mpc` ≈ 144.4 Mpc | `acoustic_anchor.r_drag_Mpc` ≈ 146.9 Mpc |
| Epoch | z_star (wrong for BAO) | z_star (wrong for BAO) | z_drag (correct for BAO) |
| ΛCDM chi² | 130 (catastrophic bias) | 130 (same bias) | 33.6 (Planck–DESI tension) |

The FEU blind test chi² values (WLI_1=25.86, etc.) are invalidated: they
reflected accidental partial cancellation between the wrong ruler and each
route's specific expansion-rate deviation, not physical BAO tension.

---

## Gating

Doubly gated:
1. `expansion_history_h0x_normalized.csv` must exist (export gate accepted route)
2. `results["acoustic_validator"]["acoustic_anchor"]["r_drag_Mpc"]` must be present
   (requires `tfa_acoustic_validator >= 0.1.4`)

Silent skip on either condition; recorded in `results["bao_validator"]`.

---

## Verified results (v0.1.1, r_drag ≈ 146.9 Mpc)

ΛCDM reference baseline: **chi² = 33.6, reduced = 2.59** (Planck–DESI tension).

| Route | Family | H0_X | Band | chi² | χ²/dof | Within 2σ |
|---|---|---|---|---|---|---|
| WQI_F765 | WQI | 67.478 | STRICT | **20.4** | **1.57** | 13/13 |
| WQI_F680 | WQI | 67.508 | STRICT | **27.1** | **2.09** | 11/13 |
| WLI_4 (α=1.0, φ∞=1.35) | WLI | 67.582 | STRICT | 55.9 | 4.30 | 10/13 |
| WLI_1 (α=1.0, φ∞=1.30) | WLI | 67.598 | STRICT | 64.8 | 4.98 | 9/13 |
| WLI_5 (α=1.5, φ∞=1.35) | WLI | 67.833 | STRICT | 292.9 | 22.5 | 3/13 |
| WLI_2 (α=1.5, φ∞=1.30) | WLI | 67.865 | STRICT | 335.2 | 25.8 | 2/13 |
| WLI_6 (α=2.0, φ∞=1.35) | WLI | 68.150 | LOOSE_2S | 828.9 | 63.8 | 0/13 |
| WLI_3 (α=2.0, φ∞=1.30) | WLI | 68.201 | LOOSE_2S | 929.5 | 71.5 | 0/13 |

WQI routes beat the ΛCDM baseline. WLI routes show monotonically increasing
tension with steeper potentials (higher α), confirming the physical expectation.

---

## What it writes

| File | Notes |
|---|---|
| `bao_results_per_datum.csv` | 13 rows: z_eff, observable, observed, model, residual, pull, datum_status, D_H/D_M/D_V |
| `bao_pulls.png` + `.pdf` | Pull bar chart colored by 1σ/2σ/3σ/>3σ |

Enriches `run_results_summary.json` under `results["bao_validator"]` with
chi2, reduced_chi2, max_abs_pull, per-sigma counts, and rd_X.

---

## Entry point

```python
from tfa_bao_validator import run_bao_validator

code, desc = run_bao_validator(run_folder)
```

Called by `tfa_common` v0.8.0 as the fourth specialist. Failure is **non-fatal**.

---

## Settings

```json
"user_adjustable": {
  "bao_validator": {
    "enabled": true
  }
}
```

---

## Dependencies

`numpy`, `scipy` (PchipInterpolator, quad), `matplotlib`. No TFA specialist
imports beyond reading the run folder files.

---

## Bundled data

DESI DR2 ALL GCcomb dataset (13 data points, full 13×13 covariance):

```
TFA-package/data/desi_bao_dr2/
    desi_gaussian_bao_ALL_GCcomb_mean.txt
    desi_gaussian_bao_ALL_GCcomb_cov.txt
```

Located at runtime by walking up from `__file__` until `TFA-package/data/desi_bao_dr2/`
is found — same walk-up pattern as `_unified_settings_path()`.
