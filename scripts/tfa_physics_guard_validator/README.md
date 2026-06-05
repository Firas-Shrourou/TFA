# tfa_physics_guard_validator

`tfa_physics_guard_validator` checks whether the integrated route satisfies the
package's physical-admissibility guards.

Approved folder:

```text
v0.1.4-build.0001/
```

## Runtime Role

The validator reads `trajectory.csv` and the frozen `environment-settings.json`
from the run folder. It writes `physics_guards.csv` and records guard outcomes in
`run_results_summary.json`.

## Guards

| Guard | Purpose |
|---|---|
| `canonical` | Checks that `w_phi` remains above the canonical floor. |
| `thawing` | Checks late-time thawing monotonicity. |
| `phantom_crossing` | Checks for crossings below the phantom boundary. |
| `BBN` | Checks the scalar density fraction against the BBN bound. |

Thresholds are read from `user_adjustable.physics_guards`.

## Output

```text
physics_guards.csv
```

The guard summary is also stored under `results.physics_guard_validator` in
`run_results_summary.json`.
