# TFA Package — Release Notes

Combined release notes for the Thawing Field Analyzer package. Each project
release is a snapshot that approves a specific set of script builds; scripts
version independently of the project release.

---

## Current approved stack

| Script | Version | Build | Folder | Role |
|---|---:|---:|---|---|
| `tfa_common` | `0.9.1` | `0002` | `scripts/tfa_common/v0.9.1-build.0002/` | Hub — orchestrates all five specialists |
| `tfa_acoustic_validator` | `0.1.5` | `0001` | `scripts/tfa_acoustic_validator/v0.1.5-build.0001/` | Engine — ODE, H0X, all CSVs, r_drag, energy_fractions |
| `tfa_physics_guard_validator` | `0.1.4` | `0001` | `scripts/tfa_physics_guard_validator/v0.1.4-build.0001/` | Guards — canonical, thawing, phantom, BBN |
| `tfa_plot_exporter` | `0.1.1` | `0001` | `scripts/tfa_plot_exporter/v0.1.1-build.0001/` | Presentation — 6 diagnostic plots |
| `tfa_bao_validator` | `0.1.1` | `0001` | `scripts/tfa_bao_validator/v0.1.1-build.0001/` | BAO — DESI DR2 distance closure, drag-epoch ruler |
| `tfa_rsd_validator` | `0.1.0` | `0001` | `scripts/tfa_rsd_validator/v0.1.0-build.0001/` | RSD — f·σ₈ growth rate, 18-point gold compilation |
| `tfa_combined_csv_results` | `0.1.0` | `0001` | `scripts/tfa_combined_csv_results/v0.1.0-build.0001/` | Utility — combine arbitrary run summaries into one union CSV |
| `tfa_normalized_history_generator` | — | — | — | **Deprecated** — moved to `archive/` |
| `tfa_csv_exporter` | — | — | — | **Deprecated** — moved to `archive/` |

---

## T002 Utility Addition — 2026-06-06

### tfa_combined_csv_results v0.1.0 build 0001

**T002 — combined CSV results utility.** Adds a standard-library-only script
that combines many `run_results_summary.json` files into one CSV. The script is
driven by a JSON config or CSV manifest, reads config/manifest/summary files
with UTF-8 BOM tolerance, and writes clean UTF-8 outputs.

The combiner treats each valid top-level JSON object as data. It flattens
arbitrary nested fields, builds union columns across all valid summaries, fills
missing numeric fields with `NaN`, fills missing text fields with `N/A`, and
does not require any current TFA summary field path.

By default it also writes a schema audit sidecar that reports column presence,
missing counts, explicit null counts, observed types, skipped inputs, and any
collision-safe flattened column suffixes.

---

## Release 0.0.4 — 2026-06-06

**Feature release — energy_fractions plot and z_eq summary block.**

### tfa_acoustic_validator v0.1.5 build 0001

**T001 — energy_fractions summary block.** A new helper
`_compute_energy_fractions` is called immediately after the ODE trajectory is
built. It writes five values into `run_results_summary.json` under
`results["acoustic_validator"]["energy_fractions"]`:

| Key | Definition |
|---|---|
| `Omega_phi_0` | Ω_φ at z=0 (tail of ODE trajectory) |
| `Omega_m_0` | 1 − Ω_φ(0) − Ω_r_route(0); route matter fraction at z=0 |
| `z_eq_lcdm` | (Ω_DE / Ω_m0)^(1/3) − 1; ΛCDM matter-DE equality |
| `z_eq_route` | z where Ω_φ(z) = 0.5 (= Ω_φ = Ω_m for flat universe) |
| `delta_z_eq` | z_eq_route − z_eq_lcdm; ≤ 0 for thawing routes |

Non-gated: the block is always written, including for EXCLUDED routes. If no
crossing is found, `z_eq_route` and `delta_z_eq` are `null` and a `z_eq_note`
string explains the miss. Physics verdicts (H0_X, band) unchanged.

### tfa_plot_exporter v0.1.1 build 0001

**T001 — energy_fractions plot.** New `_plot_energy_fractions` function adds a
sixth diagnostic plot (`energy_fractions.png/pdf`) to every run — non-gated.
Reads `trajectory.csv` (already in memory) and the pre-computed
`energy_fractions` block from the summary. Shows Ω_φ(z), Ω_m(z) (route), Ω_Λ(z)
(ΛCDM), Ω_m(z) (ΛCDM) from z=0 to z=3, with annotated `z_eq_route` and
`z_eq_lcdm` vertical lines and a z=0 energy-budget infobox. Graceful skip if
`energy_fractions` block is absent (run from older acoustic validator). Requires
`tfa_acoustic_validator v0.1.5`.

### tfa_common v0.9.1 build 0002

**T001 — specialist pointer update.** `_SPECIALIST_BUILDS` updated to pin
`tfa_acoustic_validator v0.1.5-build.0001` and `tfa_plot_exporter v0.1.1-build.0001`.
No logic changes. Version stays `0.9.1`; build advances to `0002`.

Settings: `settings_file_version` 1.0.1 → 1.0.2, `tfa_package_release` 0.0.3 → 0.0.4,
`tfa_acoustic_validator` 0.1.4 → 0.1.5, `tfa_plot_exporter` 0.1.0 → 0.1.1.
Applied to `tfa-environment-settings.json` and all 8 sample-route files.
Physics specialists (guard, BAO, RSD) unchanged.

### Verification — energy_fractions anchors

Three routes re-run through the full 0.0.4 stack (tfa_common v0.9.1 build 0002).
Physics verdicts (H0_X, band, BAO chi², RSD chi²) identical to 0.0.3.

| Route | Ω_φ(0) | Ω_m(0) | z_eq_route | z_eq_lcdm | Δz_eq |
|---|---|---|---|---|---|
| WQI_F765 | 0.672496 | 0.327413 | 0.281112 | 0.295109 | −0.013997 |
| WQI_F680 | 0.669318 | 0.330591 | 0.277406 | 0.295109 | −0.017703 |
| WLI_3    | 0.597906 | 0.402004 | 0.179729 | 0.295109 | −0.115380 |

z_eq_lcdm = 0.295109 is deterministic from Planck 2018 cosmology (Ω_DE/Ω_m0)^(1/3) − 1.
Δz_eq ≤ 0 for all thawing routes as expected.

---

## Release 0.0.3 — 2026-06-06

**Bug fix release. Sub-scripts unchanged.**

### tfa_common v0.9.1

**B001 — BOM resilience.** If `tfa-environment-settings.json` was saved with a
UTF-8 BOM (e.g. by Notepad on Windows), `json.load()` raised `JSONDecodeError`
and all runs failed immediately with no run folder produced.

Fix:
- `_read_json` now opens files with `encoding="utf-8-sig"`, which strips the
  BOM silently when present and reads normally when absent.
- The frozen settings copy is now written via parse-and-reserialize
  (`utf-8-sig` read + `_atomic_write_json`) instead of `shutil.copy2`,
  guaranteeing the frozen `environment-settings.json` in every run folder is
  BOM-free regardless of how the original was saved.
- `import shutil` removed (no longer used).

Settings schema: `settings_file_version` 1.0.0 → 1.0.1,
`tfa_package_release` 0.0.2 → 0.0.3, `tfa_common` entry 0.9.0 → 0.9.1.
Applied to `tfa-environment-settings.json` and all 8 sample-route files.

Sub-scripts (acoustic, guard, plot, bao, rsd) are unchanged in this release.
Their `_read_json` hardening is deferred to their next release per the standing
rule documented in fix plan B001.

---

## Script change log (post-0.0.2 release)

### tfa_acoustic_validator

| Version | Build | Change |
|---|---|---|
| `0.1.5` | `0001` | **Energy fractions summary block.** Adds `_compute_energy_fractions`; writes `results["acoustic_validator"]["energy_fractions"]` with Ω_φ(0), Ω_m(0), z_eq_route, z_eq_lcdm, delta_z_eq. Non-gated; always written. Physics verdicts unchanged. Required by `tfa_plot_exporter v0.1.1`. |
| `0.1.4` | `0001` | **Drag-epoch sound horizon.** Adds `compute_z_drag` (Eisenstein-Hu 1998 fitting formula, Eq. 4) and computes `r_drag_Mpc` by integrating the sound horizon to z_drag ≈ 1063 (vs z_star ≈ 1092). Same `rs_calibration` factor applied so both scales share consistent sound-speed normalisation. `r_drag_Mpc` ≈ 146.9 Mpc is written into `run_results_summary.json` under `acoustic_anchor` alongside the existing `r_s_Mpc` ≈ 144.4 Mpc. Physics verdicts (H0_X, band) unchanged. Required by `tfa_bao_validator v0.1.1`. |
| `0.1.3` | `0001` | **Expression-string potential evaluator.** Replaces the hardcoded potential catalog (`build_potential_from_form`) with a universal `build_potential_from_settings(settings, cosmology)` that evaluates `V_of_phi` and `dV_dphi` as numpy-compatible expression strings from the frozen `environment-settings.json`. Any thawing scalar field can be defined in settings without source-code changes. Falls back to a central-difference numerical derivative when `dV_dphi` is omitted. Expression evaluation uses `__builtins__: {}` (no arbitrary execution). Smoke-tests expressions at `phi=1.0` before the ODE runs. `0.1.2` (hardcoded catalog) retained for comparison. Verified: WLI_3 `H0_X = 68.2009 LOOSE_2S`; WQI_F680 `H0_X = 67.5085 STRICT`. |

### tfa_physics_guard_validator

| Version | Build | Change |
|---|---|---|
| `0.1.4` | `0001` | **Settings-driven BBN potential rebuild.** Replaces `build_potential_from_form` (hardcoded catalog) with `build_potential_from_settings` so the frozen-field BBN density uses the same expression-string path as the engine. Pins to `tfa_acoustic_validator` v0.1.3. In-memory endpoints unchanged. `0.1.3` retained for comparison. |

### tfa_common

| Version | Build | Change |
|---|---|---|
| `0.9.1` | `0002` | **T001 specialist pointer update.** `_SPECIALIST_BUILDS` pins acoustic_validator → v0.1.5-build.0001 and plot_exporter → v0.1.1-build.0001. No logic changes. Build advances to 0002 (immutable-build-folder convention). |
| `0.9.1` | `0001` | **B001 BOM resilience.** `_read_json` uses `utf-8-sig`; frozen settings copy uses parse-and-reserialize. See Release 0.0.3. |
| `0.5.0` | `0001` | **Settings-driven, in-process hub.** Removes the form-dict argument and the subprocess call model. The researcher defines the potential once in `tfa-environment-settings.json` under `user_adjustable.potential` as expression strings; the call is `tfa.run()`. The hub evaluates expressions to callables, validates `PotentialRoute`, creates the run folder, freezes settings, then calls `run_acoustic_validator` and `run_physics_guard_validator` **in-process** (no subprocess). Works for any thawing scalar field. `0.4.0` (subprocess model) retained for comparison. |
| `0.6.0` | `0001` | **Presentation layer.** Adds `tfa_plot_exporter v0.1.0` as a third in-process specialist. Plot exporter failure is **non-fatal**. Each run folder now contains up to 10 plot files (5 diagnostics × .png/.pdf). |
| `0.7.0` | `0001` | **BAO validator (initial).** Adds `tfa_bao_validator v0.1.0` as the fourth specialist using `r_s_Mpc` as the BAO ruler. Superseded by `0.8.0` (wrong ruler). |
| `0.9.0` | `0001` | **RSD validator.** Adds `tfa_rsd_validator v0.1.0` as the fifth non-fatal specialist. Growth ODE and f·σ₈ chi² against 18-point gold compilation. Physics verdict unchanged. |
| `0.8.0` | `0001` | **BAO ruler fix.** Pins `tfa_acoustic_validator v0.1.4` and `tfa_bao_validator v0.1.1`. BAO validator now uses `r_drag_Mpc` (drag-epoch, ≈ 146.9 Mpc). Physics verdicts unchanged. Previous BAO chi² values computed with v0.7.0 are invalidated. |

### tfa_plot_exporter *(new in 0.6.0)*

| Version | Build | Change |
|---|---|---|
| `0.1.1` | `0001` | **energy_fractions plot.** Adds `_plot_energy_fractions`; non-gated 6th plot showing low-redshift energy density fractions with z_eq annotation. Reads pre-computed block from summary; graceful skip if absent. Requires `tfa_acoustic_validator v0.1.5`. |
| `0.1.0` | `0001` | **Initial release.** Pure consumer of run-folder files — no physics recomputation. Reads `trajectory.csv`, `expansion_history_h0x_normalized.csv`, `run_results_summary.json`, and frozen `environment-settings.json`. Produces 5 diagnostic plots as `.png` + `.pdf` pairs. Always-available (from `trajectory.csv`): `w_of_z`, `Omega_phi`, `phase_portrait`. Gated (require `expansion_history_h0x_normalized.csv`, i.e. export gate accepted): `H_of_z`, `delta_H`. ΛCDM reference for the two gated plots is computed inline from the frozen cosmology — no re-integration. Enriches `run_results_summary.json` under `results["plot_exporter"]`. Entry point: `run_plot_exporter(run_folder) → (Code, Desc)`. |

### tfa_rsd_validator *(new in 0.9.0)*

| Version | Build | Change |
|---|---|---|
| `0.1.0` | `0001` | **Initial release.** Growth-rate f·σ₈(z) validator. Integrates the linear growth ODE `D'' + (3/a + dlnH/da) D' = 1.5·ω_m·(H0/H)²/a⁵·D` (DOP853, rtol=1e-10, dense output) against H_X(z) and ΛCDM reference. Computes `growth_ratio = D_X(1)/D_ΛCDM(1)`, `sigma8_X = 0.8111 × growth_ratio`, and `f·σ₈(z_eff)` at each datum. Chi² against the 18-point Perivolaropoulos & Skara 2020 gold compilation (diagonal covariance, independent surveys, z = 0.02–1.48). Non-fatal; produces `rsd_results_per_datum.csv`, `rsd_pulls.png/pdf`, `rsd_growth.png/pdf`. |

### tfa_bao_validator *(new in 0.7.0)*

| Version | Build | Change |
|---|---|---|
| `0.1.0` | `0001` | **Initial release.** Reads `r_s_Mpc` from acoustic anchor as BAO ruler. **Superseded** — r_s is the z_star sound horizon, not the drag-epoch ruler DESI uses. |
| `0.1.1` | `0001` | **Correct BAO ruler.** Reads `r_drag_Mpc` (drag epoch, Eisenstein-Hu, ≈ 146.9 Mpc). Confirmed: pure Planck 2018 ΛCDM gives chi²=33.6 (reduced=2.59), consistent with the known Planck–DESI tension. Routes must be run through `tfa_acoustic_validator v0.1.4` or newer to have `r_drag_Mpc` in the summary. |

---

## Verification record

All runs through `tfa_common v0.9.0` (acoustic v0.1.4, guard v0.1.4, plot v0.1.0, BAO v0.1.1, RSD v0.1.0).
BAO chi² uses `r_drag_Mpc` ≈ 146.9 Mpc. ΛCDM BAO baseline: chi²=33.6, reduced=2.59.
RSD chi² uses 18-point Perivolaropoulos & Skara 2020 gold compilation (diagonal covariance).

| Benchmark | Potential | H0_X | Band | BAO chi² | BAO χ²/dof | BAO 2σ | RSD chi² | RSD χ²/dof | RSD 2σ | sigma8_X | growth_ratio |
|---|---|---|---|---|---|---|---|---|---|---|---|
| WQI_F765 | WQI φ_F=7.65 | 67.4780 | STRICT | **20.4** | **1.57** | 13/13 | **27.2** | **1.51** | 16/18 | 0.7052 | 0.869 |
| WQI_F680 | WQI φ_F=6.80 | 67.5085 | STRICT | **27.1** | **2.09** | 11/13 | **29.8** | **1.66** | 16/18 | 0.6988 | 0.861 |
| WLI_4 | WLI α=1.0 φ∞=1.35 | 67.5822 | STRICT | 55.9 | 4.30 | 10/13 | 36.5 | 2.03 | 15/18 | 0.6850 | 0.844 |
| WLI_1 | WLI α=1.0 φ∞=1.30 | 67.5981 | STRICT | 64.8 | 4.98 | 9/13 | 38.2 | 2.12 | 15/18 | 0.6820 | 0.841 |
| WLI_5 | WLI α=1.5 φ∞=1.35 | 67.8331 | STRICT | 292.9 | 22.5 | 3/13 | 67.1 | 3.73 | 11/18 | 0.6413 | 0.791 |
| WLI_2 | WLI α=1.5 φ∞=1.30 | 67.8653 | STRICT | 335.2 | 25.8 | 2/13 | 71.4 | 3.97 | 11/18 | 0.6363 | 0.784 |
| WLI_6 | WLI α=2.0 φ∞=1.35 | 68.1505 | LOOSE_2S | 828.9 | 63.8 | 0/13 | 113.5 | 6.30 | 10/18 | 0.5956 | 0.734 |
| WLI_3 | WLI α=2.0 φ∞=1.30 | 68.2009 | LOOSE_2S | 929.5 | 71.5 | 0/13 | 120.9 | 6.72 | 9/18 | 0.5893 | 0.727 |

Physics verdicts (H0_X, band) are stable across the full post-0.0.2 change history. The r_s form correction
(validator 0.1.1) and BBN frozen-field fix (guard 0.1.2) were applied before 0.0.2 shipped.

**BAO findings:** WQI routes beat the ΛCDM baseline (chi²=33.6). WLI tension increases monotonically with
steeper potentials (higher α). BAO chi² values from v0.7.0/v0.1.0 (using r_s_Mpc) are superseded.

**RSD findings:** WQI routes are competitive on f·σ₈ (chi²=27-30, reduced≈1.5-1.7). sigma8_X for all routes
is below Planck sigma8=0.8111, consistent with the known S8 tension. WLI routes show the same monotonic
ranking on RSD as on BAO. The two probes confirm each other's ordering, strengthening confidence in the
route ranking.

---

## Versioning rule

TFA project releases, per-script version/build numbers, and the settings schema
version are tracked independently. A project release is a snapshot that approves
a specific set of script builds; it does not force scripts to share a version.
`approved-version.json` in each script folder records the current approved build.
