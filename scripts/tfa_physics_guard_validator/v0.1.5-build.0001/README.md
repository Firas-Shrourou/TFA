# tfa_physics_guard_validator 0.1.5 build 0001

Independent physics-guard specialist. Same four guards as 0.1.4 (canonical,
thawing monotonicity, phantom-crossing, BBN), same file-based entry point
`run_physics_guard_validator(run_folder) -> (Code, Desc)`.

## What changed from 0.1.4

The **only** change is the dependency: 0.1.4 imported `tfa_acoustic_validator`
for the shared `PotentialRoute`, settings, ODE, FLRW state, trace, and error
handling. 0.1.5 imports **`tfa_core`** instead. The guard and the engine are now
independent specialists that share `tfa_core`; the guard no longer reaches into
the engine module.

Name remap (engine -> core):

| 0.1.4 (tfa_acoustic_validator) | 0.1.5 (tfa_core) |
|---|---|
| `PotentialRoute`, `CosmologyContext` | same names |
| `load_environment_settings`, `cosmology_from_settings`, `integration_config_from_settings`, `build_potential_from_settings`, `potential_from_settings`, `user_adjustable_settings`, `_require_mapping` | same names |
| `execution_settings_from_settings` | added to `tfa_core` 0.1.0 |
| `_eval_route_state` | `eval_route_state` |
| `_run_phase(trace, phase, fn)` | `trace.run_phase(phase, fn)` (method) |
| `_phase_error` | `phase_error` |
| `RunTrace`, `TFAError`, `integrate_scalar_route` | same names |
| local `_read_json` / `_atomic_write_json` | `core.read_json` / `core.atomic_write_json` |

No guard logic changed. The frozen-field BBN estimate, the canonical/thawing/
phantom checks, the CSV/summary outputs, and the `(Code, Desc)` contract are
unchanged.

## Verification

- File is pure ASCII, UTF-8 no BOM, and contains no `import tfa_acoustic_validator`.
- Regression on the real WLI_1 run folder (temp copy): the v0.1.5 verdicts and
  diagnostics are byte-identical to the stored v0.1.4 result -
  `overall_pass=True`, all four guards True, `Omega_phi_BBN = 7.4587e-33`,
  `minimum_w_phi = -1.0`, `minimum_delta_w` identical.

## Dependency resolution

The build inserts `../../tfa_core/v0.1.0-build.0001` onto `sys.path` and imports
`tfa_core`. It is the guard's only cross-script dependency (plus numpy and the
standard library).
