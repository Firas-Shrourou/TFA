# Thawing Field Analyzer (TFA)

Thawing Field Analyzer is a reproducible Python package for running
route-level diagnostics of canonical thawing scalar-field expansion histories.
It reads a user-editable JSON contract, integrates the selected scalar route,
applies acoustic normalization, exports scalar and expansion-history products,
checks physical guards, and evaluates BAO and RSD diagnostics.

The repository is designed to be cloned as a complete folder. The launchers,
settings contract, sample routes, data files, approved scripts, and
documentation are intended to remain together.

## Repository Contents

```text
.
|-- README.md
|-- RELEASE-NOTES.md
|-- run_tfa.py
|-- run_tfa.bat
|-- run_tfa.sh
|-- tfa-environment-settings.json
|-- tfa-environment-settings.README.md
|-- data/
|-- sample-routes/
|   |-- WLI_1/
|   |-- WLI_2/
|   |-- WLI_3/
|   |-- WLI_4/
|   |-- WLI_5/
|   |-- WLI_6/
|   |-- WQI_F680/
|   `-- WQI_F765/
`-- scripts/
    |-- tfa_common/
    |-- tfa_acoustic_validator/
    |-- tfa_physics_guard_validator/
    |-- tfa_plot_exporter/
    |-- tfa_bao_validator/
    `-- tfa_rsd_validator/
```

Generated run folders are not stored in the repository. The root launcher
creates a local `results/` folder when it runs. Each sample-route launcher
creates its own local `results/` folder inside that sample route.

## Requirements

TFA uses Python 3 and the following third-party libraries:

- `numpy`
- `scipy`
- `matplotlib`

The Python launchers check for these libraries and attempt to install any that
are missing. In a managed environment, install them yourself first:

```bash
python -m pip install numpy scipy matplotlib
```

On Windows, UTF-8 output is recommended because the diagnostics may print Greek
symbols:

```powershell
$env:PYTHONUTF8 = "1"
```

## Run The Package-Root Configuration

The package-root `tfa-environment-settings.json` is the main user-editable
input contract. Edit the `user_adjustable.potential` block to define the route:

- `benchmark_id`
- `V_of_phi`
- `dV_dphi`
- `parameters`
- `initial_phi`
- `initial_phi_N`
- `user_remarks`

Then run from the repository root.

Windows:

```powershell
.\run_tfa.bat
```

Python directly:

```bash
python run_tfa.py
```

Unix-like shells:

```bash
./run_tfa.sh
```

Outputs are written to:

```text
results/tfa_YYYYMMDD_HHMMSS_<run_id>/
```

Each run folder includes a frozen copy of the input settings, summary JSON,
CSV products, and plots.

## Run A Preconfigured Sample Route

`sample-routes/` contains the eight route markers used by the package
demonstration set:

- `WQI_F765`
- `WQI_F680`
- `WLI_1`
- `WLI_2`
- `WLI_3`
- `WLI_4`
- `WLI_5`
- `WLI_6`

Each sample route has its own settings file and launchers. For example:

```powershell
.\sample-routes\WLI_3\windows_run_WLI_3.bat
```

or:

```bash
./sample-routes/WLI_3/unix_run_WLI_3.sh
```

Use the sample-route folders when you want to run one of the provided WLI/WQI
markers without editing the package-root settings file.

## Output Files

The run folder is the reproducibility record. Important outputs include:

| File | Purpose |
|---|---|
| `environment-settings.json` | Frozen copy of the input contract used by the run. |
| `run_results_summary.json` | High-level run identity, contract, calls, and result blocks. |
| `trajectory.csv` | Full scalar integration trajectory. |
| `expansion_history_shape.csv` | Dimensionless expansion-history shape. |
| `expansion_history_h0x_normalized.csv` | Normalized expansion history `H_X(z)`. |
| `w_of_z.csv` | Scalar equation-of-state history. |
| `physics_guards.csv` | Physical-admissibility checks. |
| `bao_results_per_datum.csv` | BAO row-level validation table. |
| `rsd_results_per_datum.csv` | RSD row-level validation table. |
| `H_of_z.png`, `delta_H.png`, `w_of_z.png` | Expansion and scalar-history plots. |
| `bao_pulls.png` | BAO pull plot. |
| `rsd_pulls.png`, `rsd_growth.png` | RSD pull and growth-rate plots. |

## Approved Script Versions

This public release keeps only the approved working script versions:

| Script | Approved folder |
|---|---|
| `tfa_common` | `v0.9.0-build.0001` |
| `tfa_acoustic_validator` | `v0.1.4-build.0001` |
| `tfa_physics_guard_validator` | `v0.1.4-build.0001` |
| `tfa_plot_exporter` | `v0.1.0-build.0001` |
| `tfa_bao_validator` | `v0.1.1-build.0001` |
| `tfa_rsd_validator` | `v0.1.0-build.0001` |

Each script folder includes an `approved-version.json` file. The launchers use
those approval files to resolve the working script versions.

## Input Contract Documentation

See `tfa-environment-settings.README.md` for the detailed description of the
settings contract, including which fields are user-changeable and which fields
are read-only defaults.

## Reproducibility Notes

TFA is folder based. To audit a run, inspect the timestamped output folder:

1. Check the frozen `environment-settings.json`.
2. Check `run_results_summary.json`.
3. Inspect the CSV products.
4. Inspect the generated plots.

This makes the user request, the execution trace, and the numerical/visual
products available in one local run folder.
