"""
tfa_cpl_fidelity_validator.py - CPL compression audit for TFA run folders.

CPL is AUDITED here, never adopted. TFA's rule stands: no CPL (w0, wa)
parametrization ever represents a route. This specialist exists because the
research community (and Boltzmann pipelines such as CLASS) routinely consume
CPL summaries; the researcher therefore needs to know, per route, whether such
a summary can be trusted at all - and where it breaks.

It computes the best-fit CPL to the route's EXACT w(z), then throws the fitted
(w0, wa) into an error report:

  1. dw_max          - max |w_CPL(z) - w_phi(z)| over the fit range (+ its z).
                       The departure grows with z and with thawing strength.
  2. df_de_max       - max relative error in the implied dark-energy density
                       rho_DE(z) under the CPL stand-in.
  3. dDM_star_pct    - percent error in the comoving distance to recombination
                       D_M(z*) under the CPL stand-in: the acoustic-distance
                       error a CPL-fed pipeline (e.g. CLASS) inherits. This is
                       the per-route explainer for the observed CLASS-vs-TFA
                       H0 offset.
  4. Phantom audit   - the canonical route satisfies w >= -1 ALWAYS (certified
                       by the physics guard). The best-fit CPL inherits no such
                       protection: w_CPL(a) = w0 + wa(1-a) crosses w = -1 at
                       a_c = 1 + (1+w0)/wa, i.e. it silently enters the phantom
                       sector the canonical field can never reach. Reported in
                       closed form: cpl_z_cross, cpl_w_min, cpl_phantom_fraction,
                       cpl_w_asymptote = w0+wa (a->0 limit), cpl_phantom_flag.
                       If the researcher feeds the fitted (w0, wa) to any
                       pipeline without noticing this, the output is corrupted.
  5. Verdict         - FAITHFUL / MARGINAL / UNFAITHFUL on configurable
                       thresholds; any phantom crossing appends _PHANTOM and
                       caps the verdict at MARGINAL_PHANTOM (a crossing fit can
                       never be FAITHFUL).

Naming: every CPL-derived key is prefixed cpl_*. The physics guard's
phantom_crossing_ok certifies the FIELD; the cpl_* phantom audit exposes the
field's CPL SHADOW. Same physical criterion, applied to the approximation
instead of the route.

No TFA component consumes the fitted (w0, wa); they appear in outputs only with
this error report attached.

Gating: NON-GATED by design (reads trajectory.csv + summary + frozen settings,
all present for every completed engine run, including EXCLUDED routes).

Entry point: run_cpl_fidelity_validator(run_folder) -> (Code, Desc)
Non-fatal in hub.

Identity: tfa_cpl_fidelity_validator 0.1.0 build 0001.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


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


TFA_PROJECT_RELEASE = "0.0.5"
SCRIPT_NAME = "tfa_cpl_fidelity_validator"
SCRIPT_VERSION = "0.1.0"
SCRIPT_BUILD = "0001"
SCRIPT_API_VERSION = "0.1"
SETTINGS_SCHEMA_VERSION = "0.1"

SUMMARY_FILENAME = "run_results_summary.json"
FROZEN_SETTINGS_FILENAME = "environment-settings.json"
TRAJECTORY_FILENAME = "trajectory.csv"
RESULTS_CSV_FILENAME = "cpl_fidelity_results.csv"
FIDELITY_PLOT_STEM = "cpl_fidelity"

# Defaults applied when the settings block is absent (back-compat).
DEFAULT_FIT_Z_MAX = 3.0
DEFAULT_DW_FAITHFUL = 0.01
DEFAULT_DW_MARGINAL = 0.05
DEFAULT_DDM_FAITHFUL_PCT = 0.1
DEFAULT_DDM_MARGINAL_PCT = 0.5

_FIT_SAMPLES = 400          # uniform-in-a resampling for the least squares
_GRID_SAMPLES = 2000        # dense u = ln(1+z) grid for error scans / D_M


def script_identity() -> Mapping[str, str]:
    return {
        "tfa_project_release": TFA_PROJECT_RELEASE,
        "script_name": SCRIPT_NAME,
        "script_version": SCRIPT_VERSION,
        "script_build": SCRIPT_BUILD,
        "script_api_version": SCRIPT_API_VERSION,
        "settings_schema_version": SETTINGS_SCHEMA_VERSION,
    }


# ---------------------------------------------------------------------------
# I/O helpers (B001 Part 2: BOM-tolerant JSON reads)
# ---------------------------------------------------------------------------

def _read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def _read_trajectory(path: Path) -> dict[str, np.ndarray]:
    """Read trajectory.csv into named float arrays, sorted ascending in z."""
    cols: dict[str, list[float]] = {}
    with path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        headers = [h.strip() for h in next(reader)]
        for h in headers:
            cols[h] = []
        for row in reader:
            if row:
                for h, v in zip(headers, row):
                    cols[h].append(float(v))
    arrays = {h: np.asarray(v, dtype=float) for h, v in cols.items()}
    order = np.argsort(arrays["z"])
    return {h: a[order] for h, a in arrays.items()}


def _record_skip(summary_path: Path, reason: str) -> None:
    try:
        summary = _read_json(summary_path)
        summary.setdefault("results", {})["cpl_fidelity_validator"] = {
            "status": "skipped",
            "reason": reason,
            "script": script_identity(),
        }
        core.atomic_write_json(summary_path, summary)
    except Exception:
        pass


def _validator_config(settings: Mapping[str, Any]) -> dict[str, Any]:
    section = settings.get("user_adjustable", {}).get("cpl_fidelity_validator", {})
    if not isinstance(section, Mapping):
        section = {}
    return {
        "enabled": bool(section.get("enabled", True)),
        "fit_z_max": float(section.get("fit_z_max", DEFAULT_FIT_Z_MAX)),
        "dw_faithful": float(section.get("dw_faithful", DEFAULT_DW_FAITHFUL)),
        "dw_marginal": float(section.get("dw_marginal", DEFAULT_DW_MARGINAL)),
        "ddm_faithful_pct": float(section.get("ddm_faithful_pct", DEFAULT_DDM_FAITHFUL_PCT)),
        "ddm_marginal_pct": float(section.get("ddm_marginal_pct", DEFAULT_DDM_MARGINAL_PCT)),
    }


# ---------------------------------------------------------------------------
# CPL math (closed-form where possible)
# ---------------------------------------------------------------------------

def _fit_cpl(traj: dict[str, np.ndarray], fit_z_max: float) -> tuple[float, float]:
    """Unweighted least-squares CPL fit of the route's exact w over the range.

    w(a) = w0 + wa (1 - a), resampled uniformly in a (uniform-in-a sampling
    avoids the e-fold grid density bias of the raw trajectory grid).
    """
    z = traj["z"]
    w = traj["w_phi"]
    a_lo = 1.0 / (1.0 + fit_z_max)
    a_grid = np.linspace(a_lo, 1.0, _FIT_SAMPLES)
    z_grid = 1.0 / a_grid - 1.0
    w_grid = np.interp(z_grid, z, w)
    basis = np.column_stack([np.ones_like(a_grid), 1.0 - a_grid])
    coef, *_ = np.linalg.lstsq(basis, w_grid, rcond=None)
    return float(coef[0]), float(coef[1])


def _w_cpl(z: np.ndarray, w0: float, wa: float) -> np.ndarray:
    # 1 - a = z / (1 + z)
    z = np.asarray(z, dtype=float)
    return w0 + wa * z / (1.0 + z)


def _f_de_cpl(z: np.ndarray, w0: float, wa: float) -> np.ndarray:
    """CPL-implied rho_DE(z)/rho_DE(0) = a^(-3(1+w0+wa)) * exp(-3 wa (1-a))."""
    a = 1.0 / (1.0 + np.asarray(z, dtype=float))
    return a ** (-3.0 * (1.0 + w0 + wa)) * np.exp(-3.0 * wa * (1.0 - a))


def _cpl_z_cross(w0: float, wa: float) -> float | None:
    """Redshift where w_CPL = -1 (phantom crossing), or None.

    w0 + wa(1-a) = -1  =>  a_c = 1 + (1+w0)/wa ; valid crossing iff 0 < a_c < 1.
    """
    if wa == 0.0:
        return None
    a_c = 1.0 + (1.0 + w0) / wa
    if 0.0 < a_c < 1.0:
        return 1.0 / a_c - 1.0
    return None


def _route_f_de(traj: dict[str, np.ndarray]) -> np.ndarray:
    """Exact f_DE(z) = Omega_phi(z) E_X(z)^2 / Omega_phi(0) (E_X(0) = 1)."""
    rho_rel = traj["Omega_phi"] * traj["E_X"] ** 2
    return rho_rel / rho_rel[0]


def _dm_to_zstar_pct_error(
    traj: dict[str, np.ndarray],
    z_star: float,
    w0: float,
    wa: float,
    Om_eff: float,
    Or_eff: float,
    Ode_eff: float,
) -> float:
    """Percent error in D_M(z*) under the CPL stand-in vs the exact route.

    The CPL stand-in shares the route's OWN present-day fractions
    (Om_eff, Or_eff, Ode_eff sum to 1, taken from the normalized route at
    z = 0), so the only difference between E_CPL and E_X is the dark-energy
    evolution law (CPL vs exact field) - true CPL infidelity, not a budget
    mismatch.

    Both integrals I = int_0^z* dz / E are evaluated on the same dense
    u = ln(1+z) grid (dz = e^u du). The route's 1/E comes from interpolating
    ln E_X vs u on the trajectory (E spans orders of magnitude, so log-space
    interpolation is accurate). H0 cancels in the ratio, so the percent error
    is normalization-free.
    """
    u_traj = np.log1p(traj["z"])
    lnE_traj = np.log(traj["E_X"])
    u_grid = np.linspace(0.0, np.log1p(z_star), _GRID_SAMPLES)
    z_grid = np.expm1(u_grid)

    lnE_route = np.interp(u_grid, u_traj, lnE_traj)
    inv_E_route = np.exp(-lnE_route)

    E2_cpl = (
        Om_eff * (1.0 + z_grid) ** 3
        + Or_eff * (1.0 + z_grid) ** 4
        + Ode_eff * _f_de_cpl(z_grid, w0, wa)
    )
    inv_E_cpl = 1.0 / np.sqrt(E2_cpl)

    dzdu = np.exp(u_grid)
    I_route = float(np.trapezoid(inv_E_route * dzdu, u_grid))
    I_cpl = float(np.trapezoid(inv_E_cpl * dzdu, u_grid))
    return 100.0 * (I_cpl / I_route - 1.0)


def _verdict(
    dw_max: float,
    ddm_pct: float,
    phantom: bool,
    cfg: Mapping[str, Any],
) -> str:
    if dw_max <= cfg["dw_faithful"] and abs(ddm_pct) <= cfg["ddm_faithful_pct"]:
        base = "FAITHFUL"
    elif dw_max <= cfg["dw_marginal"] and abs(ddm_pct) <= cfg["ddm_marginal_pct"]:
        base = "MARGINAL"
    else:
        base = "UNFAITHFUL"
    if phantom:
        # A phantom-crossing fit can never be FAITHFUL.
        if base == "FAITHFUL":
            base = "MARGINAL"
        return base + "_PHANTOM"
    return base


# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------

def _write_results_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = ["indicator", "value", "status", "note"]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({
                k: (f"{v:.10g}" if isinstance(v, float) else ("" if v is None else v))
                for k, v in row.items()
            })


def _save_fidelity_plot(
    traj: dict[str, np.ndarray],
    w0: float,
    wa: float,
    cfg: Mapping[str, Any],
    benchmark_id: str,
    verdict: str,
    z_cross: float | None,
    desi_z_cross: float | None,
    dw_max: float,
    dw_max_z: float,
    ddm_pct: float,
    outdir: Path,
) -> None:
    z_max = cfg["fit_z_max"]
    z_grid = np.linspace(0.0, z_max, 600)
    w_route = np.interp(z_grid, traj["z"], traj["w_phi"])
    w_fit = _w_cpl(z_grid, w0, wa)

    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(9, 7), sharex=True,
        gridspec_kw={"height_ratios": [2.2, 1.0], "hspace": 0.08},
    )

    ax1.plot(z_grid, w_route, color="#1f77b4", lw=2.2,
             label=r"$w_\phi(z)$ — exact route (canonical, $w \geq -1$ always)")
    ax1.plot(z_grid, w_fit, color="#d62728", lw=1.8, ls="--",
             label=rf"best-fit CPL  ($w_0={w0:.3f}$, $w_a={wa:.3f}$) — audited, not adopted")
    ax1.axhline(-1.0, color="#333", lw=1.2)
    ax1.text(0.995, -1.0, r"$w = -1$", fontsize=8, color="#333",
             ha="right", va="bottom", transform=ax1.get_yaxis_transform())

    # Shade where the CPL fit is phantom (w_CPL < -1).
    phantom_mask = w_fit < -1.0
    if np.any(phantom_mask):
        ax1.fill_between(z_grid, w_fit, -1.0, where=phantom_mask,
                         color="#d62728", alpha=0.18,
                         label="CPL phantom excursion ($w_{CPL} < -1$)")
    if z_cross is not None and z_cross <= z_max:
        ax1.axvline(z_cross, color="#d62728", lw=1.0, ls=":")
        ax1.annotate(
            f"CPL enters phantom\nat $z \\approx {z_cross:.2f}$",
            xy=(z_cross, -1.0), xytext=(z_cross + 0.08 * z_max, -1.0 + 0.04),
            fontsize=8, color="#d62728",
            arrowprops=dict(arrowstyle="->", color="#d62728", lw=0.8),
        )
    if desi_z_cross is not None and desi_z_cross <= z_max:
        ax1.plot([desi_z_cross], [-1.0], marker="v", ms=7, color="#9467bd",
                 label=f"DESI ref. posterior crossing ($z \\approx {desi_z_cross:.2f}$)")

    ax1.set_ylabel(r"$w(z)$")
    ax1.set_title(
        f"{benchmark_id}    CPL fidelity audit:  {verdict}\n"
        f"$\\Delta w_{{max}} = {dw_max:.4f}$ at $z = {dw_max_z:.2f}$;   "
        f"$\\Delta D_M(z_*) = {ddm_pct:+.3f}\\%$",
        fontsize=10,
    )
    ax1.legend(fontsize=8, loc="lower left")
    ax1.grid(True, lw=0.4, alpha=0.4)

    ax2.plot(z_grid, w_fit - w_route, color="#555", lw=1.6)
    ax2.axhline(0.0, color="#333", lw=0.8)
    ax2.set_xlabel(r"$z$")
    ax2.set_ylabel(r"$w_{CPL} - w_\phi$")
    ax2.grid(True, lw=0.4, alpha=0.4)

    ax1.set_xlim(0.0, z_max)
    for ext in ("png", "pdf"):
        fig.savefig(str(outdir / f"{FIDELITY_PLOT_STEM}.{ext}"), dpi=150, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------
# File-based entry point
# ---------------------------------------------------------------------------

def run_cpl_fidelity_validator(run_folder: str | Path) -> tuple[str, str]:
    """File-based CPL-audit entry point. Returns (Code, Desc).

    NON-GATED: runs for every completed engine run, including EXCLUDED routes.
    Non-fatal: exceptions are caught and reported as ("Error", ...).
    """
    try:
        run_folder = Path(run_folder)
        summary_path = run_folder / SUMMARY_FILENAME
        settings_path = run_folder / FROZEN_SETTINGS_FILENAME
        traj_path = run_folder / TRAJECTORY_FILENAME

        if not summary_path.exists():
            return ("Error", f"{SUMMARY_FILENAME} not found in {run_folder}")
        if not settings_path.exists():
            return ("Error", f"{FROZEN_SETTINGS_FILENAME} not found in {run_folder}")

        settings = _read_json(settings_path)
        cfg = _validator_config(settings)
        if not cfg["enabled"]:
            _record_skip(summary_path, "cpl_fidelity_validator disabled in settings")
            return ("OK", "cpl_fidelity_validator disabled")

        summary = _read_json(summary_path)
        av = summary.get("results", {}).get("acoustic_validator")
        if not isinstance(av, Mapping) or av.get("H0_X_kms") is None:
            return ("Error", "acoustic_validator results not found in summary (engine must run first)")
        if not traj_path.exists():
            return ("Error", f"{TRAJECTORY_FILENAME} not found in {run_folder}")

        benchmark_id = str(summary.get("contract", {}).get("benchmark_id", "unnamed"))
        z_star = float(av.get("acoustic_anchor", {}).get("z_star", 1091.9))
        H0_X = float(av["H0_X_kms"])

        traj = _read_trajectory(traj_path)

        # The CPL stand-in shares the route's OWN present-day budget, so the
        # D_M comparison isolates the DE evolution law (the only thing CPL
        # changes). Or_eff scales the reference radiation fraction to the
        # route's H0_X; Om_eff closes flatness.
        cosmo = settings.get("user_adjustable", {}).get("cosmology", {})
        H0_ref = float(cosmo.get("H0_ref_kms", 67.36))
        Or_eff = float(cosmo.get("Omega_r0", 9.18e-5)) * (H0_ref / H0_X) ** 2
        Ode_eff = float(traj["Omega_phi"][0])
        Om_eff = 1.0 - Ode_eff - Or_eff

        # --- 1. Best-fit CPL ---------------------------------------------------
        w0_fit, wa_fit = _fit_cpl(traj, cfg["fit_z_max"])

        # --- 2. Infidelity report ----------------------------------------------
        z_scan = np.linspace(0.0, cfg["fit_z_max"], _GRID_SAMPLES)
        w_route_scan = np.interp(z_scan, traj["z"], traj["w_phi"])
        w_cpl_scan = _w_cpl(z_scan, w0_fit, wa_fit)
        dw_scan = np.abs(w_cpl_scan - w_route_scan)
        i_dw = int(np.argmax(dw_scan))
        dw_max = float(dw_scan[i_dw])
        dw_max_z = float(z_scan[i_dw])
        dw_at_zfit_max = float(dw_scan[-1])

        f_de_route_traj = _route_f_de(traj)
        f_de_route_scan = np.interp(z_scan, traj["z"], f_de_route_traj)
        f_de_cpl_scan = _f_de_cpl(z_scan, w0_fit, wa_fit)
        df_scan = np.abs(f_de_cpl_scan / f_de_route_scan - 1.0)
        i_df = int(np.argmax(df_scan))
        df_de_max = float(df_scan[i_df])
        df_de_max_z = float(z_scan[i_df])

        ddm_star_pct = _dm_to_zstar_pct_error(
            traj, z_star, w0_fit, wa_fit, Om_eff, Or_eff, Ode_eff
        )

        # --- 3. Phantom audit (closed-form) -------------------------------------
        w_asymptote = w0_fit + wa_fit
        z_cross = _cpl_z_cross(w0_fit, wa_fit)
        w_cpl_min = float(np.min(w_cpl_scan))
        w_cpl_min_z = float(z_scan[int(np.argmin(w_cpl_scan))])
        phantom_fraction = float(np.mean(w_cpl_scan < -1.0))
        phantom_flag = bool(z_cross is not None or w_cpl_min < -1.0 or w_asymptote < -1.0)

        # DESI reference posterior's own crossing (context, computed not hardcoded).
        desi = settings.get("user_adjustable", {}).get("desi_reference", {})
        desi_z_cross = None
        if isinstance(desi, Mapping) and desi.get("w0") is not None and desi.get("wa") is not None:
            desi_z_cross = _cpl_z_cross(float(desi["w0"]), float(desi["wa"]))

        # --- 4. Verdict ----------------------------------------------------------
        verdict = _verdict(dw_max, ddm_star_pct, phantom_flag, cfg)

        # --- 5. cpl_fidelity_results.csv -----------------------------------------
        z_cross_note = (
            f"w_CPL = -1 at a_c = 1 + (1+w0)/wa; the canonical route never crosses (guard-certified)"
        )
        rows: list[dict[str, Any]] = [
            {"indicator": "cpl_w0_fit", "value": w0_fit, "status": "audited",
             "note": f"unweighted lsq of exact w(a) over 0<=z<={cfg['fit_z_max']:g}, uniform-in-a; NOT a route representation"},
            {"indicator": "cpl_wa_fit", "value": wa_fit, "status": "audited",
             "note": "see cpl_w0_fit; consume only with this error report attached"},
            {"indicator": "cpl_dw_max", "value": dw_max, "status": "infidelity",
             "note": f"max |w_CPL - w_phi| at z={dw_max_z:.4g}"},
            {"indicator": "cpl_dw_at_fit_edge", "value": dw_at_zfit_max, "status": "infidelity",
             "note": f"|w_CPL - w_phi| at z={cfg['fit_z_max']:g} (high-z growth)"},
            {"indicator": "cpl_df_de_max", "value": df_de_max, "status": "infidelity",
             "note": f"max relative rho_DE error at z={df_de_max_z:.4g}"},
            {"indicator": "cpl_dDM_star_pct", "value": ddm_star_pct, "status": "infidelity",
             "note": f"percent error in D_M(z*={z_star:.1f}) under the CPL stand-in; the acoustic-distance error a CPL-fed pipeline inherits"},
            {"indicator": "cpl_w_asymptote", "value": w_asymptote, "status": "phantom_audit",
             "note": "w0+wa = w_CPL limit as a->0; < -1 means phantom-in-the-past guaranteed"},
            {"indicator": "cpl_z_cross", "value": z_cross, "status": "phantom_audit",
             "note": z_cross_note},
            {"indicator": "cpl_w_min", "value": w_cpl_min, "status": "phantom_audit",
             "note": f"min w_CPL over fit range, at z={w_cpl_min_z:.4g}"},
            {"indicator": "cpl_phantom_fraction", "value": phantom_fraction, "status": "phantom_audit",
             "note": f"fraction of 0<=z<={cfg['fit_z_max']:g} with w_CPL < -1"},
            {"indicator": "cpl_phantom_flag", "value": phantom_flag, "status": "phantom_audit",
             "note": "True: feeding this (w0, wa) to any pipeline silently violates the canonical sector"},
            {"indicator": "desi_reference_z_cross", "value": desi_z_cross, "status": "context",
             "note": "the DESI reference posterior's own phantom crossing (computed from settings desi_reference)"},
            {"indicator": "cpl_verdict", "value": verdict, "status": "verdict",
             "note": f"thresholds: dw {cfg['dw_faithful']:g}/{cfg['dw_marginal']:g}, dDM% {cfg['ddm_faithful_pct']:g}/{cfg['ddm_marginal_pct']:g}; phantom caps at MARGINAL_PHANTOM"},
        ]
        _write_results_csv(run_folder / RESULTS_CSV_FILENAME, rows)

        # --- 6. Plot ---------------------------------------------------------------
        _save_fidelity_plot(
            traj, w0_fit, wa_fit, cfg, benchmark_id, verdict,
            z_cross, desi_z_cross, dw_max, dw_max_z, ddm_star_pct, run_folder,
        )

        # --- 7. Enrich summary ------------------------------------------------------
        summary = _read_json(summary_path)
        summary.setdefault("results", {})["cpl_fidelity_validator"] = {
            "status": "OK",
            "script": script_identity(),
            "gate_independent": True,
            "purpose": "CPL audited, never adopted; no TFA component consumes the fitted (w0, wa)",
            "fit": {
                "cpl_w0_fit": w0_fit,
                "cpl_wa_fit": wa_fit,
                "fit_z_max": cfg["fit_z_max"],
                "method": "unweighted_lsq_uniform_in_a",
            },
            "infidelity": {
                "cpl_dw_max": dw_max,
                "cpl_dw_max_z": dw_max_z,
                "cpl_dw_at_fit_edge": dw_at_zfit_max,
                "cpl_df_de_max": df_de_max,
                "cpl_df_de_max_z": df_de_max_z,
                "cpl_dDM_star_pct": ddm_star_pct,
                "z_star": z_star,
            },
            "phantom_audit": {
                "cpl_phantom_flag": phantom_flag,
                "cpl_z_cross": z_cross,
                "cpl_w_min": w_cpl_min,
                "cpl_w_min_z": w_cpl_min_z,
                "cpl_phantom_fraction": phantom_fraction,
                "cpl_w_asymptote": w_asymptote,
                "desi_reference_z_cross": desi_z_cross,
                "note": "the physics guard certifies the FIELD never crosses; this audits the field's CPL shadow",
            },
            "cpl_verdict": verdict,
            "thresholds": {
                "dw_faithful": cfg["dw_faithful"],
                "dw_marginal": cfg["dw_marginal"],
                "ddm_faithful_pct": cfg["ddm_faithful_pct"],
                "ddm_marginal_pct": cfg["ddm_marginal_pct"],
            },
            "cpl_fidelity_results_csv": RESULTS_CSV_FILENAME,
            "cpl_fidelity_plot": f"{FIDELITY_PLOT_STEM}.png",
        }
        core.atomic_write_json(summary_path, summary)

        z_cross_txt = f"{z_cross:.3f}" if z_cross is not None else "none"
        desc = (
            f"cpl_fidelity complete: verdict={verdict} "
            f"dw_max={dw_max:.4f}@z={dw_max_z:.2f} z_cross={z_cross_txt} "
            f"dDM*={ddm_star_pct:+.3f}%"
        )
        return ("OK", desc)

    except Exception as exc:
        return ("Error", f"{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    _run_folder = sys.argv[1] if len(sys.argv) > 1 else "."
    _code, _desc = run_cpl_fidelity_validator(_run_folder)
    print(json.dumps({"code": _code, "desc": _desc}))
    sys.exit(0 if _code == "OK" else 1)
