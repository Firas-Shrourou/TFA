# tfa_common

`tfa_common` is the TFA hub. It creates the timestamped run folder, freezes the
input settings file into that folder, initializes `run_results_summary.json`,
and calls the approved specialist scripts.

Approved folder:

```text
v0.9.0-build.0001/
```

## Runtime Role

The hub runs the package in this order:

1. `tfa_acoustic_validator`
2. `tfa_physics_guard_validator`
3. `tfa_plot_exporter`
4. `tfa_bao_validator`
5. `tfa_rsd_validator`

The acoustic and physics-guard stages provide the main physics verdict. Plot,
BAO, and RSD stages are diagnostics: their status is recorded in
`run_results_summary.json`.

## Public Entry Point

Most users should run TFA from the repository root:

```bash
python run_tfa.py
```

or use the platform launcher:

```powershell
.\run_tfa.bat
```

The hub can also be called from Python by importing the approved script folder,
but the root launchers are the supported public workflow.

## Outputs

The hub writes one run folder under `results/`:

```text
results/tfa_YYYYMMDD_HHMMSS_<run_id>/
```

That folder contains the frozen input contract, summary JSON, CSV products, and
plots produced by the specialists.
