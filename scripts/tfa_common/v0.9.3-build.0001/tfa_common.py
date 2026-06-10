"""
TFA hub - settings-driven entry point (v0.9.3).

The researcher defines the scalar field potential once in
``tfa-environment-settings.json`` under ``user_adjustable.potential`` and calls:

    import tfa_common as tfa
    result = tfa.run()

Architecture: reads settings, validates the potential, creates a timestamped run
folder, freezes the settings, writes the initial summary, then calls each
specialist in-process:

  - tfa_acoustic_validator.run_acoustic_validator(run_folder)       [fatal]
  - tfa_physics_guard_validator.run_physics_guard_validator(run_folder) [fatal]
  - tfa_plot_exporter.run_plot_exporter(run_folder)                [non-fatal]
  - tfa_bao_validator.run_bao_validator(run_folder)                [non-fatal]
  - tfa_rsd_validator.run_rsd_validator(run_folder)                [non-fatal]
  - tfa_density_validator.run_density_validator(run_folder)        [non-fatal]
  - tfa_cpl_fidelity_validator.run_cpl_fidelity_validator(run_folder) [non-fatal]

Change log (v0.9.3):
  - Added two downstream specialists to the chain (T004 deliverables 5b/5c):
    tfa_density_validator 0.1.0 (CPL-free density-sector diagnostics: the H0
    pull vs the DESI reference, energy-budget description, f_DE(z), thawing
    markers) and tfa_cpl_fidelity_validator 0.1.0 (CPL audited-not-adopted:
    best-fit CPL error report and the phantom-crossing audit).
  - Both new specialists are NON-GATED (they run for EXCLUDED routes too) and
    non-fatal. The physics verdict is still owned by the acoustic validator.

Change log (v0.9.2):
  - Wired to the core-based stack: tfa_acoustic_validator 0.1.6 and
    tfa_physics_guard_validator 0.1.5; shared utilities come from ``tfa_core``.
  - Settings read with utf-8-sig (BOM-tolerant); the frozen copy is written
    BOM-free.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


TFA_PROJECT_RELEASE = "0.0.5"
SCRIPT_NAME = "tfa_common"
SCRIPT_VERSION = "0.9.3"
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
# Locate and import tfa_core + the specialists in-process.
# ---------------------------------------------------------------------------

_THIS_DIR = Path(__file__).resolve().parent
_SCRIPTS_DIR = _THIS_DIR.parent.parent

_CORE_BUILD = ("tfa_core", "v0.1.0-build.0001")
_SPECIALIST_BUILDS = (
    ("tfa_acoustic_validator",       "v0.1.6-build.0001"),
    ("tfa_physics_guard_validator",  "v0.1.5-build.0001"),
    ("tfa_plot_exporter",            "v0.1.1-build.0001"),
    ("tfa_bao_validator",            "v0.1.1-build.0001"),
    ("tfa_rsd_validator",            "v0.1.0-build.0001"),
    ("tfa_density_validator",        "v0.1.0-build.0001"),
    ("tfa_cpl_fidelity_validator",   "v0.1.0-build.0001"),
)

for _name, _build in (_CORE_BUILD, *_SPECIALIST_BUILDS):
    _candidate = _SCRIPTS_DIR / _name / _build
    if _candidate.exists():
        _text = str(_candidate)
        if _text not in sys.path:
            sys.path.insert(0, _text)

import tfa_core as _core                            # noqa: E402
import tfa_acoustic_validator as _acoustic          # noqa: E402
import tfa_physics_guard_validator as _guard        # noqa: E402
import tfa_plot_exporter as _plots                  # noqa: E402
import tfa_bao_validator as _bao                    # noqa: E402
import tfa_rsd_validator as _rsd                    # noqa: E402
import tfa_density_validator as _density            # noqa: E402
import tfa_cpl_fidelity_validator as _cpl_fidelity  # noqa: E402


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
    # utf-8-sig strips a UTF-8 BOM if present; reads normally when absent.
    with path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def run(
    settings_path: str | Path | None = None,
    results_root: str | Path | None = None,
) -> Mapping[str, Any]:
    """Read the potential from settings, validate, create a run folder, call specialists.

    Returns a dict with keys ``code``, ``run_folder``, ``calls``, ``desc``.
    ``code`` is "OK" when both physics specialists succeed, even if the non-fatal
    specialists fail.
    """

    src_settings = Path(settings_path) if settings_path is not None else DEFAULT_ENVIRONMENT_SETTINGS
    if not src_settings.exists():
        return {"code": "Error", "desc": f"settings not found: {src_settings}", "run_folder": None, "calls": []}

    # --- 1. Load settings and validate potential expressions (via tfa_core) ---
    try:
        with src_settings.open("r", encoding="utf-8-sig") as _sf:
            settings = json.load(_sf)
        if not isinstance(settings, Mapping):
            raise ValueError("environment settings root must be a JSON object")
        cosmology = _core.cosmology_from_settings(settings)
        V, dV_dphi = _core.build_potential_from_settings(settings, cosmology)
        potential_spec = _core.potential_from_settings(settings)
    except _core.TFAError as exc:
        return {"code": "Error", "desc": f"{exc.code}: {exc.message}", "run_folder": None, "calls": []}
    except Exception as exc:
        return {"code": "Error", "desc": f"settings error: {exc}", "run_folder": None, "calls": []}

    initial_phi = float(potential_spec["initial_phi"])
    initial_phi_N = float(potential_spec.get("initial_phi_N", 0.0))
    benchmark_id = str(potential_spec.get("benchmark_id") or "unnamed")

    # --- 2. Validate by constructing the route contract ----------------------
    try:
        _core.PotentialRoute(
            benchmark_id=benchmark_id,
            V=V,
            dV_dphi=dV_dphi,
            initial_phi=initial_phi,
            initial_phi_N=initial_phi_N,
        )
    except Exception as exc:
        return {"code": "Error", "desc": f"potential validation failed: {exc}", "run_folder": None, "calls": []}

    # --- 3. Create run folder and freeze settings ----------------------------
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

    frozen_settings = run_folder / FROZEN_SETTINGS_FILENAME
    with src_settings.open("r", encoding="utf-8-sig") as _src_f:
        _settings_data = json.load(_src_f)
    _atomic_write_json(frozen_settings, _settings_data)

    # --- 4. Write the initial summary ----------------------------------------
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

    # --- 5. Call specialists in-process --------------------------------------
    physics_specialists = (
        ("tfa_acoustic_validator",       _acoustic.run_acoustic_validator),
        ("tfa_physics_guard_validator",  _guard.run_physics_guard_validator),
    )
    nonfatal_specialists = (
        ("tfa_plot_exporter",            _plots.run_plot_exporter),
        ("tfa_bao_validator",            _bao.run_bao_validator),
        ("tfa_rsd_validator",            _rsd.run_rsd_validator),
        ("tfa_density_validator",        _density.run_density_validator),
        ("tfa_cpl_fidelity_validator",   _cpl_fidelity.run_cpl_fidelity_validator),
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

    # --- 6. Finalize summary -------------------------------------------------
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
