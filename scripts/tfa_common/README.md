# tfa_common Approved Versions

This folder contains approved package copies of the `tfa_common` script.

| Version | Build | API | TFA release | Folder | Role | Status |
|---|---:|---:|---:|---|---|---|
| `0.9.1` | `0002` | `0.1` | `0.0.4` | `v0.9.1-build.0002/` | hub — pins T001 specialist builds | approved |
| `0.9.1` | `0001` | `0.1` | `0.0.3` | `v0.9.1-build.0001/` | B001 BOM resilience fix | superseded |
| `0.9.0` | `0001` | `0.1` | `0.0.2` | `v0.9.0-build.0001/` | hub — 5 specialists, adds RSD validator | superseded |
| `0.8.0` | `0001` | `0.1` | `0.0.2` | `v0.8.0-build.0001/` | hub — 4 specialists, r_drag BAO ruler | superseded |
| `0.7.0` | `0001` | `0.1` | `0.0.2` | `v0.7.0-build.0001/` | hub — 4 specialists (r_s BAO ruler, superseded) | superseded |
| `0.6.0` | `0001` | `0.1` | `0.0.2` | `v0.6.0-build.0001/` | hub + plot exporter (3 specialists) | superseded |
| `0.5.0` | `0001` | `0.1` | `0.0.2` | `v0.5.0-build.0001/` | settings-driven hub (2 specialists) | superseded |
| `0.4.0` | `0001` | `0.1` | `0.0.2` | `v0.4.0-build.0001/` | file-based hub with subprocess orchestration | superseded |
| `0.3.0` | `0001` | `0.1` | `0.0.2` | `v0.3.0-build.0001/` | file-based hub (run initializer only) | superseded |
| `0.2.0` | `0001` | `0.1` | `0.0.2` | `v0.2.0-build.0001/` | in-memory hub / facade | superseded |
| `0.1.0` | `0001` | `0.1` | `0.0.2` | `v0.1.0-build.0001/` | legacy monolith | reference only |

**`0.9.1 build 0002` — T001 specialist pointer update.** Updates `_SPECIALIST_BUILDS`
to pin `tfa_acoustic_validator v0.1.5-build.0001` and `tfa_plot_exporter v0.1.1-build.0001`.
No logic changes. Version stays `0.9.1`; build advances to `0002` per the
immutable-build-folder convention.

**`0.9.1 build 0001` — B001 BOM resilience.** `_read_json` now opens with
`encoding="utf-8-sig"` (strips BOM silently). Frozen settings copy uses
parse-and-reserialize instead of `shutil.copy2`, guaranteeing BOM-free run folders.

**`0.9.0` — RSD validator.** Adds `tfa_rsd_validator v0.1.0` as the fifth in-process
non-fatal specialist. Integrates the linear growth ODE against H_X(z) and computes
f·σ₈(z) against the bundled 18-point gold compilation. Physics verdict unchanged.

**`0.8.0` — BAO ruler fix.** Pins `tfa_acoustic_validator v0.1.4` and
`tfa_bao_validator v0.1.1`. The acoustic validator now computes `r_drag_Mpc`
(drag-epoch sound horizon, ≈ 146.9 Mpc) alongside `r_s_Mpc` (z_star, ≈ 144.4 Mpc).
The BAO validator uses `r_drag_Mpc` as the ruler, consistent with how DESI DR2
reports its D_X/r_d observables. Previous WLI/WQI chi² values computed with the
old r_s ruler are invalidated. Physics verdicts (H0_X, band) are unchanged.

**`0.7.0` — BAO validator.** Adds `tfa_bao_validator v0.1.0` as the fourth
in-process specialist. Used `r_s_Mpc` as the BAO ruler — superseded by `0.8.0`.

**`0.6.0` — adds the presentation layer.** Identical to `0.5.0` except a third
specialist, `tfa_plot_exporter v0.1.0`, is called in-process after the two physics
specialists. Plot exporter failure is **non-fatal**: the hub records the error but
returns `code="OK"` if the physics specialists passed. Each run folder now also
contains up to 10 plot files (5 diagnostics × .png/.pdf).

**`0.5.0` — settings-driven, in-process.** The researcher defines the potential
in `tfa-environment-settings.json` under `user_adjustable.potential` as
expression strings (`V_of_phi`, `dV_dphi`, `parameters`, `initial_phi`). The call
is `tfa.run()` — no form argument, no catalog, no subprocess. The hub evaluates
expressions to callables, validates the `PotentialRoute`, creates the run folder,
freezes settings, then calls `run_acoustic_validator` and
`run_physics_guard_validator` **in-process**. Works for any thawing scalar field.

**`0.4.0` — subprocess orchestration.** `run(form)` took a form dict with a named
`form` field (`peebles_vilenkin`, `wqi`, …) and called specialists as subprocesses
via `subprocess.run`. Required a hardcoded catalog in the engine to reconstruct
callables from JSON. Superseded by 0.5.0.

**`0.3.0` — file-based run folder (phase 1).** Per `system-design.md`, the hub
now works through a run folder on disk. Given a *form* (a serializable potential
spec), `create_run(form)`: (1) creates a run folder `prefix_datetime_guid`,
(2) freezes a copy of `environment-settings.json` into it, (3) creates
`run_results_summary.json`, and (4) fills it with the initial run metadata +
contract. It then **stops** — orchestration of the specialized scripts is not
yet wired. No physics is performed; the form is only validated structurally.
Returns the agreed `(Code, Desc)` plus the created paths.

`0.2.0` was the in-memory facade (built the `PotentialRoute` and orchestrated
the specialists in memory); it is superseded by the file-based model but kept
for reference. `0.1.0` is the original monolith, reference only. Use the newest
approved folder unless a reproducibility record requires an older one.

