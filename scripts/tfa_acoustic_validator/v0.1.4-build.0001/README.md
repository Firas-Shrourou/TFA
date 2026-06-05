# tfa_acoustic_validator.py

Approved implementation of the TFA acoustic validator.

## Public API

```python
from tfa_acoustic_validator import run_acoustic_validator

code, desc = run_acoustic_validator(run_folder)
```

`run_folder` must contain a frozen `environment-settings.json` and
`run_results_summary.json`. The function returns a status code and short
description, and writes its outputs into the same folder.

## What It Does

- Evaluates the scalar potential from `user_adjustable.potential`.
- Integrates the homogeneous scalar-field route.
- Computes the normalized expansion history.
- Solves for the acoustic-preserving `H0_X`.
- Computes `r_s_Mpc` and `r_drag_Mpc`.
- Records all derived values in `run_results_summary.json`.

## Main Outputs

```text
trajectory.csv
expansion_history_shape.csv
expansion_history_h0x_normalized.csv
w_of_z.csv
```

The package-root launcher calls this script automatically.
