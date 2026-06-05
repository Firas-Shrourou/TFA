"""
Standalone TFA physics guard validator.

This script evaluates the FEU v4.0 physics guard logic as reusable TFA
endpoints:

- ``canonical_ok``
- ``canonical_thawing_ok``
- ``BBN_OK``
- ``phantom_crossing_ok``

It does not import ``tfa_common.py``. It imports ``tfa_acoustic_validator.py``
for the shared ``PotentialRoute`` contract, environment settings, ODE
integration, trace handling, and graceful error handling.
"""

from __future__ import annotations

import csv
import json
import os
import sys
import traceback
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np


_THIS_DIR = Path(__file__).resolve().parent
_PACKAGE_VALIDATOR_CANDIDATES = (
    _THIS_DIR.parent.parent / "tfa_acoustic_validator" / "v0.1.3-build.0001",
    _THIS_DIR.parent.parent.parent / "tfa_acoustic_validator" / "v0.1.3-build.0001",
)
for _candidate in (_THIS_DIR, *_PACKAGE_VALIDATOR_CANDIDATES):
    if _candidate.exists():
        candidate_text = str(_candidate)
        if candidate_text not in sys.path:
            sys.path.insert(0, candidate_text)

import tfa_acoustic_validator as acoustic_validator


ArrayLike = Sequence[float] | np.ndarray
PotentialRoute = acoustic_validator.PotentialRoute
def _unified_settings_path() -> Path:
    """Resolve the single package-level ``tfa-environment-settings.json``.

    TFA design rule: no script carries a local settings file. Every script reads
    the one unified file at the TFA-package root, located by walking up from this
    file until it is found.
    """

    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "tfa-environment-settings.json"
        if candidate.exists():
            return candidate
    return here.parents[3] / "tfa-environment-settings.json"


DEFAULT_ENVIRONMENT_SETTINGS = _unified_settings_path()

TFA_PROJECT_RELEASE = "0.0.2"
SCRIPT_NAME = "tfa_physics_guard_validator"
SCRIPT_VERSION = "0.1.4"
SCRIPT_BUILD = "0001"
SCRIPT_API_VERSION = "0.1"
SETTINGS_SCHEMA_VERSION = "0.1"


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


def physics_guard_settings_from_settings(settings: Mapping[str, object]) -> Mapping[str, float]:
    """Return physics guard thresholds from the environment settings JSON."""

    user = acoustic_validator.user_adjustable_settings(settings)
    section = acoustic_validator._require_mapping(user, "physics_guards")
    return {
        "canonical_w_floor": float(section["canonical_w_floor"]),
        "canonical_tolerance": float(section["canonical_tolerance"]),
        "thawing_late_z_max": float(section["thawing_late_z_max"]),
        "thawing_monotonic_tolerance": float(section["thawing_monotonic_tolerance"]),
        "phantom_crossing_tolerance": float(section["phantom_crossing_tolerance"]),
        "bbn_z": float(section["bbn_z"]),
        "bbn_omega_phi_bound": float(section["bbn_omega_phi_bound"]),
    }


def load_guard_environment(settings_path: str | Path | None = None) -> Mapping[str, object]:
    """Load shared validator environment plus physics guard thresholds."""

    resolved = DEFAULT_ENVIRONMENT_SETTINGS if settings_path is None else Path(settings_path)
    settings = acoustic_validator.load_environment_settings(resolved)
    validator_env = acoustic_validator.runtime_environment_from_settings(resolved)
    return {
        **validator_env,
        "settings_path": resolved,
        "physics_guard_settings": physics_guard_settings_from_settings(settings),
    }


def _as_float_array(name: str, values: ArrayLike) -> np.ndarray:
    """Convert input to a finite float array."""

    arr = np.asarray(values, dtype=float)
    if arr.ndim != 1:
        raise ValueError(f"{name} must be a one-dimensional array")
    if np.any(~np.isfinite(arr)):
        raise ValueError(f"{name} must contain only finite values")
    return arr


def canonical_ok_from_w(
    w_phi: ArrayLike,
    w_floor: float = -1.0,
    tolerance: float = 1e-8,
) -> Mapping[str, object]:
    """Check the FEU canonical guard: all ``w_phi >= w_floor - tolerance``."""

    w = _as_float_array("w_phi", w_phi)
    minimum = float(np.min(w)) if len(w) else float("nan")
    ok = bool(len(w) > 0 and np.all(w >= w_floor - tolerance))
    return {
        "canonical_ok": ok,
        "minimum_w_phi": minimum,
        "w_floor": w_floor,
        "tolerance": tolerance,
    }


def phantom_crossing_ok_from_w(
    w_phi: ArrayLike,
    w_floor: float = -1.0,
    tolerance: float = 1e-8,
) -> Mapping[str, object]:
    """Check that the history does not cross into the phantom region."""

    check = canonical_ok_from_w(w_phi, w_floor, tolerance)
    return {
        "phantom_crossing_ok": bool(check["canonical_ok"]),
        "minimum_w_phi": check["minimum_w_phi"],
        "w_floor": w_floor,
        "tolerance": tolerance,
    }


def canonical_thawing_ok_from_history(
    z: ArrayLike,
    w_phi: ArrayLike,
    late_z_max: float = 5.0,
    tolerance: float = 1e-8,
) -> Mapping[str, object]:
    """Check FEU thawing monotonicity on the late-time ``z <= late_z_max`` slice."""

    z_arr = _as_float_array("z", z)
    w = _as_float_array("w_phi", w_phi)
    if z_arr.shape != w.shape:
        raise ValueError("z and w_phi must have the same shape")
    mask = z_arr <= late_z_max
    late_w = w[mask]
    if len(late_w) < 2:
        ok = bool(len(late_w) == 1)
        min_delta = None
    else:
        deltas = np.diff(late_w)
        min_delta = float(np.min(deltas))
        ok = bool(np.all(deltas >= -tolerance))
    return {
        "canonical_thawing_ok": ok,
        "late_z_max": late_z_max,
        "tolerance": tolerance,
        "late_sample_count": int(len(late_w)),
        "minimum_delta_w": min_delta,
    }


def bbn_ok_from_omega_phi(
    Omega_phi_bbn: float,
    bound: float = 0.045,
) -> Mapping[str, object]:
    """Check FEU BBN guard: ``Omega_phi_BBN < bound``."""

    value = float(Omega_phi_bbn)
    if not np.isfinite(value):
        raise ValueError("Omega_phi_bbn must be finite")
    return {
        "BBN_OK": bool(value < bound),
        "Omega_phi_BBN": value,
        "bbn_omega_phi_bound": bound,
    }


def _evaluate_w_omega_at_z(
    route: PotentialRoute,
    cosmology: acoustic_validator.CosmologyContext,
    sol: object,
    z_grid: ArrayLike,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Evaluate z, w_phi, and Omega_phi on a redshift grid."""

    z = _as_float_array("z_grid", z_grid)
    if np.any(z < 0.0):
        raise ValueError("z_grid must be non-negative")
    N = -np.log1p(z)
    y = sol.sol(N)
    phi, phi_N, H2, _raw_E = acoustic_validator._eval_route_state(route, cosmology, N, y)
    V = np.asarray(route.V(phi), dtype=float)
    kinetic = 0.5 * H2 * phi_N**2
    w_phi = (kinetic - V) / (kinetic + V)
    Omega_phi = (kinetic + V) / (3.0 * H2)
    return z, w_phi, Omega_phi


def bbn_omega_phi_frozen(
    route: PotentialRoute,
    cosmology: acoustic_validator.CosmologyContext,
    bbn_z: float,
) -> float:
    """Scalar density fraction at BBN, in the frozen-field limit.

    A thawing field is frozen deep in the radiation era (z >> z_star): the
    Hubble-friction term dominates, so ``phi = initial_phi`` and
    ``phi_N = initial_phi_N (~ 0)``. Its BBN density is therefore fixed by the
    potential at the frozen field value, evaluated against the analytic
    radiation+matter Friedmann background:

        Omega_phi(z_bbn) = (K + V(phi_i)) / (3 H^2),   K = 0.5 H^2 phi_Ni^2.

    This is exact in the frozen regime and does NOT evaluate the dense ODE
    solution. The previous implementation called ``sol.sol`` at ``bbn_z``
    (default 1e9), which lies outside the integrated interval ``[0, z_ini]``
    (default z_ini = 1e6); that extrapolation fabricated a spurious kinetic
    term and reported an ``Omega_phi_BBN`` ~28 orders of magnitude too large.
    """

    if bbn_z <= 0.0 or not np.isfinite(bbn_z):
        raise ValueError("bbn_z must be positive and finite")
    a = 1.0 / (1.0 + bbn_z)
    phi = float(route.initial_phi)
    phi_N = float(route.initial_phi_N)
    V = float(np.asarray(route.V(np.asarray([phi], dtype=float)), dtype=float)[0])
    denom = 3.0 - 0.5 * phi_N**2
    if denom <= 0.0:
        raise RuntimeError("phi_N^2 >= 6: kinetic energy exceeds canonical bound")
    H2 = (
        3.0 * cosmology.Omega_m0 * a**-3
        + 3.0 * cosmology.Omega_r0 * a**-4
        + V
    ) / denom
    kinetic = 0.5 * H2 * phi_N**2
    return float((kinetic + V) / (3.0 * H2))


def validate_physics_guards_from_history(
    z: ArrayLike,
    w_phi: ArrayLike,
    Omega_phi_bbn: float | None = None,
    settings_path: str | Path | None = None,
) -> Mapping[str, object]:
    """Validate guards from supplied arrays and optional BBN scalar fraction."""

    env = load_guard_environment(settings_path)
    settings = env["physics_guard_settings"]
    canonical = canonical_ok_from_w(
        w_phi,
        settings["canonical_w_floor"],
        settings["canonical_tolerance"],
    )
    thawing = canonical_thawing_ok_from_history(
        z,
        w_phi,
        settings["thawing_late_z_max"],
        settings["thawing_monotonic_tolerance"],
    )
    phantom = phantom_crossing_ok_from_w(
        w_phi,
        settings["canonical_w_floor"],
        settings["phantom_crossing_tolerance"],
    )
    bbn = None
    if Omega_phi_bbn is not None:
        bbn = bbn_ok_from_omega_phi(Omega_phi_bbn, settings["bbn_omega_phi_bound"])
    return {
        "ok": True,
        "payload": {
            **canonical,
            **thawing,
            **phantom,
            **({} if bbn is None else bbn),
            "script": script_identity(),
        },
    }


def validate_physics_guards_from_route(
    route: PotentialRoute,
    settings_path: str | Path | None = None,
    redshift_grid: ArrayLike | None = None,
) -> Mapping[str, object]:
    """Integrate a route and validate canonical, thawing, phantom, and BBN guards."""

    env = load_guard_environment(settings_path)
    execution = env["execution_settings"]
    settings = env["physics_guard_settings"]
    trace = acoustic_validator.RunTrace(
        route_id=route.benchmark_id,
        enabled=bool(execution["trace_enabled"]),
        debug_print=bool(execution["debug_print"]),
        trace_dir=execution["trace_dir"],
        filename_prefix=f"{execution['trace_filename_prefix']}-physics-guard-validator",
    )
    try:
        cosmology = acoustic_validator._run_phase(trace, "environment", lambda: env["cosmology"])
        integration_config = acoustic_validator._run_phase(
            trace,
            "environment",
            lambda: env["integration_config"],
        )
        sol = acoustic_validator._run_phase(
            trace,
            "ode_integration",
            lambda: acoustic_validator.integrate_scalar_route(route, cosmology, integration_config),
        )
        if redshift_grid is None:
            redshift_grid = np.exp(-sol.t) - 1.0
        z, w_phi, _Omega_phi = acoustic_validator._run_phase(
            trace,
            "guard_history",
            lambda: _evaluate_w_omega_at_z(route, cosmology, sol, redshift_grid),
        )
        omega_bbn = acoustic_validator._run_phase(
            trace,
            "bbn_guard",
            lambda: bbn_omega_phi_frozen(route, cosmology, settings["bbn_z"]),
        )
        result = validate_physics_guards_from_history(
            z,
            w_phi,
            omega_bbn,
            settings_path=env["settings_path"],
        )
        trace.close("PASS", "TFA physics guard validator completed")
        payload = dict(result["payload"])
        payload["benchmark_id"] = route.benchmark_id
        payload["bbn_z"] = settings["bbn_z"]
        payload["trace_path"] = str(trace.trace_path) if trace.trace_path is not None else None
        return {"ok": True, "payload": payload}
    except BaseException as exc:
        err = exc if isinstance(exc, acoustic_validator.TFAError) else acoustic_validator._phase_error("unknown", exc)
        if trace.trace_path is not None:
            err.trace_path = str(trace.trace_path)
        trace.close("ERROR", err.message)
        raise err from exc


def validate_physics_guards_from_route_safe(
    route: PotentialRoute,
    settings_path: str | Path | None = None,
    redshift_grid: ArrayLike | None = None,
) -> Mapping[str, object]:
    """Safe wrapper returning structured error dictionaries."""

    try:
        return validate_physics_guards_from_route(route, settings_path, redshift_grid)
    except acoustic_validator.TFAError as exc:
        return {
            "ok": False,
            "error": exc.to_dict(),
            "traceback": traceback.format_exc(),
            "script": script_identity(),
        }
    except BaseException as exc:
        err = acoustic_validator._phase_error("unknown", exc)
        return {
            "ok": False,
            "error": err.to_dict(),
            "traceback": traceback.format_exc(),
            "script": script_identity(),
        }


# ===========================================================================
# File-based run-folder layer (added in 0.1.3)
#
# The hub invokes this AFTER the engine (tfa_acoustic_validator) has written
# trajectory.csv. The guard depends only on the engine's output + the contract;
# it does NOT depend on the normalized-history generator, so it runs before it.
# It reads z/w_phi from trajectory.csv, rebuilds the potential only to evaluate
# the frozen-field BBN density, runs the four guard checks, writes its own
# physics_guards.csv, enriches run_results_summary.json under
# results["physics_guard_validator"], and returns (Code, Desc).
# ===========================================================================

SUMMARY_FILENAME = "run_results_summary.json"
FROZEN_SETTINGS_FILENAME = "environment-settings.json"
TRAJECTORY_FILENAME = "trajectory.csv"
GUARDS_CSV_FILENAME = "physics_guards.csv"


def _read_json(path: str | Path) -> dict:
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)


def _atomic_write_json(path: str | Path, obj: object) -> None:
    """Write JSON atomically (temp + fsync + rename) to avoid the hold-release gap."""

    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, sort_keys=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _read_trajectory_zw(path: str | Path) -> tuple[np.ndarray, np.ndarray]:
    """Read the z and w_phi columns from the engine's trajectory.csv."""

    z_vals: list[float] = []
    w_vals: list[float] = []
    with Path(path).open("r", newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        idx_z = header.index("z")
        idx_w = header.index("w_phi")
        for row in reader:
            if not row:
                continue
            z_vals.append(float(row[idx_z]))
            w_vals.append(float(row[idx_w]))
    return np.asarray(z_vals, dtype=float), np.asarray(w_vals, dtype=float)


def _fmt_guard_value(value: object) -> str:
    if isinstance(value, bool):
        return "True" if value else "False"
    if value is None:
        return ""
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return f"{value:.12g}"
    return str(value)


def _guard_rows(payload: Mapping[str, object], g: Mapping[str, object]) -> list[tuple]:
    rows = [
        ("canonical", "canonical_ok", payload.get("canonical_ok"), "verdict"),
        ("canonical", "minimum_w_phi", payload.get("minimum_w_phi"), "diagnostic"),
        ("canonical", "canonical_w_floor", g.get("canonical_w_floor"), "threshold"),
        ("canonical", "canonical_tolerance", g.get("canonical_tolerance"), "threshold"),
        ("thawing", "canonical_thawing_ok", payload.get("canonical_thawing_ok"), "verdict"),
        ("thawing", "minimum_delta_w", payload.get("minimum_delta_w"), "diagnostic"),
        ("thawing", "late_sample_count", payload.get("late_sample_count"), "diagnostic"),
        ("thawing", "thawing_late_z_max", g.get("thawing_late_z_max"), "threshold"),
        ("thawing", "thawing_monotonic_tolerance", g.get("thawing_monotonic_tolerance"), "threshold"),
        ("phantom", "phantom_crossing_ok", payload.get("phantom_crossing_ok"), "verdict"),
        ("phantom", "minimum_w_phi", payload.get("minimum_w_phi"), "diagnostic"),
        ("phantom", "canonical_w_floor", g.get("canonical_w_floor"), "threshold"),
        ("phantom", "phantom_crossing_tolerance", g.get("phantom_crossing_tolerance"), "threshold"),
    ]
    if "BBN_OK" in payload:
        rows += [
            ("bbn", "BBN_OK", payload.get("BBN_OK"), "verdict"),
            ("bbn", "Omega_phi_BBN", payload.get("Omega_phi_BBN"), "diagnostic"),
            ("bbn", "bbn_omega_phi_bound", g.get("bbn_omega_phi_bound"), "threshold"),
            ("bbn", "bbn_z", g.get("bbn_z"), "threshold"),
        ]
    return rows


def _write_guards_csv(
    path: str | Path,
    payload: Mapping[str, object],
    guard_settings: Mapping[str, object],
    benchmark_id: str,
    overall_pass: bool,
) -> int:
    rows = _guard_rows(payload, guard_settings)
    with Path(path).open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["# product", "physics_guards"])
        writer.writerow(["# benchmark_id", benchmark_id])
        writer.writerow(["# overall_pass", "True" if overall_pass else "False"])
        writer.writerow(["# guard_script", f"{SCRIPT_NAME} {SCRIPT_VERSION} build {SCRIPT_BUILD}"])
        writer.writerow(["guard", "field", "value", "category"])
        for guard, field, value, category in rows:
            writer.writerow([guard, field, _fmt_guard_value(value), category])
    return len(rows)


def run_physics_guard_validator(run_folder: str | Path) -> tuple[str, str]:
    """File-based guard entry point. Returns ``(Code, Desc)``.

    Reads z/w_phi from ``trajectory.csv`` and the contract from
    ``run_results_summary.json``, computes the frozen-field BBN density, runs the
    canonical / thawing / phantom / BBN guards, writes ``physics_guards.csv``,
    and enriches the summary under ``results["physics_guard_validator"]``.
    Depends only on the engine output, never on the normalized history.
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
        if not traj_path.exists():
            return ("Error", f"{TRAJECTORY_FILENAME} not found; run acoustic_validator first")

        summary = _read_json(summary_path)
        contract = summary.get("contract")
        if not isinstance(contract, Mapping):
            return ("Error", "run_results_summary.json has no contract section")

        settings = acoustic_validator.load_environment_settings(settings_path)
        guard_settings = physics_guard_settings_from_settings(settings)
        cosmology = acoustic_validator.cosmology_from_settings(settings)

        # z, w_phi come straight off the engine's trajectory (no re-integration).
        z, w_phi = _read_trajectory_zw(traj_path)

        # Frozen-field BBN density needs V(phi_i): rebuild from frozen settings.
        V, dV_dphi = acoustic_validator.build_potential_from_settings(settings, cosmology)
        potential_spec = acoustic_validator.potential_from_settings(settings)
        benchmark_id = str(
            potential_spec.get("benchmark_id")
            or contract.get("benchmark_id")
            or "unnamed"
        )
        route = acoustic_validator.PotentialRoute(
            benchmark_id=benchmark_id,
            V=V,
            dV_dphi=dV_dphi,
            initial_phi=float(potential_spec["initial_phi"]),
            initial_phi_N=float(potential_spec.get("initial_phi_N", 0.0)),
        )
        omega_bbn = bbn_omega_phi_frozen(route, cosmology, guard_settings["bbn_z"])

        # Run the four guards through the array endpoint.
        result = validate_physics_guards_from_history(z, w_phi, omega_bbn, settings_path=settings_path)
        payload = dict(result["payload"])

        overall_pass = bool(
            payload.get("canonical_ok")
            and payload.get("canonical_thawing_ok")
            and payload.get("phantom_crossing_ok")
            and payload.get("BBN_OK")
        )

        rows = _write_guards_csv(
            run_folder / GUARDS_CSV_FILENAME, payload, guard_settings, route.benchmark_id, overall_pass
        )

        summary = _read_json(summary_path)
        results = summary.setdefault("results", {})
        results["physics_guard_validator"] = {
            "status": "OK",
            "script": script_identity(),
            "overall_pass": overall_pass,
            "verdicts": {
                "canonical_ok": payload.get("canonical_ok"),
                "canonical_thawing_ok": payload.get("canonical_thawing_ok"),
                "phantom_crossing_ok": payload.get("phantom_crossing_ok"),
                "BBN_OK": payload.get("BBN_OK"),
            },
            "diagnostics": {
                "minimum_w_phi": payload.get("minimum_w_phi"),
                "minimum_delta_w": payload.get("minimum_delta_w"),
                "late_sample_count": payload.get("late_sample_count"),
                "Omega_phi_BBN": payload.get("Omega_phi_BBN"),
            },
            "thresholds": dict(guard_settings),
            "guards_csv": GUARDS_CSV_FILENAME,
            "guards_csv_rows": rows,
        }
        _atomic_write_json(summary_path, summary)

        return ("OK", f"physics_guard_validator complete: overall_pass={overall_pass}")

    except acoustic_validator.TFAError as exc:
        return ("Error", f"{exc.code}: {exc.message}")
    except BaseException as exc:
        return ("Error", f"{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    # CLI entry for the file-based hub: `python tfa_physics_guard_validator.py <run_folder>`.
    # Prints one JSON line {"code","desc"} and exits 0 (OK) / 1 (Error).
    _run_folder = sys.argv[1] if len(sys.argv) > 1 else "."
    _code, _desc = run_physics_guard_validator(_run_folder)
    print(json.dumps({"code": _code, "desc": _desc}))
    sys.exit(0 if _code == "OK" else 1)

