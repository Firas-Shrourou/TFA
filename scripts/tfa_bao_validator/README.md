# tfa_bao_validator

`tfa_bao_validator` evaluates BAO distance diagnostics for a completed TFA run.

Approved folder:

```text
v0.1.1-build.0001/
```

## Runtime Role

The validator reads the normalized expansion history and acoustic anchor from
the run folder. It compares the route against the bundled DESI DR2 ALL GCcomb
BAO data using the route's drag-epoch sound horizon `r_drag_Mpc`.

## Computed Quantities

For each BAO datum, the validator computes the relevant distance ratio:

```text
D_H(z) / r_drag
D_M(z) / r_drag
D_V(z) / r_drag
```

It then reports residuals, pulls, total `chi2`, reduced `chi2`, and per-sigma
counts.

## Outputs

| File | Meaning |
|---|---|
| `bao_results_per_datum.csv` | Row-level BAO model values, residuals, and pulls. |
| `bao_pulls.png/pdf` | Pull chart for the BAO data vector. |
| `run_results_summary.json` | Enriched with BAO summary statistics. |

## Public API

```python
from tfa_bao_validator import run_bao_validator

code, desc = run_bao_validator(run_folder)
```

The validator is called automatically by the package-root launcher when
`user_adjustable.bao_validator.enabled` is `true`.
