"""
tfa_rsd_validator.py — RSD growth-rate validator for TFA run folders.

Reads the completed run folder and checks whether the route's expansion
history produces a linear growth rate f·σ₈(z) consistent with the gold
compilation of redshift-space distortion (RSD) measurements.

Physical inputs (all from the run folder):
  H_X(z)   — expansion_history_h0x_normalized.csv
  H0_X     — from H_X(z) CSV metadata
  cosmology — frozen environment-settings.json

Method:
  Integrates the linear growth ODE against H_X(z), computes f·σ₈ at each
  datum redshift, and compares against the bundled 18-point gold compilation
  using a diagonal chi² (independent surveys).

  sigma8_X = sigma8_ref × D_X(a=1) / D_ΛCDM(a=1)
  f·σ₈(z)  = f_X(z) × sigma8_ref × D_X(z) / D_ΛCDM(a=1)

  where sigma8_ref = 0.8111 (Planck 2018 ΛCDM anchor, fixed external).

Dataset: 18-point f·σ₈ gold compilation, bundled in TFA-package/data/.

Entry point: run_rsd_validator(run_folder) -> (Code, Desc)
Gated: silently skips when export gate rejected the route.
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
from matplotlib.patches import Patch
from scipy.integrate import solve_ivp
from scipy.interpolate import PchipInterpolator


TFA_PROJECT_RELEASE = "0.0.2"
SCRIPT_NAME = "tfa_rsd_validator"
SCRIPT_VERSION = "0.1.0"
SCRIPT_BUILD = "0001"
SCRIPT_API_VERSION = "0.1"

SUMMARY_FILENAME = "run_results_summary.json"
FROZEN_SETTINGS_FILENAME = "environment-settings.json"
HISTORY_NORMALIZED_FILENAME = "expansion_history_h0x_normalized.csv"
PER_DATUM_CSV_FILENAME = "rsd_results_per_datum.csv"
PULLS_PLOT_STEM = "rsd_pulls"
GROWTH_PLOT_STEM = "rsd_growth"

SIGMA8_REFERENCE = 0.8111
GROWTH_Z_START = 10.0
DATASET_LABEL = "fsigma8_gold_compilation"
DEFAULT_NORMALIZATION_TOLERANCE = 1.0e-10

_DATUM_STATUS_COLORS = {
    "PASS_1SIGMA":    "#2ca02c",
    "PASS_2SIGMA":    "#ff7f0e",
    "PASS_3SIGMA":    "#9467bd",
    "OUTSIDE_3SIGMA": "#d62728",
}

_BAND_COLORS = {
    "STRICT":    "#2ca02c",
    "LOOSE_2S":  "#ff7f0e",
    "LOOSE_3S":  "#9467bd",
    "EXCLUDED":  "#d62728",
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
class RsdDatum:
    index: int
    z_eff: float
    fsigma8_obs: float
    sigma: float
    survey: str


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
    """Walk up from this file to find TFA-package/data/fsigma8_gold/."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "data" / "fsigma8_gold"
        if candidate.is_dir():
            return candidate
    raise FileNotFoundError(
        "MISSING_RSD_DATA: cannot locate TFA-package/data/fsigma8_gold/ "
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
    """Read expansion_history_h0x_normalized.csv → (meta, z_arr, H_X_arr)."""
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


def _load_rsd_data(data_dir: Path) -> tuple[list[RsdDatum], np.ndarray]:
    """Load f·σ₈ gold compilation mean vector and covariance matrix."""
    mean_path = data_dir / "fsigma8_gold_mean.txt"
    cov_path  = data_dir / "fsigma8_gold_cov.txt"
    if not mean_path.exists():
        raise FileNotFoundError(f"MISSING_RSD_DATA: {mean_path}")
    if not cov_path.exists():
        raise FileNotFoundError(f"MISSING_RSD_DATA: {cov_path}")

    rows: list[tuple[float, float, float, str]] = []
    for line in mean_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split()
        if len(parts) != 4:
            raise ValueError(f"MISSING_RSD_DATA: malformed row: {line!r}")
        rows.append((float(parts[0]), float(parts[1]), float(parts[2]), parts[3]))

    cov = np.loadtxt(cov_path, comments="#")
    n = len(rows)
    if cov.shape != (n, n):
        raise ValueError(f"MISSING_RSD_DATA: covariance shape {cov.shape}, expected ({n},{n})")
    if not np.isfinite(cov).all():
        raise ValueError("MISSING_RSD_DATA: non-finite covariance entries")
    if not np.all(np.diag(cov) > 0):
        raise ValueError("MISSING_RSD_DATA: non-positive diagonal in covariance")
    if not np.all(np.linalg.eigvalsh(cov) > 0):
        raise ValueError("MISSING_RSD_DATA: covariance not positive definite")

    data = [
        RsdDatum(index=i, z_eff=z, fsigma8_obs=fs8, sigma=sig, survey=survey)
        for i, (z, fs8, sig, survey) in enumerate(rows)
    ]
    return data, cov


# ---------------------------------------------------------------------------
# Normalization contract check (same stop-codes as BAO validator)
# ---------------------------------------------------------------------------

def _check_normalization(
    meta: dict[str, str],
    z: np.ndarray,
    H_X: np.ndarray,
) -> str:
    if "H0_X" not in meta:
        return "MISSING_H0X"
    if meta.get("normalization_mode") != "h0x_normalized":
        return "MISSING_NORMALIZATION_STATE"
    if meta.get("normalization_check") != "PASS":
        return "NORMALIZATION_CHECK_FAILED"
    h0_x = float(meta["H0_X"])
    tolerance = float(meta.get("normalization_tolerance", DEFAULT_NORMALIZATION_TOLERANCE))
    residual  = float(meta.get("normalization_residual", "nan"))
    h_at_z0   = float(H_X[np.argmin(np.abs(z))])
    if abs(h_at_z0 - h0_x) > tolerance:
        return "NORMALIZATION_MISMATCH"
    if abs(residual) > tolerance:
        return "NORMALIZATION_CHECK_FAILED"
    if np.any(np.diff(z) <= 0):
        return "HISTORY_NOT_MONOTONE"
    if np.any(H_X <= 0):
        return "HISTORY_NONPOSITIVE_HX"
    return "PASS"


# ---------------------------------------------------------------------------
# Hubble functions (ported from CMB-lensing blind test)
# ---------------------------------------------------------------------------

def _build_branch_h(
    z_arr: np.ndarray,
    H_X_arr: np.ndarray,
    h0_x: float,
    omega_m_x: float,
    omega_r_x: float,
) -> Any:
    """Branch Hubble function: PCHIP interpolation + high-z matter+radiation extension."""
    interpolator = PchipInterpolator(z_arr, H_X_arr, extrapolate=False)
    z_max = float(np.max(z_arr))

    def h_func(z_val: float) -> float:
        if -1.0e-12 < z_val < 0.0:
            z_val = 0.0
        if z_val <= z_max:
            val = float(interpolator(z_val))
            if not np.isfinite(val) or val <= 0.0:
                raise RuntimeError(f"RSD_BRANCH_H: invalid H_X at z={z_val}")
            return val
        return h0_x * np.sqrt(omega_m_x * (1.0 + z_val)**3 + omega_r_x * (1.0 + z_val)**4)

    return h_func


def _build_lcdm_h(h0_x: float, omega_m_x: float, omega_r_x: float) -> Any:
    """ΛCDM reference Hubble: same H0_X and omega_m_x as branch (measures only DE effect)."""
    omega_lambda_x = 1.0 - omega_m_x - omega_r_x

    def h_func(z_val: float) -> float:
        if -1.0e-12 < z_val < 0.0:
            z_val = 0.0
        return h0_x * np.sqrt(
            omega_m_x * (1.0 + z_val)**3
            + omega_r_x * (1.0 + z_val)**4
            + omega_lambda_x
        )

    return h_func


# ---------------------------------------------------------------------------
# Growth ODE solver (ported from CMB-lensing blind test, with dense_output)
# ---------------------------------------------------------------------------

def _integrate_growth(
    h_func: Any,
    h0_x: float,
    omega_m_x: float,
    z_start: float,
) -> Any:
    """Integrate the linear growth ODE; return solve_ivp result with dense_output.

    State: y = [D, dD/da].  Initial condition: EdS approximation at a_ini.
    dense_output=True enables sol.sol(a) evaluation at arbitrary a in range.
    """
    a_ini   = 1.0 / (1.0 + z_start)
    da_frac = 1.0e-4

    def rhs(a: float, y: list) -> list:
        D, dD = y
        z_here = 1.0 / a - 1.0
        h_a = h_func(z_here)
        ap  = a * (1.0 + da_frac)
        am  = a * (1.0 - da_frac)
        if ap > 1.0:
            d_h_da = (h_a - h_func(1.0 / am - 1.0)) / (a - am)
        else:
            d_h_da = (h_func(1.0 / ap - 1.0) - h_func(1.0 / am - 1.0)) / (ap - am)
        dlnh_da = d_h_da / h_a
        source  = 1.5 * omega_m_x * (h0_x / h_a)**2 / a**5 * D
        return [dD, -(3.0 / a + dlnh_da) * dD + source]

    y0  = [a_ini, 1.0]
    sol = solve_ivp(
        rhs, [a_ini, 1.0], y0,
        method="DOP853", rtol=1.0e-10, atol=1.0e-12,
        dense_output=True,
    )
    if not sol.success:
        raise RuntimeError(f"RSD_GROWTH_ODE_FAILED: {sol.message}")
    return sol


# ---------------------------------------------------------------------------
# Per-datum f·σ₈ computation
# ---------------------------------------------------------------------------

def _compute_fsigma8_model(
    sol_X: Any,
    sol_LCDM: Any,
    data: list[RsdDatum],
) -> tuple[float, float, list[dict[str, Any]]]:
    """Compute growth_ratio, sigma8_X, and per-datum f·σ₈ model rows.

    growth_ratio = D_X(a=1) / D_LCDM(a=1)
    sigma8_X     = SIGMA8_REFERENCE × growth_ratio

    Per datum at z_eff:
      D_X(a_z), dD/da from sol_X.sol(a_z)
      f_X(z) = a_z × (dD/da) / D_X(a_z)
      fsigma8_model = f_X × SIGMA8_REFERENCE × D_X(a_z) / D_LCDM(a=1)
    """
    a_end = min(1.0, float(sol_X.t[-1]))
    D_X_at_1    = float(sol_X.sol(a_end)[0])
    D_LCDM_at_1 = float(sol_LCDM.sol(min(1.0, float(sol_LCDM.t[-1])))[0])
    growth_ratio = D_X_at_1 / D_LCDM_at_1
    sigma8_X     = SIGMA8_REFERENCE * growth_ratio

    rows: list[dict[str, Any]] = []
    for datum in data:
        a_z  = 1.0 / (1.0 + datum.z_eff)
        state = sol_X.sol(a_z)
        D_z   = float(state[0])
        dDda  = float(state[1])
        f_X   = a_z * dDda / D_z                                  # dlnD/dlna
        fsigma8_model = f_X * SIGMA8_REFERENCE * D_z / D_LCDM_at_1
        residual = fsigma8_model - datum.fsigma8_obs
        pull     = residual / datum.sigma
        rows.append({
            "datum_index":    datum.index,
            "z_eff":          datum.z_eff,
            "survey":         datum.survey,
            "observed":       datum.fsigma8_obs,
            "sigma":          datum.sigma,
            "model":          fsigma8_model,
            "residual":       residual,
            "pull":           pull,
            "datum_status":   datum_status(pull),
            "f_X":            f_X,
            "sigma8_X":       sigma8_X,
            "D_X_norm":       D_z / D_LCDM_at_1,
            "growth_ratio":   growth_ratio,
        })
    return growth_ratio, sigma8_X, rows


# ---------------------------------------------------------------------------
# Output writers
# ---------------------------------------------------------------------------

def _write_per_datum_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "datum_index", "z_eff", "survey", "observed", "sigma",
        "model", "residual", "pull", "datum_status",
        "f_X", "sigma8_X", "D_X_norm", "growth_ratio",
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
    """Pull bar chart for RSD data (same style as BAO validator)."""
    bid    = summary.get("contract", {}).get("benchmark_id", "")
    av     = summary.get("results", {}).get("acoustic_validator", {})
    H0X    = float(av.get("H0_X_kms", float("nan")))
    band   = str(av.get("band", ""))
    rv     = summary.get("results", {}).get("rsd_validator", {})
    chi2   = float(rv.get("chi2",         float("nan")))
    rdchi2 = float(rv.get("reduced_chi2", float("nan")))
    sig8X  = float(rv.get("sigma8_X",     float("nan")))

    labels = [f"z={r['z_eff']}\n{r['survey'][:8]}" for r in rows]
    pulls  = [float(r["pull"]) for r in rows]
    colors = [_DATUM_STATUS_COLORS.get(r["datum_status"], "#888") for r in rows]
    x = np.arange(len(rows))

    fig, ax = plt.subplots(figsize=(12, 4.5))
    ax.bar(x, pulls, color=colors, edgecolor="white", width=0.7)
    ax.axhline(0,  color="#333", lw=0.8)
    ax.axhline( 1, color="#2ca02c", lw=0.8, ls="--", alpha=0.6)
    ax.axhline(-1, color="#2ca02c", lw=0.8, ls="--", alpha=0.6)
    ax.axhline( 2, color="#ff7f0e", lw=0.8, ls=":",  alpha=0.6)
    ax.axhline(-2, color="#ff7f0e", lw=0.8, ls=":",  alpha=0.6)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=6.5)
    ax.set_ylabel(r"pull  $= ({\rm model} - {\rm observed})\,/\,\sigma$")
    ax.set_title(
        f"{bid}  —  RSD $f\\sigma_8$ pulls  "
        f"($H_{{0,X}} = {H0X:.2f}$, {band})"
    )
    ax.text(
        0.99, 0.97,
        f"$\\chi^2 = {chi2:.2f}$  "
        f"$\\chi^2_\\nu = {rdchi2:.3f}$  (dof = {len(rows)})\n"
        f"$\\sigma_{{8,X}} = {sig8X:.4f}$  [Planck anchor = {SIGMA8_REFERENCE}]",
        transform=ax.transAxes, ha="right", va="top", fontsize=8,
        bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="#ccc", alpha=0.9),
    )
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


def _save_growth_plot(
    rows: list[dict[str, Any]],
    sol_X: Any,
    sol_LCDM: Any,
    summary: dict,
    outdir: Path,
) -> None:
    """Continuous (f·σ₈)_X(z) curve vs data points + ΛCDM reference."""
    bid    = summary.get("contract", {}).get("benchmark_id", "")
    av     = summary.get("results", {}).get("acoustic_validator", {})
    H0X    = float(av.get("H0_X_kms", float("nan")))
    band   = str(av.get("band", ""))
    rv     = summary.get("results", {}).get("rsd_validator", {})
    sig8X  = float(rv.get("sigma8_X",   float("nan")))
    chi2   = float(rv.get("chi2",       float("nan")))

    D_LCDM_at_1 = float(sol_LCDM.sol(min(1.0, float(sol_LCDM.t[-1])))[0])
    band_color   = _BAND_COLORS.get(band, "#333")

    # Continuous curves
    z_curve = np.linspace(0.001, 1.6, 300)
    fs8_X    = []
    fs8_lcdm = []
    for zc in z_curve:
        a_c = 1.0 / (1.0 + zc)
        st = sol_X.sol(a_c)
        D_c, dD_c = float(st[0]), float(st[1])
        f_c  = a_c * dD_c / D_c
        fs8_X.append(f_c * SIGMA8_REFERENCE * D_c / D_LCDM_at_1)

        st_l = sol_LCDM.sol(a_c)
        D_lc, dD_lc = float(st_l[0]), float(st_l[1])
        f_lc  = a_c * dD_lc / D_lc
        D_L1  = D_LCDM_at_1
        fs8_lcdm.append(f_lc * SIGMA8_REFERENCE * D_lc / D_L1)

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(z_curve, fs8_X,    color=band_color, lw=2.0, label=f"{bid}  ($H_{{0,X}}={H0X:.2f}$)")
    ax.plot(z_curve, fs8_lcdm, color="#888",     lw=1.2, ls="--", label=r"$\Lambda$CDM reference")

    # Data points
    for r in rows:
        col = _DATUM_STATUS_COLORS.get(r["datum_status"], "#888")
        ax.errorbar(
            r["z_eff"], r["observed"], yerr=r["sigma"],
            fmt="o", color=col, ms=5, lw=1.2, zorder=5,
        )

    # Legend patches for data color coding
    legend_els = [
        plt.Line2D([0], [0], color=band_color, lw=2, label=f"{bid}"),
        plt.Line2D([0], [0], color="#888",     lw=1.2, ls="--", label=r"$\Lambda$CDM"),
        Patch(fc=_DATUM_STATUS_COLORS["PASS_1SIGMA"],    label="data 1σ"),
        Patch(fc=_DATUM_STATUS_COLORS["PASS_2SIGMA"],    label="data 2σ"),
        Patch(fc=_DATUM_STATUS_COLORS["PASS_3SIGMA"],    label="data 3σ"),
        Patch(fc=_DATUM_STATUS_COLORS["OUTSIDE_3SIGMA"], label="data >3σ"),
    ]
    ax.legend(handles=legend_els, fontsize=8, loc="upper right")
    ax.set_xlabel("Redshift $z$")
    ax.set_ylabel(r"$f\sigma_8(z)$")
    ax.set_title(f"Growth rate:  {bid}  vs RSD gold compilation  ({band})")
    ax.text(
        0.02, 0.05,
        f"$\\sigma_{{8,X}} = {sig8X:.4f}$   $\\chi^2 = {chi2:.2f}$   (dof = {len(rows)})",
        transform=ax.transAxes, fontsize=8,
        bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="#ccc", alpha=0.9),
    )
    ax.grid(True, lw=0.4, alpha=0.4)
    ax.set_xlim(0.0, 1.6)
    fig.tight_layout()
    for ext in ("png", "pdf"):
        fig.savefig(str(outdir / f"{GROWTH_PLOT_STEM}.{ext}"), dpi=150, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Skip recorder
# ---------------------------------------------------------------------------

def _record_skip(summary_path: Path, reason: str) -> None:
    try:
        summary = _read_json(summary_path)
        summary.setdefault("results", {})["rsd_validator"] = {
            "status": "skipped",
            "reason": reason,
            "script": script_identity(),
        }
        _atomic_write_json(summary_path, summary)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# File-based entry point
# ---------------------------------------------------------------------------

def run_rsd_validator(run_folder: str | Path) -> tuple[str, str]:
    """File-based RSD entry point. Returns (Code, Desc).

    Reads H_X(z) from the run folder, integrates the linear growth ODE,
    computes f·σ₈ at each datum redshift, and compares against the gold
    compilation. Enriches run_results_summary.json under results["rsd_validator"].

    Gated:
    - skips if rsd_validator is disabled in settings
    - skips if expansion_history_h0x_normalized.csv is absent (export gate)
    - skips if r_s_Mpc is absent from acoustic anchor (sentinel for acoustic run)

    Non-fatal: exceptions are caught and reported as ("Error", ...).
    """
    try:
        run_folder    = Path(run_folder)
        summary_path  = run_folder / SUMMARY_FILENAME
        settings_path = run_folder / FROZEN_SETTINGS_FILENAME
        hist_path     = run_folder / HISTORY_NORMALIZED_FILENAME

        if not summary_path.exists():
            return ("Error", f"{SUMMARY_FILENAME} not found in {run_folder}")
        if not settings_path.exists():
            return ("Error", f"{FROZEN_SETTINGS_FILENAME} not found in {run_folder}")

        # --- Gate 1: enabled flag -------------------------------------------
        settings = _read_json(settings_path)
        enabled  = settings.get("user_adjustable", {}).get(
            "rsd_validator", {}
        ).get("enabled", True)
        if not enabled:
            _record_skip(summary_path, "rsd_validator disabled in settings")
            return ("OK", "rsd_validator disabled")

        # --- Gate 2: normalized history must exist --------------------------
        if not hist_path.exists():
            _record_skip(summary_path, "route not accepted by export gate")
            return ("OK", "rsd_validator skipped: route not accepted by export gate")

        # --- Gate 3: r_s_Mpc must exist (sentinel: acoustic validator ran) --
        summary = _read_json(summary_path)
        anc     = summary.get("results", {}).get(
            "acoustic_validator", {}
        ).get("acoustic_anchor", {})
        if anc.get("r_s_Mpc") is None:
            _record_skip(summary_path, "r_s_Mpc not found in acoustic_anchor")
            return ("OK", "rsd_validator skipped: r_s_Mpc not found in acoustic_anchor")

        # --- Extract cosmological parameters --------------------------------
        cosmo     = settings.get("user_adjustable", {}).get("cosmology", {})
        Omega_m0  = float(cosmo.get("Omega_m0", 0.3152))
        Omega_r0  = float(cosmo.get("Omega_r0", 9.18e-5))
        H0_ref    = float(cosmo.get("H0_ref_kms", 67.36))
        h0_x      = float(summary["results"]["acoustic_validator"]["H0_X_kms"])
        omega_m_x = Omega_m0 * (H0_ref / h0_x) ** 2   # physical: omega_m / h_X^2
        omega_r_x = Omega_r0 * (H0_ref / h0_x) ** 2   # scaled radiation density

        # --- Load RSD data --------------------------------------------------
        data_dir = _find_data_dir()
        rsd_data, cov = _load_rsd_data(data_dir)
        dof = len(rsd_data)

        # --- Load and check normalized history ------------------------------
        meta, z_arr, H_X_arr = _read_normalized_history(hist_path)
        norm_status = _check_normalization(meta, z_arr, H_X_arr)
        if norm_status != "PASS":
            return ("Error", f"rsd_validator normalization contract: {norm_status}")

        # --- Build Hubble functions -----------------------------------------
        h_X_func    = _build_branch_h(z_arr, H_X_arr, h0_x, omega_m_x, omega_r_x)
        h_LCDM_func = _build_lcdm_h(h0_x, omega_m_x, omega_r_x)

        # --- Integrate growth ODEs -----------------------------------------
        sol_X    = _integrate_growth(h_X_func,    h0_x, omega_m_x, GROWTH_Z_START)
        sol_LCDM = _integrate_growth(h_LCDM_func, h0_x, omega_m_x, GROWTH_Z_START)

        # --- Per-datum f·σ₈ ------------------------------------------------
        growth_ratio, sigma8_X, per_datum = _compute_fsigma8_model(
            sol_X, sol_LCDM, rsd_data
        )

        # --- Chi² (diagonal covariance = sum of pull²) ----------------------
        inv_cov   = np.linalg.inv(cov)
        residuals = np.array([r["residual"] for r in per_datum], dtype=float)
        pulls_arr = np.array([r["pull"]     for r in per_datum], dtype=float)
        chi2      = float(residuals @ inv_cov @ residuals)
        max_pull  = float(np.max(np.abs(pulls_arr)))

        statuses = [r["datum_status"] for r in per_datum]
        n_1s = sum(1 for s in statuses if s == "PASS_1SIGMA")
        n_2s = sum(1 for s in statuses if s in ("PASS_1SIGMA", "PASS_2SIGMA"))
        n_3s = sum(1 for s in statuses if s in ("PASS_1SIGMA", "PASS_2SIGMA", "PASS_3SIGMA"))
        n_out = dof - n_3s

        # --- Write per-datum CSV -------------------------------------------
        _write_per_datum_csv(run_folder / PER_DATUM_CSV_FILENAME, per_datum)

        # --- Enrich summary ------------------------------------------------
        summary = _read_json(summary_path)
        summary.setdefault("results", {})["rsd_validator"] = {
            "status":                        "OK",
            "script":                        script_identity(),
            "dataset_label":                 DATASET_LABEL,
            "datum_count":                   dof,
            "sigma8_reference":              SIGMA8_REFERENCE,
            "sigma8_X":                      sigma8_X,
            "growth_ratio_D_X_over_D_LCDM":  growth_ratio,
            "chi2":                          chi2,
            "dof":                           dof,
            "reduced_chi2":                  chi2 / dof,
            "max_abs_pull":                  max_pull,
            "n_within_1sigma":               n_1s,
            "n_within_2sigma":               n_2s,
            "n_within_3sigma":               n_3s,
            "n_outside_3sigma":              n_out,
            "rsd_results_per_datum_csv":     PER_DATUM_CSV_FILENAME,
            "rsd_pulls_plot":                f"{PULLS_PLOT_STEM}.png",
            "rsd_growth_plot":               f"{GROWTH_PLOT_STEM}.png",
            "growth_z_start":                GROWTH_Z_START,
            "ode_solver":                    "DOP853",
            "normalization_check":           "PASS",
        }
        _atomic_write_json(summary_path, summary)

        # --- Plots ---------------------------------------------------------
        summary_for_plot = _read_json(summary_path)
        _save_pull_plot(per_datum, summary_for_plot, run_folder)
        _save_growth_plot(per_datum, sol_X, sol_LCDM, summary_for_plot, run_folder)

        desc = (
            f"rsd_validator complete: "
            f"chi2={chi2:.4f} reduced={chi2/dof:.4f} "
            f"[{n_2s}/{dof} within 2σ]  "
            f"sigma8_X={sigma8_X:.4f}  growth_ratio={growth_ratio:.6f}"
        )
        return ("OK", desc)

    except Exception as exc:
        return ("Error", f"{type(exc).__name__}: {exc}")
