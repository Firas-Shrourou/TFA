# TFA Package

This folder holds approved script versions for the Thawing Field Analyzer
package.

---

## Agent session start — read this first

Read `E:\Thawing Field Analyzer\Bugs\Bug-Index.md` before starting work. It is
a single short table. Scan it for any entry whose affected component overlaps
with the files you are about to touch. If there is a match — especially a
"Part 2 pending" entry — read that bug's `README.md` (one page) before
proceeding. Only go deeper into `fix-plan.md` if you are actively working on
that bug.

---

## Versioning Model

TFA uses four independent version layers:

| Layer | Meaning | Example |
|---|---|---|
| TFA project release | Combined repository/package state | `0.0.2` |
| Script version/build | Individual script implementation | `tfa_common 0.1.0 build 0001` |
| Settings schema | JSON compatibility contract | `0.1` |
| Settings file version | The unified `tfa-environment-settings.json` itself | `1.0.0` |

The project release does not force every script to share the same version. A
future TFA release may include several scripts, each with its own version and
build number.

## Current Approved Scripts

| Script | Approved version | Build | API | Folder | Status |
|---|---:|---:|---:|---|---|
| `tfa_common` | `0.9.1` | `0002` | `0.1` | `scripts/tfa_common/v0.9.1-build.0002/` | approved |
| `tfa_acoustic_validator` | `0.1.5` | `0001` | `0.1` | `scripts/tfa_acoustic_validator/v0.1.5-build.0001/` | approved |
| `tfa_physics_guard_validator` | `0.1.4` | `0001` | `0.1` | `scripts/tfa_physics_guard_validator/v0.1.4-build.0001/` | approved |
| `tfa_plot_exporter` | `0.1.1` | `0001` | `0.1` | `scripts/tfa_plot_exporter/v0.1.1-build.0001/` | approved |
| `tfa_bao_validator` | `0.1.1` | `0001` | `0.1` | `scripts/tfa_bao_validator/v0.1.1-build.0001/` | approved |
| `tfa_rsd_validator` | `0.1.0` | `0001` | `0.1` | `scripts/tfa_rsd_validator/v0.1.0-build.0001/` | approved |
| `tfa_normalized_history_generator` | — | — | — | — | **deprecated** |
| `tfa_csv_exporter` | — | — | — | — | **deprecated** |

`tfa_normalized_history_generator` and `tfa_csv_exporter` are deprecated: the
acoustic validator engine now writes all CSVs directly (gated), and the
csv-exporter role is subsumed. Their superseded builds are in `archive/`.

## Package Tree

The package root is the normal user-facing run location:

```text
TFA-package/
|-- README.md
|-- RELEASE-NOTES.md
|-- run_tfa.py
|-- run_tfa.bat
|-- run_tfa.sh
|-- tfa-environment-settings.json
|-- tfa-environment-settings.README.md
|-- results/
|-- sample-routes/
|   |-- WLI_1/
|   |-- WLI_2/
|   |-- WLI_3/
|   |-- WLI_4/
|   |-- WLI_5/
|   |-- WLI_6/
|   |-- WQI_F680/
|   `-- WQI_F765/
|-- scripts/
|   |-- tfa_common/
|   |-- tfa_acoustic_validator/
|   |-- tfa_physics_guard_validator/
|   |-- tfa_plot_exporter/
|   |-- tfa_bao_validator/
|   `-- tfa_rsd_validator/
|-- data/
`-- archive/
```

`run_tfa.py`, `run_tfa.bat`, and `run_tfa.sh` are the package-root launchers.
They read the package-root `tfa-environment-settings.json`, so this is the path
used when the user edits the active input contract and runs their own
configuration. Output from this path is written to `TFA-package/results/`.

`sample-routes/` contains preconfigured WLI/WQI route folders. Each sample
folder has its own settings file and matching launchers so the reader can run a
fixed marker without editing the package-root contract. Output from a sample
launcher is written to that sample folder's own `results/` subfolder.

## Running

### Prerequisites

Only `numpy`, `scipy`, and `matplotlib` (plus stdlib) are required. On Windows
with Anaconda, set the UTF-8 flag once per session — the scripts emit Greek
characters that the default codepage cannot encode:

```powershell
$env:PYTHONUTF8 = "1"
```

The Python launchers check for `numpy`, `scipy`, and `matplotlib` and attempt
to install any missing package before the run starts. In a managed environment,
install these dependencies in advance and then run the launcher normally.

### Run all 8 benchmarks

From the repository root:

```powershell
$env:PYTHONUTF8 = "1"
python run_all_benchmarks.py
```

`run_all_benchmarks.py` (repository root) loops over all 8 benchmark routes,
patches each potential into a temporary copy of `tfa-environment-settings.json`,
calls `tfa.run()`, and writes results under `tfa-results/runs/`. The canonical
settings file is never modified.

### Run the package-root configuration

The package-root `tfa-environment-settings.json` is the user-owned input
contract. Edit `user_adjustable.potential` there with the desired
`benchmark_id`, `V_of_phi`, `dV_dphi`, `parameters`, `initial_phi`,
`initial_phi_N`, and `user_remarks`, then run one of the package-root launchers
from inside `TFA-package/`:

```powershell
.\run_tfa.bat
```

or:

```powershell
python run_tfa.py
```

On Unix-like shells, use:

```bash
./run_tfa.sh
```

The launcher resolves the approved `tfa_common` build automatically from
`scripts/tfa_common/approved-version.json`, reads the package-root
`tfa-environment-settings.json`, and writes the timestamped run folder under
`results/` beside the launcher.

### Run a preconfigured sample route

Each folder under `sample-routes/` is a self-contained preconfigured route.
For example, from inside `TFA-package/`, run the `WLI_3` sample on Windows
with:

```powershell
.\sample-routes\WLI_3\windows_run_WLI_3.bat
```

On Unix-like shells, use the matching shell launcher:

```bash
./sample-routes/WLI_3/unix_run_WLI_3.sh
```

Each sample launcher reads the `tfa-environment-settings.json` inside that
sample folder and writes outputs to that sample's `results/` subfolder. Use the
sample folders when you want to reproduce one of the provided WLI/WQI markers
without editing the package-root contract.

### Benchmark definitions

| Benchmark | Family | V_of_phi | Key parameters |
|---|---|---|---|
| `WQI_F765` | WQI | `3*Omega_DE*(phi_F**4+M_Mp**4)/(phi**4+M_Mp**4)` | phi_F=7.65, M_Mp=1.794e-13 |
| `WQI_F680` | WQI | same | phi_F=6.80, M_Mp=1.794e-13 |
| `WLI_1` | WLI | `3*Omega_DE*(phi_inf/phi)**alpha` | alpha=1.0, phi_inf=1.30 |
| `WLI_2` | WLI | same | alpha=1.5, phi_inf=1.30 |
| `WLI_3` | WLI | same | alpha=2.0, phi_inf=1.30 |
| `WLI_4` | WLI | same | alpha=1.0, phi_inf=1.35 |
| `WLI_5` | WLI | same | alpha=1.5, phi_inf=1.35 |
| `WLI_6` | WLI | same | alpha=2.0, phi_inf=1.35 |

All WLI routes: `dV_dphi = -alpha*3*Omega_DE*(phi_inf/phi)**alpha/phi`,
`initial_phi = phi_inf`, `initial_phi_N = 0.0`.

All WQI routes: `dV_dphi = -4*phi**3*3*Omega_DE*(phi_F**4+M_Mp**4)/(phi**4+M_Mp**4)**2`,
`initial_phi = phi_F`, `initial_phi_N = 0.0`.

## Benchmark verification record

Fresh run: 2026-06-05, `tfa_common 0.9.0 build 0001`, full specialist chain (physics results unchanged under 0.9.1 — B001 fix is encoding-only)
(acoustic v0.1.4, guard v0.1.4, plot v0.1.0, BAO v0.1.1, RSD v0.1.0).
BAO uses `r_drag_Mpc` ≈ 146.92 Mpc. ΛCDM BAO baseline: χ²=33.6 (reduced=2.59).
All 8 runs returned `code=OK`, all guards passed.
Physics verdicts identical under 0.0.4 stack (T001 adds energy_fractions output only).

| Benchmark | H0_X (km/s/Mpc) | Band | BAO χ² | BAO χ²/dof | BAO 2σ | RSD χ² | RSD χ²/dof | RSD 2σ | σ8_X | growth_ratio |
|---|---:|---|---:|---:|---|---:|---:|---|---:|---:|
| WQI_F765 | 67.4780 | STRICT   |   20.4 |  1.57 | 13/13 |  27.2 | 1.51 | 16/18 | 0.7052 | 0.8694 |
| WQI_F680 | 67.5085 | STRICT   |   27.1 |  2.09 | 11/13 |  29.8 | 1.66 | 16/18 | 0.6988 | 0.8615 |
| WLI_4    | 67.5822 | STRICT   |   55.9 |  4.30 | 10/13 |  36.5 | 2.03 | 15/18 | 0.6850 | 0.8445 |
| WLI_1    | 67.5981 | STRICT   |   64.8 |  4.98 |  9/13 |  38.2 | 2.12 | 15/18 | 0.6820 | 0.8408 |
| WLI_5    | 67.8331 | STRICT   |  292.9 | 22.53 |  3/13 |  67.1 | 3.73 | 11/18 | 0.6412 | 0.7906 |
| WLI_2    | 67.8653 | STRICT   |  335.2 | 25.78 |  2/13 |  71.4 | 3.97 | 11/18 | 0.6363 | 0.7845 |
| WLI_6    | 68.1505 | LOOSE_2S |  828.9 | 63.76 |  0/13 | 113.5 | 6.30 | 10/18 | 0.5956 | 0.7343 |
| WLI_3    | 68.2009 | LOOSE_2S |  929.5 | 71.50 |  0/13 | 120.9 | 6.72 |  9/18 | 0.5893 | 0.7266 |

Table is sorted by H0_X ascending (tightest acoustic anchor to most displaced).
Physics verdicts (H0_X, band) are stable: identical to the 0.0.2 verification
record in `RELEASE-NOTES.md`.

## Package Rules

- Each script owns its own folder under `scripts/<script_name>/`.
- Approved script versions live in versioned folders such as
  `v0.1.0-build.0001/`.
- A script version folder should include the script file and any
  script-specific notes needed to run it.
- **Package-root environment settings are the user-owned run contract.** The
  root launchers read `TFA-package/tfa-environment-settings.json`, documented
  by `tfa-environment-settings.README.md`.
- **Sample-route settings are preconfigured examples.** Each folder under
  `sample-routes/` carries its own settings file and launchers so that marker
  can be run without modifying the package-root contract.
- Combined release notes live in `RELEASE-NOTES.md`.
- Root-launcher results are written under `TFA-package/results/`; sample-route
  results are written under each sample folder's `results/` subfolder.

## Coding Convention — Error Handling

Every specialist entry point must wrap its entire body in a single top-level
`try / except` block. No code path may raise an unhandled exception out of an
entry point. All errors are returned as `("Error", <desc>)` tuples; the flow
is never interrupted by a bare exception.

```python
def run_my_specialist(run_folder):
    try:
        # ... all logic here ...
        return ("OK", "specialist complete: ...")
    except Exception as exc:
        return ("Error", f"{type(exc).__name__}: {exc}")
```

Rules:
- The `try` block opens immediately after the function signature — no logic
  before it.
- Early-exit conditions (missing files, disabled flags, gate checks) are
  `return ("OK", ...)` or `return ("Error", ...)` statements **inside** the
  `try`, never outside it.
- The `except` clause is the last resort; it must always return `("Error", ...)`
  and never re-raise or call `sys.exit`.
- Every new script and every updated entry point must follow this convention
  before it can be approved into the package.
