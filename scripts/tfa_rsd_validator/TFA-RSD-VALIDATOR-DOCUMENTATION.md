# TFA RSD Validator Technical Note

This note describes the public behavior of `tfa_rsd_validator`.

## Purpose

The RSD validator tests whether the route's normalized expansion history is
consistent with observed growth-rate data. It computes the model observable
`f*sigma8(z)` and compares it with the bundled 18-point compilation.

## Inputs

The validator expects a completed run folder containing:

```text
environment-settings.json
run_results_summary.json
expansion_history_h0x_normalized.csv
```

The normalized expansion history supplies `H_X(z)`. The summary supplies `H0_X`
and acoustic-validator metadata.

## Growth Calculation

The validator integrates the standard linear growth equation in General
Relativity, using scale factor `a` as the independent variable:

```text
D'' + (3/a + dlnH/da) D' = 1.5 * Omega_m(a) * D / a^2
```

It evaluates the growth rate

```text
f(z) = dlnD/dlna
```

and reports the model observable

```text
f*sigma8(z)
```

against each data point.

## Dataset

The bundled data live in:

```text
data/fsigma8_gold/
```

Files:

| File | Contents |
|---|---|
| `fsigma8_gold_mean.txt` | 18 rows of `z_eff`, observed `f*sigma8`, uncertainty, and survey label. |
| `fsigma8_gold_cov.txt` | Diagonal covariance matrix. |

## Outputs

| File | Contents |
|---|---|
| `rsd_results_per_datum.csv` | Per-datum model values, residuals, pulls, and growth quantities. |
| `rsd_pulls.png/pdf` | Pull chart. |
| `rsd_growth.png/pdf` | Continuous `f*sigma8(z)` curve with measurements. |

Summary statistics are written under `results.rsd_validator` in
`run_results_summary.json`.

## Settings

The validator can be enabled or disabled in the input contract:

```json
"rsd_validator": {
  "enabled": true
}
```

If disabled, the skip is recorded in `run_results_summary.json`.
