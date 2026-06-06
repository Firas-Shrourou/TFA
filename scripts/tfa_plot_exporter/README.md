# tfa_plot_exporter Approved Versions

| Version | Build | API | TFA release | Folder | Status |
|---|---:|---:|---:|---|---|
| `0.1.1` | `0001` | `0.1` | `0.0.4` | `v0.1.1-build.0001/` | approved |
| `0.1.0` | `0001` | `0.1` | `0.0.2` | `v0.1.0-build.0001/` | superseded |

`0.1.1` adds the **energy_fractions plot** (non-gated). A new function
`_plot_energy_fractions` reads `trajectory.csv` (already loaded) and the
pre-computed `energy_fractions` block from `run_results_summary.json` (written
by `tfa_acoustic_validator v0.1.5`). Produces `energy_fractions.png/pdf` for
every route — including EXCLUDED. Shows Ω_φ, Ω_m (route), Ω_Λ, Ω_m (ΛCDM)
curves from z=0 to z=3, with annotated equality redshifts z_eq_route and
z_eq_lcdm and a z=0 energy-budget infobox. Gracefully skips the plot if the
`energy_fractions` block is absent (run produced by an older acoustic validator).
Total plots: **6** (was 5).

`0.1.0` is the initial release. Pure consumer: reads run-folder files, produces
5 diagnostic plots as `.png` + `.pdf` pairs, enriches `run_results_summary.json`.
No physics recomputation.

## What it writes

| File | Gated | Source data |
|---|---|---|
| `energy_fractions.png/pdf` | **No** | `trajectory.csv` + `energy_fractions` summary block |
| `w_of_z.png/pdf` | No | `trajectory.csv`: z, w_phi |
| `Omega_phi.png/pdf` | No | `trajectory.csv`: z, Omega_phi |
| `phase_portrait.png/pdf` | No | `trajectory.csv`: N, phi, dphi_dN |
| `H_of_z.png/pdf` | Yes | `expansion_history_h0x_normalized.csv` + ΛCDM inline |
| `delta_H.png/pdf` | Yes | `expansion_history_h0x_normalized.csv` + ΛCDM inline |

Gated plots are silently skipped when the export gate rejected the route
(i.e. `expansion_history_h0x_normalized.csv` is absent).

## Entry point

```python
from tfa_plot_exporter import run_plot_exporter

code, desc = run_plot_exporter(run_folder)
# code: "OK" or "Error"
# desc: human-readable status string
```

Called by `tfa_common` v0.6.0 as the third specialist after
`run_acoustic_validator` and `run_physics_guard_validator`. Plot exporter
failure is non-fatal: the hub records the error but returns `code="OK"` if the
physics specialists passed.

## Dependencies

`numpy`, `scipy` (not used directly, but present in the environment),
`matplotlib` — no TFA specialist imports needed.
