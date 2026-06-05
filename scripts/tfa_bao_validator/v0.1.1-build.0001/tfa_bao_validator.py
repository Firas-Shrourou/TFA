"""
tfa_bao_validator.py — BAO distance-closure validator for TFA run folders.

Reads the completed run folder and checks whether the route's own late-time
distance geometry is self-consistent with the DESI DR2 BAO data vector,
using the route's own calibrated sound horizon r_d_X (not a fixed external ruler).

Physical inputs (all from the run folder):
  H_X(z)  — expansion_history_h0x_normalized.csv
  r_d_X   — run_results_summary.json: results.acoustic_validator.acoustic_anchor.r_drag_Mpc
  geometry — flat (Omega_K = 0 by TFA construction, asserted at runtime)

BAO observables computed:
  D_H(z) = c / H_X(z)
  D_M(z) = c * integral_0^z dz' / H_X(z')
  D_V(z) = [z * D_M(z)^2 * D_H(z)]^(1/3)
  model_ratio = D_X(z_eff) / r_d_X   for each observable type

Dataset: DESI DR2 ALL GCcomb (13 data points), bundled in TFA-package/data/.

Entry point: run_bao_validator(run_folder) -> (Code, Desc)
Gated: silently skips when the export gate rejected the route (no normalized history).
Non-fatal in hub: failure is recorded but does not affect physics verdict.
"""

from __future__ import annotations

import csv
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.integrate import quad
from scipy.interpolate import PchipInterpolator


TFA_PROJECT_RELEASE = "0.0.2"
SCRIPT_NAME = "tfa_bao_validator"
SCRIPT_VERSION = "0.1.1"
SCRIPT_BUILD = "0001"
SCRIPT_API_VERSION = "0.1"

SUMMARY_FILENAME = "run_results_summary.json"
FROZEN_SETTINGS_FILENAME = "environment-settings.json"
HISTORY_NORMALIZED_FILENAME = "expansion_history_h0x_normalized.csv"
PER_DATUM_CSV_FILENAME = "bao_results_per_datum.csv"
PULLS_PLOT_STEM = "bao_pulls"

C_KMS = 299792.458
DATASET_LABEL = "DESI_DR2_ALL_GCcomb"
DEFAULT_NORMALIZATION_TOLERANCE = 1.0e-10

_DATUM_STATUS_COLORS = {
    "PASS_1SIGMA":    "#2ca02c",
    "PASS_2SIGMA":    "#ff7f0e",
    "PASS_3SIGMA":    "#9467bd",
    "OUTSIDE_3SIGMA": "#d62728",
}


def script_identity() -> dict[str, str]:
    return {
        "tfa_project_release": TFA_PROJECT_RELEASE,
        "script_name": SCRIPT_NAME,
        "script_version": SCRIPT_VERSION,
        "script_build": SCRIPT_BUILD,
        "script_api_version": SCRIPT_API_VERSION,
    }


# ---------------------------------------------------------------------------
# Datum dataclass and status labeler
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BaoDatum:
    index: int
    z_eff: float
    observed: float
    observable: str
    sigma: float


def datum_status(pull: float) -> str:
    ap = abs(pull)
    if ap <= 1.0:
        return "PASS_1SIGMA"
    if ap <= 2.0:
        return "PASS_2SIGMA"
    if ap <= 3.0:
        return "PASS_3SIGMA"
    return "OUTSIDE_3SIGMA"


# ---------------------------------------------------------------------------
# Data bundle locator
# ---------------------------------------------------------------------------

def _find_data_dir() -> Path:
    """Walk up from this file to find TFA-package/data/desi_bao_dr2/."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "data" / "desi_bao_dr2"
        if candidate.is_dir():
            return candidate
    raise FileNotFoundError(
        "MISSING_BAO_DATA: cannot locate TFA-package/data/desi_bao_dr2/ "
        f"walking up from {here}"
    )


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------

def _read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _atomic_write_json(path: Path, obj: object) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, sort_keys=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _read_normalized_history(path: Path) -> tuple[dict[str, str], np.ndarray, np.ndarray]:
    """Read expansion_history_h0x_normalized.csv.

    Returns (meta, z_arr, H_X_arr).  Comment-header rows (# key, value) are
    parsed into meta; data rows yield z and H_X float arrays.
    """
    meta: dict[str, str] = {}
    headers: list[str] = []
    z_vals: list[float] = []
    h_vals: list[float] = []
    with path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        for row in reader:
            if not row:
                continue
            first = row[0].strip()
            if first.startswith("#"):
                key = first.lstrip("# ").strip()
                value = row[1].strip() if len(row) > 1 else ""
                meta[key] = value
            elif not headers:
                headers = [h.strip() for h in row]
            else:
                z_vals.append(float(row[headers.index("z")]))
                h_vals.append(float(row[headers.index("H_X")]))
    return meta, np.asarray(z_vals, dtype=float), np.asarray(h_vals, dtype=float)


def _load_bao_data(data_dir: Path) -> tuple[list[BaoDatum], np.ndarray]:
    """Load DESI DR2 BAO mean vector and covariance matrix."""
    mean_path = data_dir / "desi_gaussian_bao_ALL_GCcomb_mean.txt"
    cov_path  = data_dir / "desi_gaussian_bao_ALL_GCcomb_cov.txt"
    if not mean_path.exists():
        raise FileNotFoundError(f"MISSING_BAO_DATA: {mean_path}")
    if not cov_path.exists():
        raise FileNotFoundError(f"MISSING_OR_BAD_COVARIANCE: {cov_path}")

    rows: list[tuple[float, float, str]] = []
    for line in mean_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split()
        if len(parts) != 3:
            raise ValueError(f"MISSING_BAO_DATA: malformed row: {line!r}")
        rows.append((float(parts[0]), float(parts[1]), parts[2]))

    cov = np.loadtxt(cov_path)
    n = len(rows)
    if cov.shape != (n, n):
        raise ValueError(f"MISSING_OR_BAD_COVARIANCE: shape {cov.shape}, expected ({n},{n})")
    if not np.isfinite(cov).all():
        raise ValueError("MISSING_OR_BAD_COVARIANCE: non-finite entries")
    if not np.all(np.diag(cov) > 0):
        raise ValueError("MISSING_OR_BAD_COVARIANCE: non-positive diagonal")
    if not np.all(np.linalg.eigvalsh(cov) > 0):
        raise ValueError("MISSING_OR_BAD_COVARIANCE: not positive definite")

    sigma = np.sqrt(np.diag(cov))
    data = [
        BaoDatum(index=i, z_eff=z, observed=obs, observable=observable, sigma=float(sigma[i]))
        for i, (z, obs, observable) in enumerate(rows)
    ]
    return data, cov


# ---------------------------------------------------------------------------
# Normalization contract check
# ---------------------------------------------------------------------------

def _check_normalization(
    meta: dict[str, str],
    z: np.ndarray,
    H_X: np.ndarray,
    bao_z_max: float,
) -> str:
    """Return "PASS" or a named stop-code."""
    if "H0_X" not in meta:
        return "MISSING_H0X"
    if meta.get("normalization_mode") != "h0x_normalized":
        return "MISSING_NORMALIZATION_STATE"
    if meta.get("normalization_check") != "PASS":
        return "NORMALIZATION_CHECK_FAILED"

    h0_x = float(meta["H0_X"])
    tolerance = float(meta.get("normalization_tolerance", DEFAULT_NORMALIZATION_TOLERANCE))
    residual = float(meta.get("normalization_residual", "nan"))
    h_at_z0 = float(H_X[np.argmin(np.abs(z))])

    if abs(h_at_z0 - h0_x) > tolerance:
        return "NORMALIZATION_MISMATCH"
    if abs(residual) > tolerance:
        return "NORMALIZATION_CHECK_FAILED"
    if float(np.min(z)) > 0.0 or float(np.max(z)) < bao_z_max:
        return "HISTORY_RANGE_INSUFFICIENT"
    if np.any(np.diff(z) <= 0):
        return "HISTORY_NOT_MONOTONE"
    if np.any(H_X <= 0):
        return "HISTORY_NONPOSITIVE_HX"
    return "PASS"


# ---------------------------------------------------------------------------
# Core BAO computation
# ---------------------------------------------------------------------------

def _compute_bao_model(
    z: np.ndarray,
    H_X: np.ndarray,
    data: list[BaoDatum],
    rd_X: float,
) -> list[dict[str, Any]]:
    """Compute per-datum BAO model observables using the route's own r_d_X.

    Geometry: flat (Omega_K = 0). D_M = D_C = c * integral_0^z dz'/H_X(z').
    No manual compensation, no double normalization, no CPL approximation.
    """
    interpolator = PchipInterpolator(z, H_X, extrapolate=False)

    def h_of_z(z_val: float) -> float:
        val = float(interpolator(z_val))
        if not np.isfinite(val) or val <= 0.0:
            raise ValueError(f"invalid H_X interpolation at z={z_val}")
        return val

    rows: list[dict[str, Any]] = []
    for datum in data:
        h_z = h_of_z(datum.z_eff)
        d_h = C_KMS / h_z
        d_m = C_KMS * quad(
            lambda zp: 1.0 / float(interpolator(zp)),
            0.0, datum.z_eff,
            epsabs=1.0e-9, epsrel=1.0e-9, limit=200,
        )[0]
        d_v = (datum.z_eff * d_m * d_m * d_h) ** (1.0 / 3.0)

        if datum.observable == "DM_over_rs":
            model = d_m / rd_X
        elif datum.observable == "DH_over_rs":
            model = d_h / rd_X
        elif datum.observable == "DV_over_rs":
            model = d_v / rd_X
        else:
            raise ValueError(f"unsupported observable: {datum.observable!r}")

        residual = model - datum.observed
        pull = residual / datum.sigma
        rows.append({
            "datum_index":         datum.index,
            "z_eff":               datum.z_eff,
            "observable":          datum.observable,
            "observed":            datum.observed,
            "sigma":               datum.sigma,
            "model":               model,
            "residual":            residual,
            "pull":                pull,
            "datum_status":        datum_status(pull),
            "D_H_Mpc":             d_h,
            "D_M_Mpc":             d_m,
            "D_V_Mpc":             d_v,
            "rd_X_Mpc":            rd_X,
            "interpolation_method": "PchipInterpolator",
        })
    return rows


# ---------------------------------------------------------------------------
# Output writers
# ---------------------------------------------------------------------------

def _write_per_datum_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "datum_index", "z_eff", "observable", "observed", "sigma",
        "model", "residual", "pull", "datum_status",
        "D_H_Mpc", "D_M_Mpc", "D_V_Mpc", "rd_X_Mpc", "interpolation_method",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({
                k: (f"{v:.12g}" if isinstance(v, float) else v)
                for k, v in row.items()
            })


def _save_pull_plot(
    rows: list[dict[str, Any]],
    summary: dict,
    outdir: Path,
) -> None:
    """Bar chart of per-datum pulls, colored by datum_status."""
    bid    = summary.get("contract", {}).get("benchmark_id", "")
    av     = summary.get("results", {}).get("acoustic_validator", {})
    H0X    = float(av.get("H0_X_kms", float("nan")))
    band   = str(av.get("band", ""))
    bv     = summary.get("results", {}).get("bao_validator", {})
    chi2   = float(bv.get("chi2",         float("nan")))
    rdchi2 = float(bv.get("reduced_chi2", float("nan")))
    rd_X   = float(bv.get("rd_X_Mpc",    float("nan")))

    labels = [f"z={r['z_eff']}\n{r['observable']}" for r in rows]
    pulls  = [float(r["pull"]) for r in rows]
    colors = [_DATUM_STATUS_COLORS.get(r["datum_status"], "#888") for r in rows]
    x = np.arange(len(rows))

    fig, ax = plt.subplots(figsize=(10, 4.5))
    ax.bar(x, pulls, color=colors, edgecolor="white", width=0.7)
    ax.axhline(0,   color="#333", lw=0.8)
    ax.axhline( 1,  color="#2ca02c", lw=0.8, ls="--", alpha=0.6)
    ax.axhline(-1,  color="#2ca02c", lw=0.8, ls="--", alpha=0.6)
    ax.axhline( 2,  color="#ff7f0e", lw=0.8, ls=":",  alpha=0.6)
    ax.axhline(-2,  color="#ff7f0e", lw=0.8, ls=":",  alpha=0.6)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=7)
    ax.set_ylabel(r"pull  $= ({\rm model} - {\rm observed})\,/\,\sigma$")
    ax.set_title(
        f"{bid}  —  DESI DR2 BAO pulls  "
        f"($H_{{0,X}} = {H0X:.2f}$, {band})"
    )
    ax.text(
        0.99, 0.97,
        f"$\\chi^2 = {chi2:.2f}$  "
        f"$\\chi^2_\\nu = {rdchi2:.3f}$  (dof = {len(rows)})\n"
        f"$r_{{d,X}} = {rd_X:.4f}$ Mpc  [route acoustic anchor]",
        transform=ax.transAxes, ha="right", va="top", fontsize=8,
        bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="#ccc", alpha=0.9),
    )
    # legend patches
    from matplotlib.patches import Patch
    legend_els = [
        Patch(fc=_DATUM_STATUS_COLORS["PASS_1SIGMA"],    label="1σ"),
        Patch(fc=_DATUM_STATUS_COLORS["PASS_2SIGMA"],    label="2σ"),
        Patch(fc=_DATUM_STATUS_COLORS["PASS_3SIGMA"],    label="3σ"),
        Patch(fc=_DATUM_STATUS_COLORS["OUTSIDE_3SIGMA"], label=">3σ"),
    ]
    ax.legend(handles=legend_els, fontsize=8, loc="lower right")
    ax.grid(True, axis="y", lw=0.4, alpha=0.5)
    fig.tight_layout()
    for ext in ("png", "pdf"):
        fig.savefig(str(outdir / f"{PULLS_PLOT_STEM}.{ext}"), dpi=150, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------
# File-based entry point
# ---------------------------------------------------------------------------

def run_bao_validator(run_folder: str | Path) -> tuple[str, str]:
    """File-based BAO entry point. Returns (Code, Desc).

    Reads the route's normalized history and acoustic anchor from the run
    folder, computes BAO distance observables against DESI DR2, and enriches
    run_results_summary.json under results["bao_validator"].

    Doubly gated:
    - skips if expansion_history_h0x_normalized.csv is absent (export gate rejected)
    - skips if r_s_Mpc is absent from the acoustic anchor summary

    Non-fatal: exceptions are caught and reported as ("Error", ...).
    """
    try:
        run_folder = Path(run_folder)
        summary_path  = run_folder / SUMMARY_FILENAME
        settings_path = run_folder / FROZEN_SETTINGS_FILENAME
        hist_path     = run_folder / HISTORY_NORMALIZED_FILENAME

        if not summary_path.exists():
            return ("Error", f"{SUMMARY_FILENAME} not found in {run_folder}")
        if not settings_path.exists():
            return ("Error", f"{FROZEN_SETTINGS_FILENAME} not found in {run_folder}")

        # --- 1. Check enabled flag ------------------------------------------
        settings = _read_json(settings_path)
        enabled = settings.get("user_adjustable", {}).get(
            "bao_validator", {}
        ).get("enabled", True)
        if not enabled:
            _record_skip(summary_path, "bao_validator disabled in settings")
            return ("OK", "bao_validator disabled")

        # --- 2. Gate: normalized history must exist -------------------------
        if not hist_path.exists():
            _record_skip(summary_path, "route not accepted by export gate")
            return ("OK", "bao_validator skipped: route not accepted by export gate")

        # --- 3. Gate: r_drag_Mpc must be in the summary --------------------
        # r_drag_Mpc is the drag-epoch sound horizon (Eisenstein-Hu 1998),
        # z_drag < z_star, so r_drag > r_s(z_star).  DESI BAO ratios
        # D_X/r_d use the drag-epoch ruler; r_s_Mpc (z_star) is ~3% too small.
        summary  = _read_json(summary_path)
        anc      = summary.get("results", {}).get(
            "acoustic_validator", {}
        ).get("acoustic_anchor", {})
        rd_X_raw = anc.get("r_drag_Mpc")
        if rd_X_raw is None:
            _record_skip(summary_path, "r_drag_Mpc not found in acoustic_anchor (requires acoustic validator >= 0.1.4)")
            return ("OK", "bao_validator skipped: r_drag_Mpc not found in acoustic_anchor")
        rd_X = float(rd_X_raw)
        if not np.isfinite(rd_X) or rd_X <= 0.0:
            return ("Error", f"bao_validator: invalid r_drag_Mpc = {rd_X}")

        # --- 4. Assert flat geometry ----------------------------------------
        cosmo   = settings.get("user_adjustable", {}).get("cosmology", {})
        Om      = float(cosmo.get("Omega_m0", 0.0))
        Or      = float(cosmo.get("Omega_r0", 0.0))
        ode_raw = cosmo.get("Omega_DE")
        ODE     = float(ode_raw) if ode_raw is not None else (1.0 - Om - Or)
        Omega_K = 1.0 - Om - Or - ODE
        if abs(Omega_K) > 1e-6:
            return ("Error", f"bao_validator: non-flat geometry Omega_K = {Omega_K:.2e}")

        # --- 5. Load BAO data -----------------------------------------------
        data_dir    = _find_data_dir()
        bao_data, cov = _load_bao_data(data_dir)
        bao_z_max   = max(d.z_eff for d in bao_data)

        # --- 6. Load and check normalized history ---------------------------
        meta, z, H_X = _read_normalized_history(hist_path)
        contract_status = _check_normalization(meta, z, H_X, bao_z_max)
        if contract_status != "PASS":
            return ("Error", f"bao_validator normalization contract: {contract_status}")

        # --- 7. Compute BAO model values ------------------------------------
        per_datum = _compute_bao_model(z, H_X, bao_data, rd_X)

        # --- 8. Chi-squared (full covariance) -------------------------------
        inv_cov   = np.linalg.inv(cov)
        residuals = np.array([r["residual"] for r in per_datum], dtype=float)
        pulls_arr = np.array([r["pull"]     for r in per_datum], dtype=float)
        chi2      = float(residuals @ inv_cov @ residuals)
        dof       = len(bao_data)
        chi2_diag = float(np.sum(pulls_arr ** 2))
        max_pull  = float(np.max(np.abs(pulls_arr)))

        statuses  = [r["datum_status"] for r in per_datum]
        n_1s = sum(1 for s in statuses if s == "PASS_1SIGMA")
        n_2s = sum(1 for s in statuses if s in ("PASS_1SIGMA", "PASS_2SIGMA"))
        n_3s = sum(1 for s in statuses if s in ("PASS_1SIGMA", "PASS_2SIGMA", "PASS_3SIGMA"))
        n_out = dof - n_3s

        # --- 9. Write per-datum CSV ----------------------------------------
        _write_per_datum_csv(run_folder / PER_DATUM_CSV_FILENAME, per_datum)

        # --- 10. Enrich summary (before plot, so plot can read chi2) --------
        summary = _read_json(summary_path)
        summary.setdefault("results", {})["bao_validator"] = {
            "status":                 "OK",
            "script":                 script_identity(),
            "dataset_label":          DATASET_LABEL,
            "rd_X_Mpc":               rd_X,
            "rd_source":              "acoustic_anchor.r_drag_Mpc",
            "geometry":               "flat",
            "Omega_K":                round(Omega_K, 9),
            "datum_count":            dof,
            "chi2":                   chi2,
            "dof":                    dof,
            "reduced_chi2":           chi2 / dof,
            "chi2_diag":              chi2_diag,
            "reduced_chi2_diag":      chi2_diag / dof,
            "max_abs_pull":           max_pull,
            "n_within_1sigma":        n_1s,
            "n_within_2sigma":        n_2s,
            "n_within_3sigma":        n_3s,
            "n_outside_3sigma":       n_out,
            "bao_results_per_datum_csv": PER_DATUM_CSV_FILENAME,
            "bao_pulls_plot":         f"{PULLS_PLOT_STEM}.png",
            "interpolation_method":   "PchipInterpolator",
            "normalization_check":    "PASS",
        }
        _atomic_write_json(summary_path, summary)

        # --- 11. Pull plot --------------------------------------------------
        summary_for_plot = _read_json(summary_path)
        _save_pull_plot(per_datum, summary_for_plot, run_folder)

        desc = (
            f"bao_validator complete: "
            f"chi2={chi2:.4f} reduced={chi2/dof:.4f} "
            f"[{n_2s}/{dof} within 2σ]  "
            f"rd_X={rd_X:.4f} Mpc"
        )
        return ("OK", desc)

    except Exception as exc:
        return ("Error", f"{type(exc).__name__}: {exc}")


def _record_skip(summary_path: Path, reason: str) -> None:
    """Write a minimal skip record into the summary."""
    try:
        summary = _read_json(summary_path)
        summary.setdefault("results", {})["bao_validator"] = {
            "status": "skipped",
            "reason": reason,
            "script": script_identity(),
        }
        _atomic_write_json(summary_path, summary)
    except Exception:
        pass
