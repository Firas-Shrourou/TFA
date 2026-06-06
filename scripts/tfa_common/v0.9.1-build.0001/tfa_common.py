"""
TFA hub — settings-driven entry point (v0.9.1).

The researcher defines the scalar field potential once in
``tfa-environment-settings.json`` under ``user_adjustable.potential`` and then
calls:

    import tfa_common as tfa
    result = tfa.run()

Architecture (based on v0.2.0 in-process design):

  1. Reads the settings file and validates the potential expressions.
  2. Builds a ``PotentialRoute`` from the evaluated callables (fails fast if
     expressions are invalid).
  3. Creates a timestamped run folder and freezes a copy of the settings
     (including the potential spec) as a permanent audit record.
  4. Writes the initial ``run_results_summary.json`` with the contract.
  5. Calls each specialist **in-process** (no subprocess):
       - ``tfa_acoustic_validator.run_acoustic_validator(run_folder)``       [fatal]
       - ``tfa_physics_guard_validator.run_physics_guard_validator(run_folder)``  [fatal]
       - ``tfa_plot_exporter.run_plot_exporter(run_folder)``                 [non-fatal]
       - ``tfa_bao_validator.run_bao_validator(run_folder)``                 [non-fatal]
       - ``tfa_rsd_validator.run_rsd_validator(run_folder)``                 [non-fatal]
     Each specialist re-reads the frozen settings from the run folder.
  6. Returns the aggregated result dict.

``code`` is ``"OK"`` when both physics specialists succeed, regardless of whether
the non-fatal specialists (plot exporter, BAO validator, RSD validator) fail.

The run folder is the complete audit record: frozen settings contain the exact
potential definition; the summary contains every result.

Change log (v0.9.1):
  - B001 fix: step-1 settings read now opens with encoding="utf-8-sig" instead
    of delegating to _acoustic.load_environment_settings() (which uses utf-8),
    so a UTF-8 BOM prepended by editors such as Notepad is stripped before
    json.load() is called.
  - B001 fix: _read_json now uses encoding="utf-8-sig" (defensive; covers
    run_results_summary.json reads).
  - B001 fix: frozen settings copy is now written via parse-and-reserialize
    (utf-8-sig read + _atomic_write_json) instead of shutil.copy2, guaranteeing
    the frozen environment-settings.json in every run folder is BOM-free
    regardless of how the original was saved.
  - import shutil removed (no longer needed after the above change).
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


TFA_PROJECT_RELEASE = "0.0.2"
SCRIPT_NAME = "tfa_common"
SCRIPT_VERSION = "0.9.1"
SCRIPT_BUILD = "0001"
SCRIPT_API_VERSION = "0.1"
SETTINGS_SCHEMA_VERSION = "0.1"
SUMMARY_SCHEMA_VERSION = "0.1"

SUMMARY_FILENAME = "run_results_summary.json"
FROZEN_SETTINGS_FILENAME = "environment-settings.json"


def script_identity() -> Mapping[str, str]:
    return {
        "tfa_project_release": TFA_PROJECT_RELEASE,
        "script_name": SCRIPT_NAME,
        "script_version": SCRIPT_VERSION,
        "script_build": SCRIPT_BUILD,
        "script_api_version": SCRIPT_API_VERSION,
        "settings_schema_version": SETTINGS_SCHEMA_VERSION,
        "role": "hub",
    }


# ---------------------------------------------------------------------------
# Locate and import specialists in-process.
# ---------------------------------------------------------------------------

_THIS_DIR = Path(__file__).resolve().parent
_SCRIPTS_DIR = _THIS_DIR.parent.parent

_SPECIALIST_BUILDS = (
    ("tfa_acoustic_validator",      "v0.1.4-build.0001"),
    ("tfa_physics_guard_validator",  "v0.1.4-build.0001"),
    ("tfa_plot_exporter",            "v0.1.0-build.0001"),
    ("tfa_bao_validator",            "v0.1.1-build.0001"),
    ("tfa_rsd_validator",            "v0.1.0-build.0001"),
)

for _name, _build in _SPECIALIST_BUILDS:
    _candidate = _SCRIPTS_DIR / _name / _build
    if _candidate.exists():
        _text = str(_candidate)
        if _text not in sys.path:
            sys.path.insert(0, _text)

import tfa_acoustic_validator as _acoustic        # noqa: E402
import tfa_physics_guard_validator as _guard      # noqa: E402
import tfa_plot_exporter as _plots                # noqa: E402
import tfa_bao_validator as _bao                  # noqa: E402
import tfa_rsd_validator as _rsd                  # noqa: E402


def _unified_settings_path() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "tfa-environment-settings.json"
        if candidate.exists():
            return candidate
    return here.parents[3] / "tfa-environment-settings.json"


DEFAULT_ENVIRONMENT_SETTINGS = _unified_settings_path()


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _atomic_write_json(path: Path, obj: object) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, sort_keys=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _read_json(path: Path) -> dict:
    # B001: utf-8-sig strips a UTF-8 BOM if present; reads normally when absent.
    with path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def run(
    settings_path: str | Path | None = None,
    results_root: str | Path | None = None,
) -> Mapping[str, Any]:
    """Read potential from settings, validate, create run folder, call specialists.

    Parameters
    ----------
    settings_path:
        Path to ``tfa-environment-settings.json``. Defaults to the unified
        package-level file resolved by walking up from this script.
    results_root:
        Directory under which the timestamped run folder is created. Defaults
        to ``<repo>/tfa-results/runs/``.

    Returns
    -------
    dict with keys: ``code``, ``run_folder``, ``calls``, and ``desc``.
    ``code`` is "OK" when both physics specialists succeeded, even if the
    non-fatal specialists (plot exporter, BAO validator) failed.
    """

    src_settings = Path(settings_path) if settings_path is not None else DEFAULT_ENVIRONMENT_SETTINGS
    if not src_settings.exists():
        return {
            "code": "Error",
            "desc": f"settings not found: {src_settings}",
            "run_folder": None,
            "calls": [],
        }

    # --- 1. Load settings and validate potential expressions ----------------
    try:
        # B001: read with utf-8-sig so a UTF-8 BOM is stripped transparently.
        # load_environment_settings() uses encoding="utf-8" and would fail on a
        # BOM-prefixed file; we replicate its JSON parse + structure check here
        # and then call the downstream functions that accept the parsed dict.
        with src_settings.open("r", encoding="utf-8-sig") as _sf:
            settings = json.load(_sf)
        if not isinstance(settings, Mapping):
            raise ValueError("environment settings root must be a JSON object")
        cosmology = _acoustic.cosmology_from_settings(settings)
        V, dV_dphi = _acoustic.build_potential_from_settings(settings, cosmology)
        potential_spec = _acoustic.potential_from_settings(settings)
    except _acoustic.TFAError as exc:
        return {
            "code": "Error",
            "desc": f"{exc.code}: {exc.message}",
            "run_folder": None,
            "calls": [],
        }
    except Exception as exc:
        return {
            "code": "Error",
            "desc": f"settings error: {exc}",
            "run_folder": None,
            "calls": [],
        }

    initial_phi = float(potential_spec["initial_phi"])
    initial_phi_N = float(potential_spec.get("initial_phi_N", 0.0))
    benchmark_id = str(potential_spec.get("benchmark_id") or "unnamed")

    # --- 2. Validate by constructing the route contract ---------------------
    try:
        _acoustic.PotentialRoute(
            benchmark_id=benchmark_id,
            V=V,
            dV_dphi=dV_dphi,
            initial_phi=initial_phi,
            initial_phi_N=initial_phi_N,
        )
    except Exception as exc:
        return {
            "code": "Error",
            "desc": f"potential validation failed: {exc}",
            "run_folder": None,
            "calls": [],
        }

    # --- 3. Create run folder and freeze settings ---------------------------
    export_section = settings.get("user_adjustable", {}).get("export", {})
    prefix = str(export_section.get("prefix", "tfa")) or "tfa"
    ts_fmt = str(export_section.get("timestamp_format", "%Y%m%d_%H%M%S"))

    if results_root is not None:
        root = Path(results_root)
    else:
        root = src_settings.parent.parent / "tfa-results" / "runs"

    run_id = __import__("uuid").uuid4().hex
    stamp = datetime.now().strftime(ts_fmt)
    run_folder = root / f"{prefix}_{stamp}_{run_id}"
    run_folder.mkdir(parents=True, exist_ok=False)

    # B001: parse-and-reserialize instead of shutil.copy2 so the frozen copy
    # is always written as clean UTF-8 (no BOM), regardless of how the original
    # was saved. Uses _atomic_write_json for consistency and crash-safety.
    frozen_settings = run_folder / FROZEN_SETTINGS_FILENAME
    with src_settings.open("r", encoding="utf-8-sig") as _src_f:
        _settings_data = json.load(_src_f)
    _atomic_write_json(frozen_settings, _settings_data)

    # --- 4. Write initial summary -------------------------------------------
    contract = {
        "benchmark_id": benchmark_id,
        "V_of_phi": str(potential_spec.get("V_of_phi", "")),
        "dV_dphi": str(potential_spec.get("dV_dphi", "")),
        "parameters": dict(potential_spec.get("parameters", {})),
        "initial_phi": initial_phi,
        "initial_phi_N": initial_phi_N,
        "user_remarks": str(potential_spec.get("user_remarks", "")),
        "settings_source": FROZEN_SETTINGS_FILENAME,
    }

    summary: dict = {
        "summary_schema_version": SUMMARY_SCHEMA_VERSION,
        "run": {
            "run_id": run_id,
            "created_utc": _now_utc_iso(),
            "prefix": prefix,
            "run_folder": run_folder.name,
            "tfa_project_release": TFA_PROJECT_RELEASE,
            "hub": script_identity(),
            "frozen_settings_file": FROZEN_SETTINGS_FILENAME,
            "status": "initialized",
        },
        "contract": contract,
        "calls": [],
        "results": {},
    }
    summary_path = run_folder / SUMMARY_FILENAME
    _atomic_write_json(summary_path, summary)

    # --- 5. Call specialists in-process -------------------------------------
    # Physics specialists: failure sets overall code to "Error".
    # Non-fatal specialists: failure is recorded but does not affect code.
    physics_specialists = (
        ("tfa_acoustic_validator",      _acoustic.run_acoustic_validator),
        ("tfa_physics_guard_validator",  _guard.run_physics_guard_validator),
    )
    nonfatal_specialists = (
        ("tfa_plot_exporter",  _plots.run_plot_exporter),
        ("tfa_bao_validator",  _bao.run_bao_validator),
        ("tfa_rsd_validator",  _rsd.run_rsd_validator),
    )

    calls: list[dict] = []

    def _call_specialist(name: str, fn: Any) -> dict:
        t0 = time.perf_counter()
        started = _now_utc_iso()
        try:
            code, desc = fn(run_folder)
        except Exception as exc:
            code, desc = "Error", f"{type(exc).__name__}: {exc}"
        duration = time.perf_counter() - t0
        ended = _now_utc_iso()
        entry = {
            "specialist": name,
            "code": code,
            "desc": desc,
            "started_utc": started,
            "ended_utc": ended,
            "duration_s": round(duration, 6),
        }
        calls.append(entry)
        nonlocal summary_path
        s = _read_json(summary_path)
        s.setdefault("calls", []).append(entry)
        _atomic_write_json(summary_path, s)
        return entry

    physics_ok = True
    for name, fn in physics_specialists:
        entry = _call_specialist(name, fn)
        if entry["code"] != "OK":
            physics_ok = False

    for name, fn in nonfatal_specialists:
        _call_specialist(name, fn)

    # --- 6. Finalize summary ------------------------------------------------
    summary = _read_json(summary_path)
    summary["run"]["status"] = "completed" if physics_ok else "completed_with_errors"
    _atomic_write_json(summary_path, summary)

    return {
        "code": "OK" if physics_ok else "Error",
        "desc": "run complete" if physics_ok else "run complete (with errors)",
        "run_folder": str(run_folder),
        "calls": calls,
        "summary_path": str(summary_path),
    }
