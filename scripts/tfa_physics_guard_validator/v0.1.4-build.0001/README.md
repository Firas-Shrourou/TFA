# tfa_physics_guard_validator.py

Approved implementation of the TFA physics-guard validator.

## Public API

```python
from tfa_physics_guard_validator import run_physics_guard_validator

code, desc = run_physics_guard_validator(run_folder)
```

`run_folder` must contain `trajectory.csv`, `environment-settings.json`, and
`run_results_summary.json`.

## What It Does

- Reads the scalar history produced by the acoustic validator.
- Applies canonical, thawing, phantom-crossing, and BBN checks.
- Writes the long-form guard table.
- Enriches `run_results_summary.json`.

## Main Output

```text
physics_guards.csv
```
