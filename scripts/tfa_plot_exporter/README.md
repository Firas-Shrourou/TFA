# tfa_plot_exporter

`tfa_plot_exporter` creates visual diagnostics from files already present in a
run folder. It does not recompute the scalar-field solution.

Approved folder:

```text
v0.1.0-build.0001/
```

## Runtime Role

The exporter reads run-folder CSV and JSON products, then writes plot files in
PNG and PDF form.

## Plots

| Plot | Source |
|---|---|
| `w_of_z.png/pdf` | `trajectory.csv` |
| `Omega_phi.png/pdf` | `trajectory.csv` |
| `phase_portrait.png/pdf` | `trajectory.csv` |
| `H_of_z.png/pdf` | `expansion_history_h0x_normalized.csv` |
| `delta_H.png/pdf` | `expansion_history_h0x_normalized.csv` |

`H_of_z` and `delta_H` are written only when the export gate accepts the route
and the normalized history exists.

## Public API

```python
from tfa_plot_exporter import run_plot_exporter

code, desc = run_plot_exporter(run_folder)
```

The package-root launcher calls this script automatically.
