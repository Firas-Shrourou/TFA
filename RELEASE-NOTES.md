# Release Notes

## TFA 0.0.2

This release packages the approved Thawing Field Analyzer stack for public use.
It includes the package-root launcher, eight preconfigured WLI/WQI sample
routes, bundled BAO and RSD data files, and the current approved specialist
scripts.

## Approved Stack

| Component | Version | Folder | Role |
|---|---:|---|---|
| `tfa_common` | `0.9.0` | `scripts/tfa_common/v0.9.0-build.0001/` | Run-folder hub and specialist orchestration. |
| `tfa_acoustic_validator` | `0.1.4` | `scripts/tfa_acoustic_validator/v0.1.4-build.0001/` | Scalar integration, acoustic normalization, `H0_X`, `r_s`, and `r_drag`. |
| `tfa_physics_guard_validator` | `0.1.4` | `scripts/tfa_physics_guard_validator/v0.1.4-build.0001/` | Canonical, thawing, phantom-crossing, and BBN guard checks. |
| `tfa_plot_exporter` | `0.1.0` | `scripts/tfa_plot_exporter/v0.1.0-build.0001/` | Diagnostic plots from run-folder products. |
| `tfa_bao_validator` | `0.1.1` | `scripts/tfa_bao_validator/v0.1.1-build.0001/` | DESI DR2 BAO distance diagnostics using the drag-epoch ruler. |
| `tfa_rsd_validator` | `0.1.0` | `scripts/tfa_rsd_validator/v0.1.0-build.0001/` | Growth-rate `f*sigma8` diagnostics. |

Each component folder includes an `approved-version.json` file. The launchers
resolve the approved folders from those files.

## Included Data

| Dataset | Files | Used by |
|---|---|---|
| DESI DR2 ALL GCcomb BAO | `data/desi_bao_dr2/*` | `tfa_bao_validator` |
| 18-point `f*sigma8` gold compilation | `data/fsigma8_gold/*` | `tfa_rsd_validator` |

## User-Facing Changes

- The root `tfa-environment-settings.json` is the main user input contract.
- The run command is available as `run_tfa.bat`, `run_tfa.py`, and `run_tfa.sh`.
- Outputs are written locally under `results/tfa_YYYYMMDD_HHMMSS_<run_id>/`.
- Each run folder stores a frozen `environment-settings.json` copy for audit.
- BAO and RSD diagnostics are enabled by default and can be disabled in the
  settings file.
- Python launchers check for `numpy`, `scipy`, and `matplotlib`, and attempt to
  install missing packages.

## Notes

This release is intended to be cloned and run as a self-contained folder. The
generated `results/` folders are intentionally ignored by version control.
