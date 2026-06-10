"""
TFA acoustic validator (engine) - redesigned build.

Computes the acoustic verdict for a thawing scalar route: H0_required (H0_X),
delta_X, the band verdict, and the gated normalized history, plus the energy
budget and a self-consistency field. It is the only specialist that integrates
the scalar ODE; downstream specialists read its trajectory.csv.

What changed relative to 0.1.5 (the agreed redesign, deliverables item 1):

1. Depends on ``tfa_core`` for the ODE, settings, potential builder, FLRW
   helpers, I/O, trace, errors, and the encoding policy. It does NOT duplicate
   any of that and does NOT import any other specialist. The acoustic anchor
   physics (z_star, z_drag, r_s integral, sound speed) stays here.

2. NORMALIZATION FIX. H0_X is solved from the NORMALIZED shape E_X with
   E_X(0) = 1, using I_X = integral_0^z* dz / E_X. Build 0.1.5 used the raw,
   un-normalized shape in the distance integral, which inflated H0_X by
   1/raw_E(0). The output history H_X(z) = H0_X * E_X(z) now reproduces the
   target distance D_target by construction.

3. rs_calibration REMOVED. D_target = r_star / theta_obs is built from a sourced
   sound horizon (Planck r_*, overridable in settings) and the observed acoustic
   angle. No LCDM-distance calibration fudge. The EH-fit sound horizon is still
   computed and reported for transparency.

4. delta_X is an audit signature only (H0_X / H0_ref - 1); not consumed
   downstream.

5. Self-consistency field added: omega_m_out = Omega_m_0 * (H0_X/100)^2 and
   omega_m_residual_pct = omega_m_out / OMH2 - 1, surfacing the physical-density
   residual that build 0.1.5 left latent.

Identity: tfa_acoustic_validator 0.1.6 build 0001.
"""

from __future__ import annotations

import csv
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import numpy as np
from scipy.integrate import quad


# ---------------------------------------------------------------------------
# Resolve tfa_core (the only cross-script dependency) and import it.
# ---------------------------------------------------------------------------
_THIS_DIR = Path(__file__).resolve().parent
_CORE_CANDIDATES = (
    _THIS_DIR.parent.parent / "tfa_core" / "v0.1.0-build.0001",
    _THIS_DIR.parent.parent.parent / "tfa_core" / "v0.1.0-build.0001",
)
for _candidate in (_THIS_DIR, *_CORE_CANDIDATES):
    if _candidate.exists():
        _text = str(_candidate)
        if _text not in sys.path:
            sys.path.insert(0, _text)

import tfa_core as core  # noqa: E402


ArrayLike = Sequence[float] | np.ndarray
PotentialRoute = core.PotentialRoute
DEFAULT_ENVIRONMENT_SETTINGS = core.DEFAULT_ENVIRONMENT_SETTINGS

TFA_PROJECT_RELEASE = "0.0.4"
SCRIPT_NAME = "tfa_acoustic_validator"
SCRIPT_VERSION = "0.1.6"
SCRIPT_BUILD = "0001"
SCRIPT_API_VERSION = "0.1"
SETTINGS_SCHEMA_VERSION = "0.1"

# Sourced sound horizons (Planck 2018 VI, base-LCDM). Used unless overridden in
# settings (acoustic_priors.r_star_Mpc / r_drag_Mpc). r_* is the comoving sound
# horizon at recombination; r_drag is the drag-epoch ruler used by BAO.
PLANCK_R_STAR_MPC = 144.39
PLANCK_R_DRAG_MPC = 147.05


def script_identity() -> Mapping[str, str]:
    """Return script metadata for audit payloads, logs, and release notes."""

    return {
        "tfa_project_release": TFA_PROJECT_RELEASE,
        "script_name": SCRIPT_NAME,
        "script_version": SCRIPT_VERSION,
        "script_build": SCRIPT_BUILD,
        "script_api_version": SCRIPT_API_VERSION,
        "settings_schema_version": SETTINGS_SCHEMA_VERSION,
    }


# ===========================================================================
# Acoustic anchor physics (acoustic-specific; stays in this specialist)
# ===========================================================================

def compute_z_star(config: core.AcousticConfig) -> float:
    """Hu-Sugiyama (1996) photon-decoupling redshift fit."""

    g1 = 0.0783 * config.OBH2 ** -0.238 / (1.0 + 39.5 * config.OBH2 ** 0.763)
    g2 = 0.560 / (1.0 + 21.1 * config.OBH2 ** 1.81)
    return float(1048.0 * (1.0 + 0.00124 * config.OBH2 ** -0.738) * (1.0 + g1 * config.OMH2 ** g2))


def compute_z_drag(config: core.AcousticConfig) -> float:
    """Eisenstein-Hu (1998) baryon drag-epoch redshift fit (Eq. 4)."""

    b1 = 0.313 * config.OMH2 ** -0.419 * (1.0 + 0.607 * config.OMH2 ** 0.674)
    b2 = 0.238 * config.OMH2 ** 0.223
    return float(
        1345.0 * config.OMH2 ** 0.251 / (1.0 + 0.659 * config.OMH2 ** 0.828)
        * (1.0 + b1 * config.OBH2 ** b2)
    )


def baryon_to_photon_momentum_ratio(z: float | np.ndarray, config: core.AcousticConfig) -> np.ndarray:
    """Baryon-to-photon momentum ratio R(z)."""

    z_arr = np.asarray(z, dtype=float)
    return 31500.0 * config.OBH2 * (config.T0_K / 2.7) ** (-4) / (1.0 + z_arr)


def photon_baryon_sound_speed_kms(
    z: float | np.ndarray,
    cosmology: core.CosmologyContext,
    config: core.AcousticConfig,
) -> np.ndarray:
    """Photon-baryon sound speed in km/s."""

    ratio = baryon_to_photon_momentum_ratio(z, config)
    return cosmology.c_kms / np.sqrt(3.0 * (1.0 + ratio))


def compute_r_s_Mpc(
    z_event: float,
    cosmology: core.CosmologyContext,
    config: core.AcousticConfig,
) -> float:
    """Comoving sound horizon to ``z_event`` (Mpc), pre-recombination integrand.

    Matter+radiation only (scalar inert for z >= z_event), the 31500 R-form, and
    the u = ln(1+z) substitution. No calibration is applied; this is the raw
    fitting-formula value, reported for transparency.
    """

    h = cosmology.H0_ref_kms / 100.0
    omega_m = config.OMH2 / h**2
    omega_r = config.OGH2 * (1.0 + 0.2271 * config.NEFF) / h**2

    def integrand(u: float) -> float:
        z = np.expm1(u)
        E2 = omega_r * (1.0 + z) ** 4 + omega_m * (1.0 + z) ** 3
        H = cosmology.H0_ref_kms * np.sqrt(E2)
        c_s = photon_baryon_sound_speed_kms(z, cosmology, config)
        return float(c_s / H * (1.0 + z))

    value, _ = quad(
        integrand, np.log1p(z_event), np.log1p(config.z_integral_max), epsrel=1e-9, limit=500
    )
    return float(value)


@dataclass(frozen=True)
class AcousticAnchor:
    """Candidate-independent acoustic reference (no calibration)."""

    z_star: float
    theta_obs: float
    r_star_Mpc: float          # sourced sound horizon used for D_target
    D_target_Mpc: float        # = r_star / theta_obs
    r_s_computed_Mpc: float     # EH fitting-formula r_s, reported for transparency
    D_M_LCDM_Mpc: float
    theta_lcdm: float           # r_star / D_M_LCDM (shows anchor consistency)
    z_drag: float
    r_drag_Mpc: float           # sourced drag ruler used by BAO
    r_drag_computed_Mpc: float
    r_star_source: str
    r_drag_source: str


@dataclass(frozen=True)
class H0XResult:
    benchmark_id: str
    raw_E0: float
    I_X: float
    D_M_X_Mpc: float
    D_target_Mpc: float
    H0_X_kms: float
    H0_ref_kms: float
    Omega_m_X: float
    delta_X: float
    status: str


def _acoustic_priors_section(settings: Mapping[str, Any]) -> Mapping[str, Any]:
    user = core.user_adjustable_settings(settings)
    return core._require_mapping(user, "acoustic_priors")


def compute_acoustic_anchor(
    cosmology: core.CosmologyContext,
    config: core.AcousticConfig,
    settings: Mapping[str, Any] | None = None,
) -> AcousticAnchor:
    """Build the shared acoustic anchor.

    D_target = r_star / theta_obs, where r_star is the sourced sound horizon
    (Planck r_*, or settings override). The EH-fit r_s and the LCDM distance are
    computed and reported so the anchor's consistency is visible.
    """

    z_star = compute_z_star(config)
    z_drag = compute_z_drag(config)
    theta_obs = config.theta_star_target

    # Sourced rulers, with optional settings overrides.
    r_star = PLANCK_R_STAR_MPC
    r_star_source = "Planck2018_r_star"
    r_drag = PLANCK_R_DRAG_MPC
    r_drag_source = "Planck2018_r_drag"
    if settings is not None:
        priors = _acoustic_priors_section(settings)
        if priors.get("r_star_Mpc") is not None:
            r_star = float(priors["r_star_Mpc"])
            r_star_source = "settings.r_star_Mpc"
        if priors.get("r_drag_Mpc") is not None:
            r_drag = float(priors["r_drag_Mpc"])
            r_drag_source = "settings.r_drag_Mpc"

    D_target = r_star / theta_obs

    # Reported-only computed values (transparency / anchor cross-check).
    r_s_computed = compute_r_s_Mpc(z_star, cosmology, config)
    r_drag_computed = compute_r_s_Mpc(z_drag, cosmology, config)
    D_M_LCDM = core.comoving_distance_Mpc(
        lambda z: float(core.H_lcdm_kms(z, cosmology)), z_star, cosmology
    )
    theta_lcdm = r_star / D_M_LCDM

    return AcousticAnchor(
        z_star=z_star,
        theta_obs=theta_obs,
        r_star_Mpc=r_star,
        D_target_Mpc=D_target,
        r_s_computed_Mpc=r_s_computed,
        D_M_LCDM_Mpc=D_M_LCDM,
        theta_lcdm=theta_lcdm,
        z_drag=z_drag,
        r_drag_Mpc=r_drag,
        r_drag_computed_Mpc=r_drag_computed,
        r_star_source=r_star_source,
        r_drag_source=r_drag_source,
    )


# ===========================================================================
# H0_X solve (Option A, normalized shape)
# ===========================================================================

def solve_h0x(
    route: PotentialRoute,
    cosmology: core.CosmologyContext,
    anchor: AcousticAnchor,
    sol: object,
    acoustic_config: core.AcousticConfig,
    bands: core.AcousticBands,
) -> H0XResult:
    """Solve H0_X from the NORMALIZED shape, Option A closed form.

        E_X(z) = raw_E(z) / raw_E(0),   E_X(0) = 1
        I_X    = integral_0^z* dz / E_X(z)
        H0_X   = c * I_X / D_target

    The output history H_X = H0_X * E_X then has D_M(z*) = D_target by
    construction, so it reproduces the observed acoustic angle.
    """

    raw_E0 = core.evaluate_raw_E_at_z(route, cosmology, sol, 0.0)
    if raw_E0 <= 0.0:
        raise core.TFAError(
            code="TFA_H0X_SOLVE_ERROR",
            message="raw_E(0) must be positive",
            phase="h0x_solve",
        )

    def inv_E_X(z: float) -> float:
        # 1 / E_X = raw_E0 / raw_E(z)
        return raw_E0 / core.evaluate_raw_E_at_z(route, cosmology, sol, float(z))

    I_X, _ = quad(inv_E_X, 0.0, anchor.z_star, limit=500, epsrel=1e-8)
    if I_X <= 0.0:
        raise core.TFAError(
            code="TFA_H0X_SOLVE_ERROR", message="I_X must be positive", phase="h0x_solve"
        )

    H0_X = cosmology.c_kms * I_X / anchor.D_target_Mpc
    D_M_X = cosmology.c_kms * I_X / H0_X  # equals D_target by construction
    Omega_m_X = acoustic_config.OMH2 / (H0_X / 100.0) ** 2
    delta_X = H0_X / cosmology.H0_ref_kms - 1.0

    return H0XResult(
        benchmark_id=route.benchmark_id,
        raw_E0=float(raw_E0),
        I_X=float(I_X),
        D_M_X_Mpc=float(D_M_X),
        D_target_Mpc=float(anchor.D_target_Mpc),
        H0_X_kms=float(H0_X),
        H0_ref_kms=float(cosmology.H0_ref_kms),
        Omega_m_X=float(Omega_m_X),
        delta_X=float(delta_X),
        status=bands.classify(float(H0_X)),
    )


# ===========================================================================
# Trajectory / energy fractions / self-consistency
# ===========================================================================

def _w_and_omega_from_state(
    route: PotentialRoute,
    phi: np.ndarray,
    phi_N: np.ndarray,
    H2: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Return (w_phi, Omega_phi) from scalar state arrays."""

    V = np.asarray(route.V(phi), dtype=float)
    kinetic = 0.5 * H2 * phi_N**2
    w_phi = (kinetic - V) / (kinetic + V)
    Omega_phi = (kinetic + V) / (3.0 * H2)
    return w_phi, Omega_phi


def compute_energy_fractions(
    z_arr: np.ndarray,
    omega_phi: np.ndarray,
    H0_X_kms: float,
    cosmology: core.CosmologyContext,
    acoustic_config: core.AcousticConfig,
) -> dict:
    """Energy budget at z=0, equality redshifts, and the self-consistency field.

    z_arr is descending (z[-1] ~ 0); omega_phi is ascending (omega_phi[-1] ~ 0.68).
    """

    Omega_phi_0 = float(omega_phi[-1])
    Or_route0 = cosmology.Omega_r0 * (cosmology.H0_ref_kms / H0_X_kms) ** 2
    Omega_m_0 = 1.0 - Omega_phi_0 - Or_route0
    z_eq_lcdm = float((cosmology.Omega_DE / cosmology.Omega_m0) ** (1.0 / 3.0) - 1.0)

    diff = omega_phi - 0.5
    z_eq_route = None
    for i in range(len(diff) - 1):
        if diff[i] * diff[i + 1] < 0:
            t = diff[i] / (diff[i] - diff[i + 1])
            z_eq_route = float(z_arr[i] + t * (z_arr[i + 1] - z_arr[i]))
            break

    # Self-consistency: the physical matter density the finished route carries,
    # vs the input early-anchor density OMH2.
    h_X = H0_X_kms / 100.0
    omega_m_out = Omega_m_0 * h_X**2
    omega_m_residual_pct = 100.0 * (omega_m_out / acoustic_config.OMH2 - 1.0)

    result: dict = {
        "Omega_phi_0": round(Omega_phi_0, 6),
        "Omega_m_0": round(Omega_m_0, 6),
        "z_eq_lcdm": round(z_eq_lcdm, 6),
        "z_eq_route": round(z_eq_route, 6) if z_eq_route is not None else None,
        "delta_z_eq": round(z_eq_route - z_eq_lcdm, 6) if z_eq_route is not None else None,
        "omega_m_out": round(omega_m_out, 8),
        "omega_m_input_OMH2": round(float(acoustic_config.OMH2), 8),
        "omega_m_residual_pct": round(omega_m_residual_pct, 4),
    }
    if z_eq_route is None:
        result["z_eq_note"] = "no Omega_phi=0.5 crossing found within trajectory z-range"
    return result


# ===========================================================================
# CSV writers
# ===========================================================================

SUMMARY_FILENAME = "run_results_summary.json"
FROZEN_SETTINGS_FILENAME = "environment-settings.json"
TRAJECTORY_FILENAME = "trajectory.csv"
SHAPE_CSV_FILENAME = "expansion_history_shape.csv"
HISTORY_CSV_FILENAME = "expansion_history_h0x_normalized.csv"
W_OF_Z_CSV_FILENAME = "w_of_z.csv"


def _write_trajectory_csv(path, N, z, phi, phi_N, E_X, H_X, w_phi, Omega_phi) -> int:
    with Path(path).open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["N", "z", "a", "phi", "dphi_dN", "E_X", "H_X", "w_phi", "Omega_phi"])
        for i in range(len(N)):
            w.writerow([
                f"{N[i]:.12g}", f"{z[i]:.12g}", f"{np.exp(N[i]):.12g}",
                f"{phi[i]:.12g}", f"{phi_N[i]:.12g}", f"{E_X[i]:.12g}",
                f"{H_X[i]:.12g}", f"{w_phi[i]:.12g}", f"{Omega_phi[i]:.12g}",
            ])
    return int(len(N))


def _write_shape_csv(path, z, E_X, H0_X, H0_ref, delta_X, shape_residual, shape_check) -> None:
    with Path(path).open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["# quantity", "E_X"])
        w.writerow(["# units", "dimensionless"])
        w.writerow(["# normalization_mode", "shape_only"])
        w.writerow(["# H0_X", f"{H0_X:.12g}"])
        w.writerow(["# H0_Lambda", f"{H0_ref:.12g}"])
        w.writerow(["# delta_X", f"{delta_X:.12g}"])
        w.writerow(["# shape_residual", f"{shape_residual:.12g}"])
        w.writerow(["# shape_check", shape_check])
        w.writerow(["z", "E_X"])
        for zi, ei in zip(z, E_X):
            w.writerow([f"{zi:.12g}", f"{ei:.12g}"])


def _write_history_csv(path, z, H_X, H0_X, H0_ref, delta_X, norm_residual, norm_tol, norm_check) -> None:
    with Path(path).open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["# quantity", "H_X"])
        w.writerow(["# units", "km s^-1 Mpc^-1"])
        w.writerow(["# normalization_mode", "h0x_normalized"])
        w.writerow(["# H0_X", f"{H0_X:.12g}"])
        w.writerow(["# H0_Lambda", f"{H0_ref:.12g}"])
        w.writerow(["# delta_X", f"{delta_X:.12g}"])
        w.writerow(["# normalization_residual", f"{norm_residual:.12g}"])
        w.writerow(["# normalization_tolerance", f"{norm_tol:.12g}"])
        w.writerow(["# normalization_check", norm_check])
        w.writerow(["z", "H_X"])
        for zi, hi in zip(z, H_X):
            w.writerow([f"{zi:.12g}", f"{hi:.12g}"])


def _write_w_of_z_csv(path, z, w_phi, H0_X, H0_ref, delta_X, band) -> None:
    with Path(path).open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["# quantity", "w_phi"])
        w.writerow(["# units", "dimensionless"])
        w.writerow(["# H0_X", f"{H0_X:.12g}"])
        w.writerow(["# H0_Lambda", f"{H0_ref:.12g}"])
        w.writerow(["# delta_X", f"{delta_X:.12g}"])
        w.writerow(["# band", band])
        w.writerow(["z", "w_phi"])
        for zi, wi in zip(z, w_phi):
            w.writerow([f"{zi:.12g}", f"{wi:.12g}"])


def _export_config_from_settings(settings: Mapping[str, object]) -> Mapping[str, object]:
    user = core.user_adjustable_settings(settings)
    exp = core._require_mapping(user, "export")
    gate = core._require_mapping(user, "export_gate")
    accepted = [str(b).upper() for b in gate.get("accepted_bands", [])]
    return {
        "low_z_step": float(exp["low_z_step"]),
        "low_z_max": float(exp["low_z_max"]),
        "shape_tolerance": float(exp["shape_tolerance"]),
        "normalization_tolerance": float(exp["normalization_tolerance"]),
        "gate_enabled": bool(gate.get("enabled", True)),
        "accepted_bands": accepted,
    }


def _export_grid(z_star: float, low_z_step: float, low_z_max: float) -> np.ndarray:
    grid = np.concatenate([np.arange(0.0, low_z_max + low_z_step / 2.0, low_z_step), [z_star]])
    return np.sort(np.unique(grid))


# ===========================================================================
# File-based run-folder entry point
# ===========================================================================

def run_acoustic_validator(run_folder: str | Path) -> tuple[str, str]:
    """File-based engine entry point. Returns ``(Code, Desc)``.

    Reads the contract + frozen settings, rebuilds the potential (via tfa_core),
    integrates the route once, solves H0_X from the normalized shape, writes
    trajectory.csv plus the gated history CSVs, and enriches
    run_results_summary.json under results["acoustic_validator"].
    """

    try:
        run_folder = Path(run_folder)
        summary_path = run_folder / SUMMARY_FILENAME
        settings_path = run_folder / FROZEN_SETTINGS_FILENAME
        if not summary_path.exists():
            return ("Error", f"{SUMMARY_FILENAME} not found in {run_folder}")
        if not settings_path.exists():
            return ("Error", f"{FROZEN_SETTINGS_FILENAME} not found in {run_folder}")

        summary = core.read_json(summary_path)
        contract = summary.get("contract")
        if not isinstance(contract, Mapping):
            return ("Error", "run_results_summary.json has no contract section")

        settings = core.load_environment_settings(settings_path)
        cosmology = core.cosmology_from_settings(settings)
        acoustic_config = core.acoustic_config_from_settings(settings)
        bands = core.acoustic_bands_from_settings(settings)
        integration_config = core.integration_config_from_settings(settings)

        V, dV_dphi = core.build_potential_from_settings(settings, cosmology)
        potential_spec = core.potential_from_settings(settings)
        benchmark_id = str(
            potential_spec.get("benchmark_id") or contract.get("benchmark_id") or "unnamed"
        )
        route = core.PotentialRoute(
            benchmark_id=benchmark_id,
            V=V,
            dV_dphi=dV_dphi,
            initial_phi=float(potential_spec["initial_phi"]),
            initial_phi_N=float(potential_spec.get("initial_phi_N", 0.0)),
        )

        # Physics: integrate once, solve H0_X.
        anchor = compute_acoustic_anchor(cosmology, acoustic_config, settings)
        sol = core.integrate_scalar_route(route, cosmology, integration_config)
        h0x = solve_h0x(route, cosmology, anchor, sol, acoustic_config, bands)

        # Dense trajectory on the solver grid (ascending N, z=0 included).
        N = np.sort(np.asarray(sol.t, dtype=float))
        y = sol.sol(N)
        phi, phi_N, H2, raw_E = core.eval_route_state(route, cosmology, N, y)
        z = np.expm1(-N)
        E_X = raw_E / h0x.raw_E0
        H_X = h0x.H0_X_kms * E_X
        w_phi, Omega_phi = _w_and_omega_from_state(route, phi, phi_N, H2)

        rows = _write_trajectory_csv(
            run_folder / TRAJECTORY_FILENAME, N, z, phi, phi_N, E_X, H_X, w_phi, Omega_phi
        )

        # Gated contract CSVs evaluated on the low-z export grid.
        cfg = _export_config_from_settings(settings)
        gate_accepted = (not cfg["gate_enabled"]) or (h0x.status in cfg["accepted_bands"])
        history_files: dict[str, object] = {"shape": None, "normalized_history": None}
        shape_check = None
        normalization_check = None
        if gate_accepted:
            grid = _export_grid(anchor.z_star, cfg["low_z_step"], cfg["low_z_max"])
            raw_E_grid = np.array(
                [core.evaluate_raw_E_at_z(route, cosmology, sol, float(zz)) for zz in grid], dtype=float
            )
            E_X_grid = raw_E_grid / h0x.raw_E0
            H_X_grid = h0x.H0_X_kms * E_X_grid
            shape_residual = float(E_X_grid[0] - 1.0)  # grid[0] == 0.0
            normalization_residual = float((H_X_grid[0] - h0x.H0_X_kms) / h0x.H0_X_kms)
            shape_check = "PASS" if abs(shape_residual) <= cfg["shape_tolerance"] else "FAIL"
            normalization_check = "PASS" if abs(normalization_residual) <= cfg["normalization_tolerance"] else "FAIL"
            _write_shape_csv(
                run_folder / SHAPE_CSV_FILENAME, grid, E_X_grid,
                h0x.H0_X_kms, h0x.H0_ref_kms, h0x.delta_X, shape_residual, shape_check,
            )
            _write_history_csv(
                run_folder / HISTORY_CSV_FILENAME, grid, H_X_grid,
                h0x.H0_X_kms, h0x.H0_ref_kms, h0x.delta_X,
                normalization_residual, cfg["normalization_tolerance"], normalization_check,
            )
            w_grid_state = core.eval_route_state(route, cosmology, -np.log1p(grid), sol.sol(-np.log1p(grid)))
            w_phi_grid, _ = _w_and_omega_from_state(route, w_grid_state[0], w_grid_state[1], w_grid_state[2])
            _write_w_of_z_csv(
                run_folder / W_OF_Z_CSV_FILENAME, grid, w_phi_grid,
                h0x.H0_X_kms, h0x.H0_ref_kms, h0x.delta_X, h0x.status,
            )
            history_files = {
                "shape": SHAPE_CSV_FILENAME,
                "normalized_history": HISTORY_CSV_FILENAME,
                "w_of_z": W_OF_Z_CSV_FILENAME,
            }

        energy_fractions = compute_energy_fractions(z, Omega_phi, h0x.H0_X_kms, cosmology, acoustic_config)

        # Enrich the summary.
        summary = core.read_json(summary_path)
        results = summary.setdefault("results", {})
        results["acoustic_validator"] = {
            "status": "OK",
            "script": script_identity(),
            "method": "OptionA_normalized_shape",
            "H0_X_kms": h0x.H0_X_kms,
            "delta_X": h0x.delta_X,
            "band": h0x.status,
            "H0_ref_kms": h0x.H0_ref_kms,
            "Omega_m_X": h0x.Omega_m_X,
            "raw_E0": h0x.raw_E0,
            "I_X": h0x.I_X,
            "D_M_X_Mpc": h0x.D_M_X_Mpc,
            "D_target_Mpc": h0x.D_target_Mpc,
            "acoustic_anchor": {
                "z_star": anchor.z_star,
                "theta_obs": anchor.theta_obs,
                "r_star_Mpc": anchor.r_star_Mpc,
                "r_s_Mpc": anchor.r_star_Mpc,  # alias (decoupling-epoch r_s); RSD sentinel + back-compat
                "r_star_source": anchor.r_star_source,
                "D_target_Mpc": anchor.D_target_Mpc,
                "r_s_computed_Mpc": anchor.r_s_computed_Mpc,
                "D_M_LCDM_Mpc": anchor.D_M_LCDM_Mpc,
                "theta_lcdm": anchor.theta_lcdm,
                "z_drag": anchor.z_drag,
                "r_drag_Mpc": anchor.r_drag_Mpc,
                "r_drag_source": anchor.r_drag_source,
                "r_drag_computed_Mpc": anchor.r_drag_computed_Mpc,
                "calibration_applied": False,
            },
            "trajectory_file": TRAJECTORY_FILENAME,
            "trajectory_rows": rows,
            "export_gate": {
                "enabled": cfg["gate_enabled"],
                "accepted": gate_accepted,
                "band": h0x.status,
                "accepted_bands": cfg["accepted_bands"],
            },
            "shape_check": shape_check,
            "normalization_check": normalization_check,
            "expansion_history_files": history_files,
            "energy_fractions": energy_fractions,
        }
        core.atomic_write_json(summary_path, summary)

        if gate_accepted:
            return ("OK", f"acoustic_validator complete: H0_X={h0x.H0_X_kms:.4f} band={h0x.status} (history written)")
        return ("OK", f"acoustic_validator complete: H0_X={h0x.H0_X_kms:.4f} band={h0x.status} (export gate rejected; no history)")

    except core.TFAError as exc:
        return ("Error", f"{exc.code}: {exc.message}")
    except BaseException as exc:
        return ("Error", f"{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    _run_folder = sys.argv[1] if len(sys.argv) > 1 else "."
    _code, _desc = run_acoustic_validator(_run_folder)
    print(json.dumps({"code": _code, "desc": _desc}))
    sys.exit(0 if _code == "OK" else 1)
