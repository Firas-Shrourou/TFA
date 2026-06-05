# tfa_rsd_validator

`tfa_rsd_validator` evaluates growth-rate diagnostics for a completed TFA run.
It complements BAO: BAO tests distance geometry, while RSD tests structure
growth through `f*sigma8(z)`.

Approved folder:

```text
v0.1.0-build.0001/
```

## Runtime Role

The validator reads `expansion_history_h0x_normalized.csv` and
`run_results_summary.json`, integrates the linear growth equation, and compares
the route prediction against the bundled 18-point `f*sigma8` compilation.

## Outputs

| File | Meaning |
|---|---|
| `rsd_results_per_datum.csv` | Row-level RSD model values, residuals, pulls, and growth quantities. |
| `rsd_pulls.png/pdf` | Pull chart for the RSD measurements. |
| `rsd_growth.png/pdf` | Continuous `f*sigma8(z)` curve with data points and reference curve. |
| `run_results_summary.json` | Enriched with RSD summary statistics. |

## Public API

```python
from tfa_rsd_validator import run_rsd_validator

code, desc = run_rsd_validator(run_folder)
```

The validator is called automatically by the package-root launcher when
`user_adjustable.rsd_validator.enabled` is `true`.
