# tfa_density_validator

Dark-energy density-sector validator. **Strictly CPL-free** — no indicator in
this specialist involves any (w0, wa) parametrization; everything is computed
from the route's exact integrated trajectory or echoed from the engine summary.
The CPL fidelity audit is a separate specialist (`tfa_cpl_fidelity_validator`).

## Role

| Aspect | Value |
|---|---|
| Entry point | `run_density_validator(run_folder) -> (Code, Desc)` |
| Inputs | `run_results_summary.json`, `trajectory.csv`, frozen `environment-settings.json` |
| External reference | `user_adjustable.desi_reference` (DESI DR2 w0waCDM, DESI+CMB+DESY5) |
| Gating | **Non-gated** — runs for every completed engine run, including EXCLUDED routes |
| Fatal? | No (non-fatal in the hub chain) |
| Dependency | `tfa_core` only (specialists never import each other) |

## Indicators

1. **H0 pull (the only pull):** `(H0_X - 66.74) / 0.56` with a
   PASS_1/2/3SIGMA / OUTSIDE_3SIGMA class. Distinct from the engine's
   `delta_X` (which is vs the reference cosmology H0_ref = 67.36 — a different
   reference, both labeled). Includes a `bands_consistent` cross-check that the
   settings `h0_bands` still equal the `desi_reference` mean +/- 1/2/3 sigma,
   so the pull class can never silently contradict the engine's band verdict.
2. **Energy budget (descriptive, no pulls):** echoes the engine's
   `energy_fractions` block (never recomputes Omega_m by a new convention — no
   third Omega_m number), rechecks flat closure at z = 0 from `trajectory.csv`,
   and quotes DESI's Omega_m **reference-only**. There is deliberately **no
   Omega_m pull**: the route, Planck, and DESI all share omega_m ~ 0.142-0.143,
   so it would double-count the H0 pull.
3. **f_DE(z) = rho_phi(z)/rho_phi(0)** = `Omega_phi(z) E_X(z)^2 / Omega_phi(0)`
   (exact). LCDM baseline is f_DE = 1. Reports f_DE at marker redshifts and the
   max |f_DE - 1| over 0 <= z <= `fde_z_max`.
4. **Thawing-strength route properties:** `1 + w(0)`; `z_thaw` (largest z where
   1 + w exceeds `thaw_threshold`); `wa_tangent = -dw/da at a=1` — a derivative
   of the exact route's w (the WQI source-paper convention), **not a CPL fit**.

## Outputs

- `density_results.csv` — indicator, value, reference, reference_sigma, pull, status, note
- `density_fde.png/pdf` — f_DE(z) vs the f_DE = 1 LCDM line
- Summary enrichment under `results["density_validator"]`

## Settings block (`user_adjustable.density_validator`)

```json
{ "enabled": true, "fde_z_max": 3.0, "fde_marker_z": [0.5, 1.0, 2.0], "thaw_threshold": 0.01 }
```

Missing block defaults to the values above (back-compat with frozen settings
older than file version 1.2.0). A missing `desi_reference` block records a skip.

## Version history

| Version | Build | Notes |
|---|---|---|
| 0.1.0 | 0001 | Initial release (T004 deliverable 5b, CPL-free redesign). |
