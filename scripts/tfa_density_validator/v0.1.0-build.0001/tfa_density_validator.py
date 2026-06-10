"""
tfa_density_validator.py - dark-energy density-sector validator for TFA run folders.

Strictly CPL-free. This specialist never reduces the route to any (w0, wa)
parametrization; every indicator is computed from the route's exact integrated
trajectory or echoed from the engine's summary.

Purpose:
  1. Score the route's required H0 against the external DESI reference
     (the ONLY pull this specialist computes).
  2. Describe the route's exact energy budget (echoed from the engine's
     energy_fractions block, plus a closure recheck from trajectory.csv).
  3. Report f_DE(z) = rho_phi(z) / rho_phi(0) distance-from-Lambda markers
     (LCDM baseline is f_DE = 1).
  4. Report thawing-strength route properties: 1 + w(0), the thaw redshift
     z_thaw, and the tangent slope -dw/da at a = 1 (a property of the exact
     route, the same convention the WQI source paper quotes - NOT a fit).

Deliberate exclusions (documented, not omissions):
  - NO Omega_m pull. The route, Planck, and DESI all share
    omega_m ~ 0.142-0.143, so an Omega_m pull would double-count the H0 pull.
    DESI's Omega_m is quoted reference-only.
  - NO CPL anywhere. The CPL fidelity audit lives in the separate
    tfa_cpl_fidelity_validator specialist.

Distinct from existing outputs (consistency contract):
  - delta_X in the summary is H0_X/H0_ref - 1 (vs the reference cosmology
    67.36); the H0 pull here is vs the DESI measurement 66.74 +/- 0.56.
    Different references, both labeled.
  - The engine's energy_fractions block is echoed, never recomputed by a new
    convention; no third Omega_m number is introduced.
  - bands_consistent cross-checks that the settings h0_bands still equal the
    desi_reference mean +/- 1/2/3 sigma, so the pull class can never silently
    contradict the engine's band verdict.

Gating: NON-GATED by design. Inputs (trajectory.csv, summary, frozen settings)
exist for every completed engine run, including EXCLUDED routes - where the H0
pull is most informative (it quantifies HOW excluded).

Entry point: run_density_validator(run_folder) -> (Code, Desc)
Non-fatal in hub: failure is recorded but does not affect the physics verdict.

Identity: tfa_density_validator 0.1.0 build 0001.
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
SCRIPT_NAME = "tfa_density_validator"
SCRIPT_VERSION = "0.1.0"
SCRIPT_BUILD = "0001"
SCRIPT_API_VERSION = "0.1"
SETTINGS_SCHEMA_VERSION = "0.1"

SUMMARY_FILENAME = "run_results_summary.json"
FROZEN_SETTINGS_FILENAME = "environment-settings.json"
TRAJECTORY_FILENAME = "trajectory.csv"
RESULTS_CSV_FILENAME = "density_results.csv"
FDE_PLOT_STEM = "density_fde"

# Defaults applied when the settings block is absent (back-compat with frozen
# settings older than file version 1.2.0).
DEFAULT_FDE_Z_MAX = 3.0
DEFAULT_FDE_MARKER_Z = (0.5, 1.0, 2.0)
DEFAULT_THAW_THRESHOLD = 0.01
BANDS_CONSISTENCY_TOL = 1e-6


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
    # utf-8-sig strips a UTF-8 BOM if present; reads normally when absent.
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


def _sigma_class(pull: float) -> str:
    ap = abs(pull)
    if ap <= 1.0:
        return "PASS_1SIGMA"
    if ap <= 2.0:
        return "PASS_2SIGMA"
    if ap <= 3.0:
        return "PASS_3SIGMA"
    return "OUTSIDE_3SIGMA"


def _record_skip(summary_path: Path, reason: str) -> None:
    try:
        summary = _read_json(summary_path)
        summary.setdefault("results", {})["density_validator"] = {
            "status": "skipped",
            "reason": reason,
            "script": script_identity(),
        }
        core.atomic_write_json(summary_path, summary)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Settings blocks (with back-compat defaults)
# ---------------------------------------------------------------------------

def _validator_config(settings: Mapping[str, Any]) -> dict[str, Any]:
    section = settings.get("user_adjustable", {}).get("density_validator", {})
    if not isinstance(section, Mapping):
        section = {}
    marker_z = section.get("fde_marker_z", list(DEFAULT_FDE_MARKER_Z))
    return {
        "enabled": bool(section.get("enabled", True)),
        "fde_z_max": float(section.get("fde_z_max", DEFAULT_FDE_Z_MAX)),
        "fde_marker_z": [float(z) for z in marker_z],
        "thaw_threshold": float(section.get("thaw_threshold", DEFAULT_THAW_THRESHOLD)),
    }


def _desi_reference(settings: Mapping[str, Any]) -> Mapping[str, Any] | None:
    section = settings.get("user_adjustable", {}).get("desi_reference")
    if not isinstance(section, Mapping):
        return None
    required = ("H0_kms", "H0_sigma", "Omega_m", "Omega_m_sigma")
    if any(section.get(k) is None for k in required):
        return None
    return section


def _check_bands_consistency(
    settings: Mapping[str, Any], desi: Mapping[str, Any]
) -> tuple[bool, str]:
    """Verify h0_bands == desi_reference mean +/- 1/2/3 sigma.

    The engine's band verdict and this specialist's pull class are coherent by
    construction only while these two settings blocks agree.
    """
    user = settings.get("user_adjustable", {})
    bands = user.get("h0_bands") or user.get("planck_h0_bands")
    if not isinstance(bands, Mapping):
        return False, "h0_bands block not found in settings"
    mean = float(desi["H0_kms"])
    sigma = float(desi["H0_sigma"])
    expected = {
        "strict": (mean - sigma, mean + sigma),
        "loose_2s": (mean - 2.0 * sigma, mean + 2.0 * sigma),
        "loose_3s": (mean - 3.0 * sigma, mean + 3.0 * sigma),
    }
    for key, (lo, hi) in expected.items():
        pair = bands.get(key)
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            return False, f"h0_bands.{key} missing or malformed"
        if abs(float(pair[0]) - lo) > BANDS_CONSISTENCY_TOL or abs(float(pair[1]) - hi) > BANDS_CONSISTENCY_TOL:
            return False, (
                f"h0_bands.{key} = [{float(pair[0]):.6g}, {float(pair[1]):.6g}] "
                f"does not equal desi_reference mean +/- sigma "
                f"[{lo:.6g}, {hi:.6g}]; band verdict and H0 pull class may disagree"
            )
    return True, "h0_bands equal desi_reference mean +/- 1/2/3 sigma"


# ---------------------------------------------------------------------------
# Indicators
# ---------------------------------------------------------------------------

def _compute_f_de(traj: dict[str, np.ndarray]) -> np.ndarray:
    """f_DE(z) = rho_phi(z)/rho_phi(0) = Omega_phi(z) E_X(z)^2 / Omega_phi(0).

    E_X(0) = 1 by the engine's normalization contract, so the denominator is
    Omega_phi at the z = 0 row. Exact - no parametrization.
    """
    omega_phi = traj["Omega_phi"]
    e_x = traj["E_X"]
    rho_rel = omega_phi * e_x**2
    return rho_rel / rho_rel[0]


def _interp_at(z_arr: np.ndarray, y_arr: np.ndarray, z0: float) -> float:
    return float(np.interp(z0, z_arr, y_arr))


def _thaw_redshift(z: np.ndarray, w_phi: np.ndarray, threshold: float) -> float | None:
    """Largest z at which 1 + w first exceeds the threshold (thawing onset).

    The field is frozen (w = -1) at high z; scanning from high z downward, the
    first crossing of 1 + w = threshold marks where the route leaves Lambda.
    Linear interpolation between the bracketing samples.
    """
    dep = 1.0 + w_phi
    above = dep >= threshold
    if not np.any(above):
        return None
    idx = int(np.max(np.nonzero(above)[0]))
    if idx == len(z) - 1:
        return float(z[idx])
    z1, z2 = z[idx], z[idx + 1]
    d1, d2 = dep[idx], dep[idx + 1]
    if d1 == d2:
        return float(z1)
    t = (threshold - d1) / (d2 - d1)
    return float(z1 + t * (z2 - z1))


def _tangent_wa(traj: dict[str, np.ndarray]) -> float:
    """-dw/da at a = 1, by local linear fit of w(a) for z <= 0.05.

    A derivative of the exact route's w - a route property (the convention the
    WQI source paper quotes), not a CPL fit.
    """
    z = traj["z"]
    a = traj["a"]
    w = traj["w_phi"]
    mask = z <= 0.05
    if int(np.sum(mask)) < 3:
        mask = np.zeros_like(z, dtype=bool)
        mask[: max(3, int(np.sum(z <= 0.05)))] = True
    slope = np.polyfit(a[mask], w[mask], 1)[0]
    return float(-slope)


# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------

def _write_results_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = ["indicator", "value", "reference", "reference_sigma", "pull", "status", "note"]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({
                k: (f"{v:.10g}" if isinstance(v, float) else ("" if v is None else v))
                for k, v in row.items()
            })


def _save_fde_plot(
    traj: dict[str, np.ndarray],
    f_de: np.ndarray,
    cfg: dict[str, Any],
    benchmark_id: str,
    H0_X: float,
    band: str,
    h0_pull: float,
    budget: Mapping[str, Any],
    outdir: Path,
) -> None:
    z = traj["z"]
    z_max = cfg["fde_z_max"]
    mask = z <= z_max

    fig, ax = plt.subplots(figsize=(9, 5.5))
    ax.plot(z[mask], f_de[mask], color="#1f77b4", lw=2.2,
            label=r"$f_{DE}(z) = \rho_\phi(z)/\rho_\phi(0)$  (exact route)")
    ax.axhline(1.0, color="#999", lw=1.5, ls="--",
               label=r"$f_{DE} \equiv 1$  ($\Lambda$CDM)")
    for zm in cfg["fde_marker_z"]:
        if zm <= z_max:
            ax.plot([zm], [_interp_at(z, f_de, zm)], "o", ms=5, color="#d62728")

    ax.text(
        0.03, 0.97,
        f"$H_{{0,X}} = {H0_X:.4f}$  [{band}]\n"
        f"$H_0$ pull vs DESI $= {h0_pull:+.2f}\\sigma$\n"
        f"$\\Omega_\\phi(0) = {float(budget.get('Omega_phi_0', float('nan'))):.5f}$\n"
        f"$\\Omega_m(0) = {float(budget.get('Omega_m_0', float('nan'))):.5f}$",
        transform=ax.transAxes, ha="left", va="top", fontsize=8.5,
        bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="#ccc", alpha=0.92),
    )

    ax.set_xlim(0.0, z_max)
    ax.set_xlabel(r"$z$")
    ax.set_ylabel(r"$f_{DE}(z)$")
    ax.set_title(
        f"{benchmark_id}    dark-energy density evolution (CPL-free)\n"
        r"$f_{DE}(z) = \Omega_\phi(z) E_X(z)^2 / \Omega_\phi(0)$",
        fontsize=10,
    )
    ax.legend(fontsize=8, loc="lower right")
    ax.grid(True, lw=0.4, alpha=0.4)
    fig.tight_layout()
    for ext in ("png", "pdf"):
        fig.savefig(str(outdir / f"{FDE_PLOT_STEM}.{ext}"), dpi=150, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------
# File-based entry point
# ---------------------------------------------------------------------------

def run_density_validator(run_folder: str | Path) -> tuple[str, str]:
    """File-based density-sector entry point. Returns (Code, Desc).

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
            _record_skip(summary_path, "density_validator disabled in settings")
            return ("OK", "density_validator disabled")

        desi = _desi_reference(settings)
        if desi is None:
            _record_skip(summary_path, "desi_reference block not found in settings (requires settings file >= 1.2.0)")
            return ("OK", "density_validator skipped: desi_reference block not found in settings")

        summary = _read_json(summary_path)
        av = summary.get("results", {}).get("acoustic_validator")
        if not isinstance(av, Mapping) or av.get("H0_X_kms") is None:
            return ("Error", "acoustic_validator results not found in summary (engine must run first)")
        if not traj_path.exists():
            return ("Error", f"{TRAJECTORY_FILENAME} not found in {run_folder}")

        benchmark_id = str(summary.get("contract", {}).get("benchmark_id", "unnamed"))
        H0_X = float(av["H0_X_kms"])
        band = str(av.get("band", ""))
        delta_X = av.get("delta_X")
        budget = av.get("energy_fractions")
        if not isinstance(budget, Mapping):
            return ("Error", "energy_fractions block not found in acoustic_validator results (requires acoustic validator >= 0.1.6)")

        # --- 1. H0 pull (the ONLY pull) + bands consistency ------------------
        desi_H0 = float(desi["H0_kms"])
        desi_H0_sigma = float(desi["H0_sigma"])
        h0_pull = (H0_X - desi_H0) / desi_H0_sigma
        h0_class = _sigma_class(h0_pull)
        bands_consistent, bands_note = _check_bands_consistency(settings, desi)

        # --- 2. Energy budget echo + closure recheck from trajectory ---------
        traj = _read_trajectory(traj_path)
        cosmo = settings.get("user_adjustable", {}).get("cosmology", {})
        H0_ref = float(cosmo.get("H0_ref_kms", 67.36))
        Omega_r0_ref = float(cosmo.get("Omega_r0", 9.18e-5))
        Omega_phi_0_traj = float(traj["Omega_phi"][0])
        Or_route0 = Omega_r0_ref * (H0_ref / H0_X) ** 2
        Omega_m_0_echo = float(budget["Omega_m_0"])
        closure_residual = abs(Omega_phi_0_traj + Omega_m_0_echo + Or_route0 - 1.0)
        echo_residual = abs(Omega_phi_0_traj - float(budget["Omega_phi_0"]))

        # --- 3. f_DE(z) markers ----------------------------------------------
        z = traj["z"]
        f_de = _compute_f_de(traj)
        fde_mask = z <= cfg["fde_z_max"]
        dev = np.abs(f_de[fde_mask] - 1.0)
        i_max = int(np.argmax(dev))
        fde_max_dev = float(dev[i_max])
        fde_max_dev_z = float(z[fde_mask][i_max])
        fde_markers = {
            f"f_de_at_z{zm:g}": _interp_at(z, f_de, zm)
            for zm in cfg["fde_marker_z"]
            if zm <= float(np.max(z))
        }

        # --- 4. Thawing-strength route properties -----------------------------
        w0_route = float(traj["w_phi"][0])
        one_plus_w0 = 1.0 + w0_route
        z_thaw = _thaw_redshift(z, traj["w_phi"], cfg["thaw_threshold"])
        wa_tangent = _tangent_wa(traj)

        # --- 5. density_results.csv ------------------------------------------
        rows: list[dict[str, Any]] = [
            {"indicator": "H0_X_kms", "value": H0_X, "reference": desi_H0,
             "reference_sigma": desi_H0_sigma, "pull": h0_pull, "status": h0_class,
             "note": f"vs {desi.get('_source', 'DESI reference')}; engine band={band}"},
            {"indicator": "delta_X", "value": float(delta_X) if delta_X is not None else None,
             "reference": None, "reference_sigma": None, "pull": None, "status": "audit_echo",
             "note": f"engine audit signature H0_X/H0_ref-1 vs H0_ref={H0_ref:g}; different reference than the DESI pull"},
            {"indicator": "bands_consistent", "value": bands_consistent,
             "reference": None, "reference_sigma": None, "pull": None,
             "status": "PASS" if bands_consistent else "WARN", "note": bands_note},
            {"indicator": "Omega_phi_0", "value": float(budget["Omega_phi_0"]),
             "reference": None, "reference_sigma": None, "pull": None, "status": "descriptive",
             "note": "echoed from acoustic_validator.energy_fractions"},
            {"indicator": "Omega_m_0", "value": Omega_m_0_echo,
             "reference": float(desi["Omega_m"]), "reference_sigma": float(desi["Omega_m_sigma"]),
             "pull": None, "status": "no_pull",
             "note": "DESI Omega_m quoted reference-only; an Omega_m pull would double-count the H0 pull (shared omega_m)"},
            {"indicator": "closure_residual_z0", "value": closure_residual,
             "reference": None, "reference_sigma": None, "pull": None, "status": "descriptive",
             "note": "|Omega_phi + Omega_m + Omega_r - 1| at z=0, recomputed from trajectory.csv"},
            {"indicator": "z_eq_route", "value": budget.get("z_eq_route"),
             "reference": budget.get("z_eq_lcdm"), "reference_sigma": None, "pull": None,
             "status": "descriptive",
             "note": f"echoed; delta_z_eq={budget.get('delta_z_eq')}"},
            {"indicator": "omega_m_residual_pct", "value": budget.get("omega_m_residual_pct"),
             "reference": None, "reference_sigma": None, "pull": None, "status": "audit_echo",
             "note": "echoed from acoustic_validator.energy_fractions (engine self-consistency)"},
            {"indicator": "fde_max_abs_dev", "value": fde_max_dev,
             "reference": 0.0, "reference_sigma": None, "pull": None, "status": "descriptive",
             "note": f"max |f_DE - 1| over 0<=z<={cfg['fde_z_max']:g}, at z={fde_max_dev_z:.4g}; LCDM baseline f_DE=1"},
            {"indicator": "one_plus_w0", "value": one_plus_w0,
             "reference": 0.0, "reference_sigma": None, "pull": None, "status": "descriptive",
             "note": "thawing strength today; 0 means Lambda"},
            {"indicator": "z_thaw", "value": z_thaw,
             "reference": None, "reference_sigma": None, "pull": None, "status": "descriptive",
             "note": f"largest z with 1+w >= {cfg['thaw_threshold']:g} (thawing onset)"},
            {"indicator": "wa_tangent", "value": wa_tangent,
             "reference": None, "reference_sigma": None, "pull": None, "status": "descriptive",
             "note": "-dw/da at a=1, derivative of the exact route w (NOT a CPL fit); WQI source-paper convention"},
        ]
        for key, value in fde_markers.items():
            rows.append({"indicator": key, "value": value, "reference": 1.0,
                         "reference_sigma": None, "pull": None, "status": "descriptive",
                         "note": "LCDM baseline f_DE=1"})
        _write_results_csv(run_folder / RESULTS_CSV_FILENAME, rows)

        # --- 6. Plot -----------------------------------------------------------
        _save_fde_plot(traj, f_de, cfg, benchmark_id, H0_X, band, h0_pull, budget, run_folder)

        # --- 7. Enrich summary --------------------------------------------------
        summary = _read_json(summary_path)
        summary.setdefault("results", {})["density_validator"] = {
            "status": "OK",
            "script": script_identity(),
            "gate_independent": True,
            "desi_reference": {
                "source": str(desi.get("_source", "")),
                "H0_kms": desi_H0,
                "H0_sigma": desi_H0_sigma,
                "Omega_m": float(desi["Omega_m"]),
                "Omega_m_sigma": float(desi["Omega_m_sigma"]),
            },
            "H0_pull": h0_pull,
            "H0_pull_class": h0_class,
            "engine_band": band,
            "bands_consistent": bands_consistent,
            "bands_note": bands_note,
            "energy_budget": {
                "source": "acoustic_validator.energy_fractions",
                "Omega_phi_0": float(budget["Omega_phi_0"]),
                "Omega_m_0": Omega_m_0_echo,
                "z_eq_route": budget.get("z_eq_route"),
                "z_eq_lcdm": budget.get("z_eq_lcdm"),
                "delta_z_eq": budget.get("delta_z_eq"),
                "omega_m_residual_pct": budget.get("omega_m_residual_pct"),
                "closure_residual_z0": closure_residual,
                "echo_residual_Omega_phi_0": echo_residual,
            },
            "f_de": {
                "fde_z_max": cfg["fde_z_max"],
                "max_abs_dev": fde_max_dev,
                "max_abs_dev_z": fde_max_dev_z,
                **fde_markers,
            },
            "thawing": {
                "one_plus_w0": one_plus_w0,
                "z_thaw": z_thaw,
                "thaw_threshold": cfg["thaw_threshold"],
                "wa_tangent": wa_tangent,
                "wa_tangent_note": "route property (-dw/da at a=1), not a CPL fit",
            },
            "omega_m_pull": "not_computed_by_design (double-counts H0 pull)",
            "density_results_csv": RESULTS_CSV_FILENAME,
            "density_fde_plot": f"{FDE_PLOT_STEM}.png",
        }
        core.atomic_write_json(summary_path, summary)

        z_thaw_txt = f"{z_thaw:.3f}" if z_thaw is not None else "none"
        desc = (
            f"density_validator complete: H0_pull={h0_pull:+.2f} ({h0_class}) "
            f"f_DE_max_dev={fde_max_dev:.4f} z_thaw={z_thaw_txt}"
        )
        if not bands_consistent:
            desc += " [WARN: h0_bands inconsistent with desi_reference]"
        return ("OK", desc)

    except Exception as exc:
        return ("Error", f"{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    _run_folder = sys.argv[1] if len(sys.argv) > 1 else "."
    _code, _desc = run_density_validator(_run_folder)
    print(json.dumps({"code": _code, "desc": _desc}))
    sys.exit(0 if _code == "OK" else 1)
