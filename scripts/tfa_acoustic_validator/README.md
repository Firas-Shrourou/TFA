# tfa_acoustic_validator

`tfa_acoustic_validator` is the scalar-field engine and acoustic normalization
stage.

Approved folder:

```text
v0.1.4-build.0001/
```

## Runtime Role

The validator reads the frozen `environment-settings.json` from a run folder,
builds the scalar potential from `user_adjustable.potential`, integrates the
route, solves the acoustic-preserving `H0_X`, and writes the main history CSVs.

## Inputs

- `environment-settings.json`
- `run_results_summary.json`

The potential is supplied as expression strings:

```json
{
  "V_of_phi": "3 * Omega_DE * (phi_inf / phi) ** alpha",
  "dV_dphi": "-alpha * 3 * Omega_DE * (phi_inf / phi) ** alpha / phi",
  "parameters": { "alpha": 2.0, "phi_inf": 1.30 },
  "initial_phi": 1.30,
  "initial_phi_N": 0.0
}
```

If `dV_dphi` is omitted or empty, the engine uses a numerical derivative.

## Outputs

| File | Meaning |
|---|---|
| `trajectory.csv` | Full scalar trajectory and equation-of-state history. |
| `expansion_history_shape.csv` | Dimensionless expansion shape `E_X(z)`. |
| `expansion_history_h0x_normalized.csv` | Normalized expansion history `H_X(z)`. |
| `w_of_z.csv` | Compact equation-of-state output. |
| `run_results_summary.json` | Enriched with `H0_X`, acoustic quantities, and band status. |

The acoustic summary includes both the recombination sound horizon `r_s_Mpc` and
the drag-epoch ruler `r_drag_Mpc`.
