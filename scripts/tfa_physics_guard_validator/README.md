# tfa_physics_guard_validator Approved Versions

| Version | Build | API | TFA release | Folder | Validator dep | Status |
|---|---:|---:|---:|---|---|---|
| `0.1.4` | `0001` | `0.1` | `0.0.2` | `v0.1.4-build.0001/` | `tfa_acoustic_validator` v0.1.5 | approved |
| `0.1.3` | `0001` | `0.1` | `0.0.2` | `v0.1.3-build.0001/` | `tfa_acoustic_validator` v0.1.2 | superseded |
| `0.1.2` | `0001` | `0.1` | `0.0.2` | `v0.1.2-build.0001/` | `tfa_acoustic_validator` v0.1.1 | superseded |
| `0.1.1` | `0001` | `0.1` | `0.0.2` | `v0.1.1-build.0001/` | `tfa_acoustic_validator` v0.1.1 | superseded (BBN extrapolation bug) |
| `0.1.0` | `0001` | `0.1` | `0.0.2` | `v0.1.0-build.0001/` | `tfa_acoustic_validator` v0.1.0 | superseded |

`0.1.4` replaces the `build_potential_from_form` catalog call with
`build_potential_from_settings` — reads the `V_of_phi` expression directly from
the frozen `environment-settings.json` in the run folder. No form name or
parameter catalog needed. Pins to `tfa_acoustic_validator` v0.1.5. In-memory
endpoints are unchanged.

`0.1.3` added the **file-based entry point** `run_physics_guard_validator(run_folder)`.
Reads `z`/`w_phi` from the engine's `trajectory.csv`, rebuilds the potential via
`build_potential_from_form` (now superseded) to compute the frozen-field BBN
density, runs the four guards, writes `physics_guards.csv`, enriches the summary.

`0.1.2` fixes the BBN guard: `Omega_phi(z_bbn)` is now computed in the
frozen-field limit instead of by evaluating the dense ODE solution at
`bbn_z` (default 1e9), which lay outside the integrated interval `[0, z_ini=1e6]`
and fabricated a spurious kinetic term (reported `Omega_phi_BBN` ~28 orders of
magnitude too high). Other guards are unchanged. `0.1.1` (repoint only) and
`0.1.0` are retained for comparison.
