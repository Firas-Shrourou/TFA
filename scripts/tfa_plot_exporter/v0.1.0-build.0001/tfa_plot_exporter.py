"""
tfa_plot_exporter.py — diagnostic plot exporter for TFA run folders.

Reads completed run-folder outputs and produces 5 diagnostic plots
as .png + .pdf pairs. Does not re-integrate or recompute any physics.

Always-available (trajectory.csv always written):
  w_of_z.png/pdf       — equation of state w_phi(z)
  Omega_phi.png/pdf    — scalar-field energy density Omega_phi(z)
  phase_portrait.png/pdf — phi vs dphi/dN trajectory colored by N

Gated (only when export gate accepted, i.e. expansion_history_h0x_normalized.csv exists):
  H_of_z.png/pdf       — H_X(z) vs LCDM reference
  delta_H.png/pdf      — fractional Hubble deviation (H_X - H_LCDM)/H_LCDM

Entry point: run_plot_exporter(run_folder) -> (Code, Desc)
Enriches run_results_summary.json under results["plot_exporter"].
"""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection


TFA_PROJECT_RELEASE = "0.0.2"
SCRIPT_NAME = "tfa_plot_exporter"
SCRIPT_VERSION = "0.1.0"
SCRIPT_BUILD = "0001"
SCRIPT_API_VERSION = "0.1"

SUMMARY_FILENAME = "run_results_summary.json"
FROZEN_SETTINGS_FILENAME = "environment-settings.json"
TRAJECTORY_FILENAME = "trajectory.csv"
HISTORY_NORMALIZED_FILENAME = "expansion_history_h0x_normalized.csv"

BAND_COLORS: dict[str, str] = {
    "STRICT":   "#2ca02c",
    "LOOSE_2S": "#ff7f0e",
    "LOOSE_3S": "#9467bd",
    "EXCLUDED": "#d62728",
}

_BAND_LABELS: dict[str, str] = {
    "STRICT": "1σ", "LOOSE_2S": "2σ", "LOOSE_3S": "3σ", "EXCLUDED": "EXC",
}

# Recombination EDE bound (plotted as reference line on Omega_phi)
_REC_BOUND = 0.061


def script_identity() -> dict[str, str]:
    return {
        "tfa_project_release": TFA_PROJECT_RELEASE,
        "script_name": SCRIPT_NAME,
        "script_version": SCRIPT_VERSION,
        "script_build": SCRIPT_BUILD,
        "script_api_version": SCRIPT_API_VERSION,
    }


def band_label(status: str) -> str:
    return _BAND_LABELS.get(status, status)


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


def _read_trajectory(path: Path) -> dict[str, np.ndarray]:
    """Read all columns of trajectory.csv into a dict of float arrays.

    Trajectory rows are in ODE order: N increasing from most-negative (z~z_ini)
    to 0 (z=0). So traj[col][-1] is the z=0 value.
    """
    cols: dict[str, list[float]] = {}
    with path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        headers = [h.strip() for h in next(reader)]
        for h in headers:
            cols[h] = []
        for row in reader:
            if not row:
                continue
            for h, val in zip(headers, row):
                cols[h].append(float(val))
    return {h: np.asarray(v, dtype=float) for h, v in cols.items()}


def _read_csv_with_comments(path: Path) -> tuple[dict[str, str], dict[str, np.ndarray]]:
    """Read a TFA CSV with leading # comment rows.

    Returns (meta, data_cols) where meta maps comment keys to string values
    and data_cols maps column headers to float arrays.
    """
    meta: dict[str, str] = {}
    headers: list[str] = []
    cols: dict[str, list[float]] = {}
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
                for h in headers:
                    cols[h] = []
            else:
                for h, val in zip(headers, row):
                    cols[h].append(float(val))
    return meta, {h: np.asarray(v, dtype=float) for h, v in cols.items()}


def _get_cosmology(settings: dict) -> dict[str, float]:
    """Extract LCDM reference cosmology from frozen environment-settings.json."""
    cosmo = settings.get("user_adjustable", {}).get("cosmology", {})
    Om = float(cosmo["Omega_m0"])
    Or = float(cosmo["Omega_r0"])
    ode_raw = cosmo.get("Omega_DE")
    ODE = float(ode_raw) if ode_raw is not None else (1.0 - Om - Or)
    H0_ref = float(cosmo["H0_ref_kms"])
    return {"Omega_m0": Om, "Omega_r0": Or, "Omega_DE": ODE, "H0_ref": H0_ref}


def _lcdm_H(z_arr: np.ndarray, cosmo: dict[str, float]) -> np.ndarray:
    z = np.asarray(z_arr, dtype=float)
    H0 = cosmo["H0_ref"]
    Om = cosmo["Omega_m0"]
    Or = cosmo["Omega_r0"]
    ODE = cosmo["Omega_DE"]
    return H0 * np.sqrt(Om * (1.0 + z)**3 + Or * (1.0 + z)**4 + ODE)


def _save(fig: Any, outdir: Path, stem: str) -> None:
    for ext in ("png", "pdf"):
        fig.savefig(str(outdir / f"{stem}.{ext}"), dpi=150, bbox_inches="tight")
    plt.close(fig)


def _infobox() -> dict:
    return dict(boxstyle="round,pad=0.3", fc="white", ec="#ccc", alpha=0.9)


# ---------------------------------------------------------------------------
# Individual plot functions
# ---------------------------------------------------------------------------

def _plot_w_of_z(traj: dict, summary: dict, outdir: Path) -> str:
    av = summary.get("results", {}).get("acoustic_validator", {})
    bid = summary.get("contract", {}).get("benchmark_id", "")
    band = str(av.get("band", ""))
    H0X = float(av.get("H0_X_kms", float("nan")))

    # Sort z ascending for a left-to-right plot
    mask = traj["z"] <= 2.5
    z_p = traj["z"][mask]
    w_p = traj["w_phi"][mask]
    idx = np.argsort(z_p)
    z_p, w_p = z_p[idx], w_p[idx]

    # w0 is at z=0 (minimum z in trajectory)
    w0 = float(traj["w_phi"][np.argmin(traj["z"])])

    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.plot(z_p, w_p, "#1f77b4", lw=2.2, label=r"$w_\phi(z)$")
    ax.axhline(-1.0, color="#888", lw=1.0, ls=":",
               label=r"$w = -1$ ($\Lambda$CDM)")
    ax.fill_between(z_p, -1.0, w_p, alpha=0.08, color="#1f77b4")
    ax.set_xlim(0.0, 2.5)
    ax.set_xlabel(r"$z$")
    ax.set_ylabel(r"$w_\phi$")
    ax.set_title(f"{bid}  —  equation of state $w_\\phi(z)$")
    ax.text(
        0.97, 0.05,
        f"$w_0 = {w0:.4f}$\n$H_{{0,X}} = {H0X:.2f}$ [{band_label(band)}]",
        transform=ax.transAxes, ha="right", va="bottom", fontsize=8,
        bbox=_infobox(),
    )
    ax.legend(fontsize=8, loc="upper right")
    ax.grid(True, lw=0.4, alpha=0.5)
    fig.tight_layout()
    _save(fig, outdir, "w_of_z")
    return "w_of_z"


def _plot_Omega_phi(traj: dict, summary: dict, outdir: Path) -> str:
    av = summary.get("results", {}).get("acoustic_validator", {})
    bid = summary.get("contract", {}).get("benchmark_id", "")
    anc = av.get("acoustic_anchor", {})
    z_star = float(anc.get("z_star", 1090.0))

    mask = traj["z"] <= 1200.0
    z_p = traj["z"][mask]
    Op = traj["Omega_phi"][mask]
    idx = np.argsort(z_p)
    z_p, Op = z_p[idx], Op[idx]
    Op = np.maximum(Op, 1e-12)

    Op0 = float(traj["Omega_phi"][np.argmin(traj["z"])])

    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.semilogy(z_p, Op, "#1f77b4", lw=2.0, label=r"$\Omega_\phi(z)$")
    ax.axhline(
        _REC_BOUND, color="#d62728", lw=1.2, ls="--",
        label=f"$\\Omega_\\phi < {_REC_BOUND}$ (recombination bound)",
    )
    ax.axvline(
        z_star, color="#888", lw=0.8, ls=":",
        label=f"$z_* = {z_star:.1f}$",
    )
    ax.set_xlim(0.0, 1200.0)
    ax.set_ylim(1e-12, 1.2)
    ax.set_xlabel(r"$z$")
    ax.set_ylabel(r"$\Omega_\phi(z)$")
    ax.set_title(f"{bid}  —  scalar-field energy density $\\Omega_\\phi(z)$")
    ax.text(
        0.97, 0.97,
        f"$\\Omega_\\phi(0) = {Op0:.5f}$",
        transform=ax.transAxes, ha="right", va="top", fontsize=8,
        bbox=_infobox(),
    )
    ax.legend(fontsize=8)
    fig.tight_layout()
    _save(fig, outdir, "Omega_phi")
    return "Omega_phi"


def _plot_phase_portrait(traj: dict, summary: dict, outdir: Path) -> str:
    bid = summary.get("contract", {}).get("benchmark_id", "")
    phi = traj["phi"]
    dphi = traj["dphi_dN"]
    N = traj["N"]

    points = np.array([phi, dphi]).T.reshape(-1, 1, 2)
    segs = np.concatenate([points[:-1], points[1:]], axis=1)
    norm = plt.Normalize(float(N.min()), float(N.max()))
    lc = LineCollection(segs, cmap="plasma", norm=norm, lw=1.5)
    lc.set_array(N[:-1])

    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.add_collection(lc)
    ax.autoscale()
    plt.colorbar(lc, ax=ax, label=r"$N = \ln a$")
    ax.set_xlabel(r"$\varphi\,/\,M_{\rm P}$")
    ax.set_ylabel(r"$\mathrm{d}\varphi/\mathrm{d}N$")
    ax.set_title(
        f"{bid}  —  "
        r"phase portrait $\varphi$ vs $\mathrm{d}\varphi/\mathrm{d}N$"
    )
    fig.tight_layout()
    _save(fig, outdir, "phase_portrait")
    return "phase_portrait"


def _plot_H_of_z(
    hist_meta: dict[str, str],
    hist_data: dict[str, np.ndarray],
    summary: dict,
    cosmo: dict[str, float],
    outdir: Path,
) -> str:
    av = summary.get("results", {}).get("acoustic_validator", {})
    bid = summary.get("contract", {}).get("benchmark_id", "")
    H0X = float(av.get("H0_X_kms", float("nan")))
    band = str(av.get("band", ""))
    Om_X = float(av.get("Omega_m_X", float("nan")))
    norm_res_str = hist_meta.get("normalization_residual", "nan")
    try:
        norm_res = float(norm_res_str)
    except ValueError:
        norm_res = float("nan")

    mask = hist_data["z"] <= 2.5
    z_p = hist_data["z"][mask]
    H_X = hist_data["H_X"][mask]
    H_lam = _lcdm_H(z_p, cosmo)

    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.plot(z_p, H_X, "#1f77b4", lw=2.2, label=r"$H_X(z)$ (H0X-normalized)")
    ax.plot(z_p, H_lam, "#888", lw=1.5, ls="--", label=r"$\Lambda$CDM reference")
    ax.fill_between(z_p, H_lam, H_X, alpha=0.10, color="#1f77b4")
    ax.set_xlim(0.0, 2.5)
    ax.set_xlabel(r"$z$")
    ax.set_ylabel(r"$H(z)$ (km s$^{-1}$ Mpc$^{-1}$)")
    ax.set_title(f"{bid}  —  expansion history $H_X(z)$")
    ax.text(
        0.03, 0.97,
        f"$H_{{0,X}} = {H0X:.2f}$ km s$^{{-1}}$ Mpc$^{{-1}}$  [{band_label(band)}]\n"
        f"$\\Omega_m^X = {Om_X:.4f}$\n"
        f"$\\epsilon_{{H0}} = {norm_res:.1e}$",
        transform=ax.transAxes, ha="left", va="top", fontsize=8,
        bbox=_infobox(),
    )
    ax.legend(fontsize=8)
    ax.grid(True, lw=0.4, alpha=0.5)
    fig.tight_layout()
    _save(fig, outdir, "H_of_z")
    return "H_of_z"


def _plot_delta_H(
    hist_data: dict[str, np.ndarray],
    summary: dict,
    cosmo: dict[str, float],
    w0: float,
    outdir: Path,
) -> str:
    av = summary.get("results", {}).get("acoustic_validator", {})
    bid = summary.get("contract", {}).get("benchmark_id", "")
    H0X = float(av.get("H0_X_kms", float("nan")))
    band = str(av.get("band", ""))

    mask = hist_data["z"] <= 2.5
    z_p = hist_data["z"][mask]
    H_X = hist_data["H_X"][mask]
    H_lam = _lcdm_H(z_p, cosmo)
    dH = 100.0 * (H_X - H_lam) / H_lam

    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.plot(z_p, dH, "#1f77b4", lw=2.2)
    ax.fill_between(z_p, 0.0, dH, alpha=0.12, color="#1f77b4")
    ax.axhline(0.0, color="#888", lw=0.8, ls=":")
    ax.set_xlim(0.0, 2.5)
    ax.set_xlabel(r"$z$")
    ax.set_ylabel(r"$\Delta H_X / H_\Lambda$ (%)")
    ax.set_title(
        f"{bid}  —  "
        r"fractional Hubble deviation $\Delta H_X / H_\Lambda$"
    )
    ax.text(
        0.97, 0.97,
        f"$w_0 = {w0:.4f}$\n$H_{{0,X}} = {H0X:.2f}$ [{band_label(band)}]",
        transform=ax.transAxes, ha="right", va="top", fontsize=8,
        bbox=_infobox(),
    )
    ax.grid(True, lw=0.4, alpha=0.5)
    fig.tight_layout()
    _save(fig, outdir, "delta_H")
    return "delta_H"


# ---------------------------------------------------------------------------
# File-based entry point
# ---------------------------------------------------------------------------

def run_plot_exporter(run_folder: str | Path) -> tuple[str, str]:
    """File-based plot entry point. Returns (Code, Desc).

    Reads trajectory.csv, expansion_history_h0x_normalized.csv (if present),
    run_results_summary.json, and environment-settings.json from run_folder.
    Writes plot files to run_folder and enriches the summary under
    results["plot_exporter"].
    """
    try:
        run_folder = Path(run_folder)
        summary_path = run_folder / SUMMARY_FILENAME
        settings_path = run_folder / FROZEN_SETTINGS_FILENAME
        traj_path = run_folder / TRAJECTORY_FILENAME
        hist_path = run_folder / HISTORY_NORMALIZED_FILENAME

        if not summary_path.exists():
            return ("Error", f"{SUMMARY_FILENAME} not found in {run_folder}")
        if not settings_path.exists():
            return ("Error", f"{FROZEN_SETTINGS_FILENAME} not found in {run_folder}")
        if not traj_path.exists():
            return ("Error", f"{TRAJECTORY_FILENAME} not found; run acoustic_validator first")

        summary = _read_json(summary_path)
        settings = _read_json(settings_path)
        cosmo = _get_cosmology(settings)
        traj = _read_trajectory(traj_path)

        plots_written: list[str] = []
        plots_skipped: list[str] = []

        # Always-available plots
        plots_written.append(_plot_w_of_z(traj, summary, run_folder))
        plots_written.append(_plot_Omega_phi(traj, summary, run_folder))
        plots_written.append(_plot_phase_portrait(traj, summary, run_folder))

        # Gated plots
        if hist_path.exists():
            hist_meta, hist_data = _read_csv_with_comments(hist_path)
            w0 = float(traj["w_phi"][np.argmin(traj["z"])])
            plots_written.append(
                _plot_H_of_z(hist_meta, hist_data, summary, cosmo, run_folder)
            )
            plots_written.append(
                _plot_delta_H(hist_data, summary, cosmo, w0, run_folder)
            )
        else:
            plots_skipped.extend(["H_of_z", "delta_H"])

        # Enrich summary
        plot_files = [f"{s}.png" for s in plots_written] + [f"{s}.pdf" for s in plots_written]
        summary = _read_json(summary_path)
        summary.setdefault("results", {})["plot_exporter"] = {
            "status": "OK",
            "script": script_identity(),
            "plots_written": sorted(plot_files),
            "plots_skipped": plots_skipped,
            "plot_count": len(plots_written),
        }
        _atomic_write_json(summary_path, summary)

        n = len(plots_written)
        skipped_note = f", {len(plots_skipped)} skipped (export gate)" if plots_skipped else ""
        return ("OK", f"plot_exporter complete: {n} plots written{skipped_note}")

    except Exception as exc:
        return ("Error", f"{type(exc).__name__}: {exc}")
