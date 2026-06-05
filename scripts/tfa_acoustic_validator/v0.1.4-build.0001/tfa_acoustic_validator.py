"""
Standalone TFA acoustic validator.

This script computes only the compact acoustic verdict for a thawing scalar
route:

- ``H0_X``
- ``delta_X``
- H0 band verdict

It reads the same environment settings JSON format used by the TFA package,
uses the same graceful error and trace style, and deliberately stops before
export gates, normalized histories, trajectory CSV files, plots, or other
science-output products.

The filename follows the requested internal spelling
``tfa_acoustic_validator.py``. Physics comments and payload fields use the
standard spelling "acoustic".
"""

from __future__ import annotations

import csv
import json
import os
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from uuid import uuid4

import numpy as np
from scipy.integrate import quad, solve_ivp


ArrayLike = Sequence[float] | np.ndarray
PotentialFn = Callable[[np.ndarray], np.ndarray]
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
SCRIPT_NAME = "tfa_acoustic_validator"
SCRIPT_VERSION = "0.1.4"
SCRIPT_BUILD = "0001"
SCRIPT_API_VERSION = "0.1"
SETTINGS_SCHEMA_VERSION = "0.1"


PHASE_ERROR_CODES = {
    "environment": "TFA_ENVIRONMENT_ERROR",
    "potential": "TFA_POTENTIAL_ERROR",
    "acoustic_anchor": "TFA_ACOUSTIC_ANCHOR_ERROR",
    "ode_integration": "TFA_ODE_INTEGRATION_ERROR",
    "h0x_solve": "TFA_H0X_SOLVE_ERROR",
    "unknown": "TFA_UNKNOWN_ERROR",
}


class TFAError(RuntimeError):
    """Structured runtime error with stable code and phase."""

    def __init__(
        self,
        code: str,
        message: str,
        phase: str = "unknown",
        cause: BaseException | None = None,
        trace_path: str | Path | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.phase = phase
        self.cause = cause
        self.trace_path = str(trace_path) if trace_path is not None else None

    def to_dict(self) -> Mapping[str, str]:
        data = {
            "code": self.code,
            "phase": self.phase,
            "message": self.message,
        }
        if self.cause is not None:
            data["cause_type"] = type(self.cause).__name__
            data["cause_message"] = str(self.cause)
        if self.trace_path is not None:
            data["trace_path"] = self.trace_path
        return data


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


def _utc_timestamp() -> str:
    """Return an ISO-8601 UTC timestamp for trace records."""

    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _debug_print(enabled: bool, message: str) -> None:
    """Print only when environment settings request debug output."""

    if enabled:
        print(f"[TFA DEBUG] {message}")


class RunTrace:
    """JSON-lines phase trace for one validator run.

    Trace records intentionally avoid physics arrays and detailed results.
    They include route id, phase names, status, durations, and error metadata.
    """

    def __init__(
        self,
        route_id: str,
        enabled: bool = True,
        debug_print: bool = False,
        trace_dir: str | Path = "tfa-run-logs",
        filename_prefix: str = "tfa-run",
    ) -> None:
        self.run_id = uuid4().hex
        self.route_id = route_id
        self.enabled = enabled
        self.debug_print = debug_print
        self.trace_path: Path | None = None
        if enabled:
            directory = Path(trace_dir)
            directory.mkdir(parents=True, exist_ok=True)
            filename = f"{filename_prefix}-acoustic-validator-{route_id}-{self.run_id}.jsonl"
            self.trace_path = directory / filename
            self.event("run", "START", "TFA acoustic validator started")

    def event(
        self,
        phase: str,
        status: str,
        message: str = "",
        code: str | None = None,
        duration_s: float | None = None,
    ) -> None:
        _debug_print(self.debug_print, f"{phase}: {status} {message}".strip())
        if not self.enabled or self.trace_path is None:
            return
        record: dict[str, object] = {
            "timestamp_utc": _utc_timestamp(),
            "run_id": self.run_id,
            "route_id": self.route_id,
            "phase": phase,
            "status": status,
        }
        if message:
            record["message"] = message
        if code:
            record["code"] = code
        if duration_s is not None:
            record["duration_s"] = round(duration_s, 6)
        with self.trace_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, sort_keys=True) + "\n")

    def close(self, status: str, message: str = "") -> None:
        self.event("run", status, message)


def _phase_error(phase: str, exc: BaseException) -> TFAError:
    """Wrap arbitrary exceptions in a phase-specific ``TFAError``."""

    if isinstance(exc, TFAError):
        return exc
    code = PHASE_ERROR_CODES.get(phase, PHASE_ERROR_CODES["unknown"])
    return TFAError(code=code, message=f"{phase} failed: {exc}", phase=phase, cause=exc)


def _run_phase(trace: RunTrace, phase: str, func: Callable[[], Any]) -> Any:
    """Run one named phase with START/PASS/ERROR trace events."""

    start = time.perf_counter()
    trace.event(phase, "START")
    try:
        value = func()
    except BaseException as exc:
        err = _phase_error(phase, exc)
        trace.event(phase, "ERROR", err.message, err.code, time.perf_counter() - start)
        raise err from exc
    trace.event(phase, "PASS", duration_s=time.perf_counter() - start)
    return value


@dataclass(frozen=True)
class CosmologyContext:
    """Reference FLRW constants used by ODE and acoustic calculations."""

    Omega_m0: float = 0.3152
    Omega_r0: float = 9.18e-5
    H0_ref_kms: float = 67.36
    c_kms: float = 2.99792458e5
    Omega_DE: float | None = None

    def __post_init__(self) -> None:
        omega_de = (
            1.0 - self.Omega_m0 - self.Omega_r0
            if self.Omega_DE is None
            else self.Omega_DE
        )
        object.__setattr__(self, "Omega_DE", omega_de)
        if self.Omega_m0 <= 0.0:
            raise ValueError("Omega_m0 must be positive")
        if self.Omega_r0 < 0.0:
            raise ValueError("Omega_r0 must be non-negative")
        if omega_de <= 0.0:
            raise ValueError("Omega_DE must be positive")
        if self.H0_ref_kms <= 0.0:
            raise ValueError("H0_ref_kms must be positive")
        if self.c_kms <= 0.0:
            raise ValueError("c_kms must be positive")


@dataclass(frozen=True)
class AcousticConfig:
    """Candidate-independent physical-density anchor inputs."""

    OBH2: float = 0.02237
    OMH2: float = 0.1430
    T0_K: float = 2.7255
    NEFF: float = 3.046
    OGH2: float = 2.4728e-5
    theta_star_target: float = 0.010411
    z_integral_max: float = 1e8
    theta_tolerance: float = 1e-10

    def __post_init__(self) -> None:
        if self.OBH2 <= 0.0:
            raise ValueError("OBH2 must be positive")
        if self.OMH2 <= 0.0:
            raise ValueError("OMH2 must be positive")
        if self.T0_K <= 0.0:
            raise ValueError("T0_K must be positive")
        if self.NEFF <= 0.0:
            raise ValueError("NEFF must be positive")
        if self.OGH2 <= 0.0:
            raise ValueError("OGH2 must be positive")
        if self.theta_star_target <= 0.0:
            raise ValueError("theta_star_target must be positive")


@dataclass(frozen=True)
class AcousticBands:
    """Ordered H0X verdict bands, from narrowest to widest."""

    strict: tuple[float, float] = (66.82, 67.90)
    loose_2s: tuple[float, float] = (66.28, 68.44)
    loose_3s: tuple[float, float] = (65.74, 68.98)

    def classify(self, H0_X_kms: float) -> str:
        if self.strict[0] <= H0_X_kms <= self.strict[1]:
            return "STRICT"
        if self.loose_2s[0] <= H0_X_kms <= self.loose_2s[1]:
            return "LOOSE_2S"
        if self.loose_3s[0] <= H0_X_kms <= self.loose_3s[1]:
            return "LOOSE_3S"
        return "EXCLUDED"


@dataclass(frozen=True)
class IntegrationConfig:
    """Canonical scalar ODE solver configuration."""

    z_ini: float = 1e6
    z_final: float = 0.0
    method: str = "DOP853"
    rtol: float = 1e-10
    atol: float = 1e-12
    max_step: float = 0.01
    dense_output: bool = True

    def __post_init__(self) -> None:
        if self.z_ini <= self.z_final:
            raise ValueError("z_ini must be greater than z_final")
        if self.z_final != 0.0:
            raise ValueError("TFA acoustic validator expects z_final = 0")
        if self.rtol <= 0.0 or self.atol <= 0.0:
            raise ValueError("solver tolerances must be positive")
        if self.max_step <= 0.0:
            raise ValueError("max_step must be positive")


@dataclass(frozen=True)
class PotentialRoute:
    """Generic canonical scalar route supplied by a source adapter."""

    benchmark_id: str
    V: PotentialFn
    dV_dphi: PotentialFn
    initial_phi: float
    initial_phi_N: float = 0.0
    dynamic_parameters: Mapping[str, float | str | None] = field(default_factory=dict)
    source_landmarks: Mapping[str, float | str | None] = field(default_factory=dict)
    units: Mapping[str, str] = field(default_factory=dict)
    provenance: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.benchmark_id:
            raise ValueError("benchmark_id is required")
        if not np.isfinite(self.initial_phi):
            raise ValueError("initial_phi must be finite")
        if not np.isfinite(self.initial_phi_N):
            raise ValueError("initial_phi_N must be finite")
        v0 = np.asarray(self.V(np.asarray([self.initial_phi], dtype=float)))
        dv0 = np.asarray(self.dV_dphi(np.asarray([self.initial_phi], dtype=float)))
        if v0.shape != (1,) or dv0.shape != (1,):
            raise ValueError("V and dV_dphi must accept and return numpy arrays")
        if not np.isfinite(v0[0]) or not np.isfinite(dv0[0]):
            raise ValueError("potential and derivative must be finite initially")
        if v0[0] <= 0.0:
            raise ValueError("potential must be positive initially")


@dataclass(frozen=True)
class AcousticAnchor:
    """Candidate-independent acoustic reference package."""

    z_star: float
    r_s_raw_Mpc: float
    rs_calibration: float
    r_s_Mpc: float
    D_M_LCDM_Mpc: float
    theta_star: float
    anchor_residual: float
    anchor_check: str
    # Drag-epoch sound horizon — the correct BAO ruler (Eisenstein-Hu 1998 fit).
    # r_d_Mpc > r_s_Mpc because z_drag < z_star (baryons decouple after photons).
    z_drag: float = 0.0
    r_drag_Mpc: float = 0.0


@dataclass(frozen=True)
class H0XResult:
    """Route-specific acoustic-preserving Hubble verdict."""

    benchmark_id: str
    D_M_X_Mpc: float
    D_M_LCDM_Mpc: float
    H0_X_kms: float
    H0_ref_kms: float
    Omega_m_X: float
    delta_X: float
    status: str


def _require_mapping(parent: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    """Return a required nested mapping from JSON settings."""

    value = parent.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f"settings section '{key}' must be an object")
    return value


def _tuple_pair(value: Any, key: str) -> tuple[float, float]:
    """Parse a JSON two-number list as a float pair."""

    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"'{key}' must be a two-number array")
    if len(value) != 2:
        raise ValueError(f"'{key}' must contain exactly two numbers")
    lo = float(value[0])
    hi = float(value[1])
    if lo > hi:
        raise ValueError(f"'{key}' lower bound must be <= upper bound")
    return lo, hi


def load_environment_settings(path: str | Path | None = None) -> Mapping[str, Any]:
    """Read the TFA environment settings JSON."""

    settings_path = Path(path) if path is not None else DEFAULT_ENVIRONMENT_SETTINGS
    with settings_path.open("r", encoding="utf-8") as f:
        settings = json.load(f)
    if not isinstance(settings, Mapping):
        raise ValueError("environment settings root must be a JSON object")
    _require_mapping(settings, "read_only_hardcoded_defaults")
    _require_mapping(settings, "user_adjustable")
    return settings


def user_adjustable_settings(settings: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return the runtime-consumed user-adjustable settings section."""

    return _require_mapping(settings, "user_adjustable")


def cosmology_from_settings(settings: Mapping[str, Any]) -> CosmologyContext:
    """Build ``CosmologyContext`` from settings."""

    section = _require_mapping(user_adjustable_settings(settings), "cosmology")
    return CosmologyContext(
        Omega_m0=float(section["Omega_m0"]),
        Omega_r0=float(section["Omega_r0"]),
        Omega_DE=None if section.get("Omega_DE") is None else float(section["Omega_DE"]),
        H0_ref_kms=float(section["H0_ref_kms"]),
        c_kms=float(section["c_kms"]),
    )


def acoustic_config_from_settings(settings: Mapping[str, Any]) -> AcousticConfig:
    """Build ``AcousticConfig`` from settings."""

    section = _require_mapping(user_adjustable_settings(settings), "acoustic_priors")
    return AcousticConfig(
        OBH2=float(section["OBH2"]),
        OMH2=float(section["OMH2"]),
        T0_K=float(section["T0_K"]),
        NEFF=float(section["NEFF"]),
        OGH2=float(section["OGH2"]),
        theta_star_target=float(section["theta_star_target"]),
        z_integral_max=float(section["z_integral_max"]),
        theta_tolerance=float(section["theta_tolerance"]),
    )


def acoustic_bands_from_settings(settings: Mapping[str, Any]) -> AcousticBands:
    """Build ``AcousticBands`` from settings."""

    section = _require_mapping(user_adjustable_settings(settings), "planck_h0_bands")
    return AcousticBands(
        strict=_tuple_pair(section["strict"], "strict"),
        loose_2s=_tuple_pair(section["loose_2s"], "loose_2s"),
        loose_3s=_tuple_pair(section["loose_3s"], "loose_3s"),
    )


def integration_config_from_settings(settings: Mapping[str, Any]) -> IntegrationConfig:
    """Build ``IntegrationConfig`` from settings."""

    section = _require_mapping(user_adjustable_settings(settings), "integration")
    return IntegrationConfig(
        z_ini=float(section["z_ini"]),
        z_final=float(section["z_final"]),
        method=str(section["method"]),
        rtol=float(section["rtol"]),
        atol=float(section["atol"]),
        max_step=float(section["max_step"]),
        dense_output=bool(section["dense_output"]),
    )


def execution_settings_from_settings(
    settings: Mapping[str, Any],
    settings_path: str | Path | None = None,
) -> Mapping[str, object]:
    """Return runtime execution controls from settings."""

    section = _require_mapping(user_adjustable_settings(settings), "execution")
    trace_dir = Path(str(section["trace_dir"]))
    if not trace_dir.is_absolute():
        base = Path(settings_path).resolve().parent if settings_path is not None else DEFAULT_ENVIRONMENT_SETTINGS.parent
        trace_dir = (base / trace_dir).resolve()
    return {
        "debug_print": bool(section["debug_print"]),
        "trace_enabled": bool(section["trace_enabled"]),
        "trace_dir": trace_dir,
        "trace_filename_prefix": str(section["trace_filename_prefix"]),
        "safe_runner_returns_error_object": bool(section["safe_runner_returns_error_object"]),
    }


def runtime_environment_from_settings(path: str | Path | None = None) -> Mapping[str, object]:
    """Load settings and build validator runtime configuration objects."""

    settings_path = Path(path) if path is not None else DEFAULT_ENVIRONMENT_SETTINGS
    settings = load_environment_settings(settings_path)
    return {
        "settings": settings,
        "cosmology": cosmology_from_settings(settings),
        "acoustic_config": acoustic_config_from_settings(settings),
        "acoustic_bands": acoustic_bands_from_settings(settings),
        "integration_config": integration_config_from_settings(settings),
        "execution_settings": execution_settings_from_settings(settings, settings_path),
    }


def compute_z_star(config: AcousticConfig) -> float:
    """Hu-Sugiyama photon decoupling redshift fit."""

    g1 = 0.0783 * config.OBH2 ** -0.238 / (1.0 + 39.5 * config.OBH2 ** 0.763)
    g2 = 0.560 / (1.0 + 21.1 * config.OBH2 ** 1.81)
    return float(1048.0 * (1.0 + 0.00124 * config.OBH2 ** -0.738) * (1.0 + g1 * config.OMH2 ** g2))


def compute_z_drag(config: AcousticConfig) -> float:
    """Eisenstein-Hu (1998) baryon drag epoch redshift fit (Eq. 4).

    z_drag is the redshift at which baryons decouple from the photon-baryon
    fluid.  Because baryons are still dragged by photons for a short while after
    photon decoupling, z_drag < z_star, so r_drag > r_s(z_star).
    r_drag is the physically correct BAO standard ruler used by DESI.
    """

    b1 = (
        0.313 * config.OMH2 ** -0.419
        * (1.0 + 0.607 * config.OMH2 ** 0.674)
    )
    b2 = 0.238 * config.OMH2 ** 0.223
    return float(
        1345.0
        * config.OMH2 ** 0.251
        / (1.0 + 0.659 * config.OMH2 ** 0.828)
        * (1.0 + b1 * config.OBH2 ** b2)
    )


def H_lcdm_kms(z: float | np.ndarray, cosmology: CosmologyContext) -> np.ndarray:
    """Reference LCDM H(z) in km/s/Mpc."""

    z_arr = np.asarray(z, dtype=float)
    E2 = (
        cosmology.Omega_m0 * (1.0 + z_arr) ** 3
        + cosmology.Omega_r0 * (1.0 + z_arr) ** 4
        + cosmology.Omega_DE
    )
    return cosmology.H0_ref_kms * np.sqrt(E2)


def baryon_to_photon_momentum_ratio(z: float | np.ndarray, config: AcousticConfig) -> np.ndarray:
    """Baryon-to-photon momentum ratio R(z) (appendix eq. R-numeric)."""

    z_arr = np.asarray(z, dtype=float)
    return 31500.0 * config.OBH2 * (config.T0_K / 2.7) ** (-4) / (1.0 + z_arr)


def photon_baryon_sound_speed_kms(
    z: float | np.ndarray,
    cosmology: CosmologyContext,
    config: AcousticConfig,
) -> np.ndarray:
    """Photon-baryon sound speed in km/s (appendix eq. cs-R)."""

    ratio = baryon_to_photon_momentum_ratio(z, config)
    return cosmology.c_kms / np.sqrt(3.0 * (1.0 + ratio))


def compute_r_s_raw_Mpc(
    z_star: float,
    cosmology: CosmologyContext,
    config: AcousticConfig,
) -> float:
    """Raw comoving sound horizon in Mpc.

    Matches the canonical TFA implementation (``tfa_common`` / ``wli_run``) and
    the appendix: the pre-recombination integrand uses matter+radiation only
    (eq. HX-early, scalar/DE inert for z >= z_star), the ``31500`` R-form
    (eq. R-numeric), and the ``u = ln(1+z)`` substitution.
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
        integrand,
        np.log1p(z_star),
        np.log1p(config.z_integral_max),
        epsrel=1e-9,
        limit=500,
    )
    return float(value)


def comoving_distance_Mpc(
    H_kms: Callable[[float], float],
    z_max: float,
    cosmology: CosmologyContext,
    epsabs: float = 1e-4,
    epsrel: float = 1e-8,
) -> float:
    """Comoving distance integral ``D_M(z_max) = integral c / H(z) dz``."""

    value, _ = quad(
        lambda z: cosmology.c_kms / H_kms(float(z)),
        0.0,
        z_max,
        limit=500,
        epsabs=epsabs,
        epsrel=epsrel,
    )
    return float(value)


def compute_acoustic_anchor(
    cosmology: CosmologyContext,
    config: AcousticConfig,
) -> AcousticAnchor:
    """Compute the shared acoustic anchor for one settings configuration.

    Computes two sound-horizon scales:
      r_s_Mpc   — calibrated to theta_star at z_star; used for H0X normalisation.
      r_drag_Mpc — drag-epoch sound horizon (z_drag < z_star); the correct BAO ruler.
    Both use the same calibration factor from the theta_star fit so that the
    overall sound-speed normalisation is consistent between the two epochs.
    """

    z_star = compute_z_star(config)
    r_s_raw = compute_r_s_raw_Mpc(z_star, cosmology, config)
    D_M_LCDM = comoving_distance_Mpc(lambda z: float(H_lcdm_kms(z, cosmology)), z_star, cosmology)
    rs_calibration = config.theta_star_target * D_M_LCDM / r_s_raw
    r_s = rs_calibration * r_s_raw
    theta_star = r_s / D_M_LCDM
    residual = theta_star - config.theta_star_target
    check = "PASS" if abs(residual) <= config.theta_tolerance else "FAIL"
    if check != "PASS":
        raise RuntimeError(f"acoustic anchor check failed: residual={residual:.3e}")

    # Drag-epoch sound horizon: integrate to z_drag < z_star, apply same calibration.
    z_drag = compute_z_drag(config)
    r_drag_raw = compute_r_s_raw_Mpc(z_drag, cosmology, config)
    r_drag = rs_calibration * r_drag_raw

    return AcousticAnchor(
        z_star=z_star,
        r_s_raw_Mpc=r_s_raw,
        rs_calibration=rs_calibration,
        r_s_Mpc=r_s,
        D_M_LCDM_Mpc=D_M_LCDM,
        theta_star=theta_star,
        anchor_residual=residual,
        anchor_check=check,
        z_drag=z_drag,
        r_drag_Mpc=r_drag,
    )


def _eval_route_state(
    route: PotentialRoute,
    cosmology: CosmologyContext,
    N_arr: ArrayLike,
    y_arr: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Evaluate scalar state quantities needed by the H0X route distance."""

    N = np.asarray(N_arr, dtype=float)
    phi = np.asarray(y_arr[0], dtype=float)
    phi_N = np.asarray(y_arr[1], dtype=float)
    a = np.exp(N)
    V = np.asarray(route.V(phi), dtype=float)
    rhs_fried = (
        3.0 * cosmology.Omega_m0 * a**-3
        + 3.0 * cosmology.Omega_r0 * a**-4
        + V
    )
    denom = 3.0 - 0.5 * phi_N**2
    if np.any(denom <= 0.0):
        raise RuntimeError("phi_N^2 >= 6: kinetic energy exceeds canonical bound")
    H2 = rhs_fried / denom
    return phi, phi_N, H2, np.sqrt(H2)


def make_scalar_rhs(
    route: PotentialRoute,
    cosmology: CosmologyContext,
) -> Callable[[float, Sequence[float]], list[float]]:
    """Build the generic canonical scalar-field RHS in e-fold time."""

    def rhs(N: float, y: Sequence[float]) -> list[float]:
        phi = np.asarray([y[0]], dtype=float)
        phi_N = float(y[1])
        a = np.exp(N)
        V = float(route.V(phi)[0])
        dV = float(route.dV_dphi(phi)[0])
        rhs_fried = (
            3.0 * cosmology.Omega_m0 * a**-3
            + 3.0 * cosmology.Omega_r0 * a**-4
            + V
        )
        denom = 3.0 - 0.5 * phi_N**2
        if denom <= 0.0:
            raise RuntimeError("phi_N^2 >= 6: kinetic energy exceeds canonical bound")
        H2 = rhs_fried / denom
        d_rhs_fried_dN = (
            -9.0 * cosmology.Omega_m0 * a**-3
            - 12.0 * cosmology.Omega_r0 * a**-4
            + dV * phi_N
        )
        dlnH = 0.5 * d_rhs_fried_dN / (H2 * denom)
        phi_NN = -(3.0 + dlnH) * phi_N - dV / H2
        return [phi_N, phi_NN]

    return rhs


def integrate_scalar_route(
    route: PotentialRoute,
    cosmology: CosmologyContext,
    config: IntegrationConfig,
) -> object:
    """Integrate one canonical scalar route and return the dense solver."""

    N_ini = -np.log(1.0 + config.z_ini)
    sol = solve_ivp(
        make_scalar_rhs(route, cosmology),
        [N_ini, 0.0],
        [route.initial_phi, route.initial_phi_N],
        method=config.method,
        dense_output=config.dense_output,
        rtol=config.rtol,
        atol=config.atol,
        max_step=config.max_step,
    )
    if not sol.success:
        raise RuntimeError(f"ODE failed for {route.benchmark_id}: {sol.message}")
    if sol.sol is None:
        raise RuntimeError("dense ODE solution is required for H0X solve")
    return sol


def evaluate_raw_E_at_z(
    route: PotentialRoute,
    cosmology: CosmologyContext,
    sol: object,
    z: float,
) -> float:
    """Evaluate raw dimensionless route expansion at one redshift."""

    if z < 0.0:
        raise ValueError("z must be non-negative")
    N = np.asarray([-np.log1p(z)], dtype=float)
    y = sol.sol(N)
    _phi, _phi_N, _H2, raw_E = _eval_route_state(route, cosmology, N, y)
    return float(raw_E[0])


def solve_h0x(
    route: PotentialRoute,
    cosmology: CosmologyContext,
    acoustic_anchor: AcousticAnchor,
    sol: object,
    acoustic_config: AcousticConfig,
    bands: AcousticBands,
) -> H0XResult:
    """Solve the route-specific acoustic-preserving H0X value."""

    def H_route_kms(z: float) -> float:
        return cosmology.H0_ref_kms * evaluate_raw_E_at_z(route, cosmology, sol, z)

    D_M_X = comoving_distance_Mpc(H_route_kms, acoustic_anchor.z_star, cosmology)
    if D_M_X <= 0.0:
        raise RuntimeError("D_M_X must be positive")
    H0_X = cosmology.H0_ref_kms * (D_M_X / acoustic_anchor.D_M_LCDM_Mpc)
    Omega_m_X = acoustic_config.OMH2 / (H0_X / 100.0) ** 2
    delta_X = H0_X / cosmology.H0_ref_kms - 1.0
    return H0XResult(
        benchmark_id=route.benchmark_id,
        D_M_X_Mpc=D_M_X,
        D_M_LCDM_Mpc=acoustic_anchor.D_M_LCDM_Mpc,
        H0_X_kms=H0_X,
        H0_ref_kms=cosmology.H0_ref_kms,
        Omega_m_X=Omega_m_X,
        delta_X=delta_X,
        status=bands.classify(H0_X),
    )


def _route_id(route: PotentialRoute) -> str:
    """Return a route id suitable for trace filenames."""

    return getattr(route, "benchmark_id", "unknown-route") or "unknown-route"


def validate_h0x(
    route: PotentialRoute,
    settings_path: str | Path | None = None,
) -> Mapping[str, object]:
    """
    Validate the acoustic H0X verdict for one route.

    The caller supplies a complete ``PotentialRoute``. The validator reads the
    environment settings on every call and returns only the H0X verdict payload.
    """

    settings_path = DEFAULT_ENVIRONMENT_SETTINGS if settings_path is None else settings_path
    env = runtime_environment_from_settings(settings_path)
    execution = env["execution_settings"]
    trace = RunTrace(
        route_id=_route_id(route),
        enabled=bool(execution["trace_enabled"]),
        debug_print=bool(execution["debug_print"]),
        trace_dir=execution["trace_dir"],
        filename_prefix=str(execution["trace_filename_prefix"]),
    )
    try:
        cosmology = _run_phase(trace, "environment", lambda: env["cosmology"])
        acoustic_config = _run_phase(trace, "environment", lambda: env["acoustic_config"])
        acoustic_bands = _run_phase(trace, "environment", lambda: env["acoustic_bands"])
        integration_config = _run_phase(trace, "environment", lambda: env["integration_config"])
        anchor = _run_phase(
            trace,
            "acoustic_anchor",
            lambda: compute_acoustic_anchor(cosmology, acoustic_config),
        )
        sol = _run_phase(
            trace,
            "ode_integration",
            lambda: integrate_scalar_route(route, cosmology, integration_config),
        )
        h0x = _run_phase(
            trace,
            "h0x_solve",
            lambda: solve_h0x(route, cosmology, anchor, sol, acoustic_config, acoustic_bands),
        )
        trace.close("PASS", "TFA acoustic validator completed")
        return {
            "ok": True,
            "payload": {
                "benchmark_id": route.benchmark_id,
                "H0_X_kms": h0x.H0_X_kms,
                "delta_X": h0x.delta_X,
                "band": h0x.status,
                "H0_ref_kms": h0x.H0_ref_kms,
                "Omega_m_X": h0x.Omega_m_X,
                "D_M_X_Mpc": h0x.D_M_X_Mpc,
                "D_M_LCDM_Mpc": h0x.D_M_LCDM_Mpc,
                "script": script_identity(),
                "trace_path": str(trace.trace_path) if trace.trace_path is not None else None,
            },
        }
    except BaseException as exc:
        err = exc if isinstance(exc, TFAError) else _phase_error("unknown", exc)
        if trace.trace_path is not None:
            err.trace_path = str(trace.trace_path)
        trace.close("ERROR", err.message)
        raise err from exc


def validate_h0x_safe(
    route: PotentialRoute,
    settings_path: str | Path | None = None,
) -> Mapping[str, object]:
    """Safe wrapper returning structured error dictionaries."""

    try:
        return validate_h0x(route, settings_path)
    except TFAError as exc:
        return {
            "ok": False,
            "error": exc.to_dict(),
            "traceback": traceback.format_exc(),
            "script": script_identity(),
        }
    except BaseException as exc:
        err = _phase_error("unknown", exc)
        return {
            "ok": False,
            "error": err.to_dict(),
            "traceback": traceback.format_exc(),
            "script": script_identity(),
        }


def validate_h0x_values(
    route: PotentialRoute,
    settings_path: str | Path | None = None,
) -> tuple[float, float, str]:
    """Return only ``(H0_X_kms, delta_X, band)``."""

    result = validate_h0x(route, settings_path)
    payload = result["payload"]
    return (
        float(payload["H0_X_kms"]),
        float(payload["delta_X"]),
        str(payload["band"]),
    )


def validate_many_h0x_safe(
    routes: Sequence[PotentialRoute],
    settings_path: str | Path | None = None,
) -> Mapping[str, object]:
    """Safe batch validator for multiple independent routes."""

    results = [validate_h0x_safe(route, settings_path) for route in routes]
    return {
        "ok": all(bool(item.get("ok")) for item in results),
        "results": results,
        "script": script_identity(),
    }


# ===========================================================================
# File-based run-folder layer (added in 0.1.2)
#
# This is how the hub (tfa_common, file-based) invokes the engine. The engine
# reads the frozen settings + contract from the run folder, rebuilds V from the
# named potential form, runs the physics ONCE, writes trajectory.csv, enriches
# run_results_summary.json with its own results section, and returns the agreed
# (Code, Desc) tuple. It is the first specialist in the chain and the only one
# that integrates the ODE; downstream specialists read trajectory.csv.
# ===========================================================================

SUMMARY_FILENAME = "run_results_summary.json"
FROZEN_SETTINGS_FILENAME = "environment-settings.json"
TRAJECTORY_FILENAME = "trajectory.csv"
SHAPE_CSV_FILENAME = "expansion_history_shape.csv"
HISTORY_CSV_FILENAME = "expansion_history_h0x_normalized.csv"
W_OF_Z_CSV_FILENAME = "w_of_z.csv"


def potential_from_settings(settings: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return the potential spec from user_adjustable settings."""

    return _require_mapping(user_adjustable_settings(settings), "potential")


def build_potential_from_settings(
    settings: Mapping[str, Any],
    cosmology: CosmologyContext,
) -> tuple[Callable[[np.ndarray], np.ndarray], Callable[[np.ndarray], np.ndarray]]:
    """Build (V, dV_dphi) callables from the potential section of settings.

    The researcher writes V_of_phi and dV_dphi as numpy-compatible expression
    strings in tfa-environment-settings.json under user_adjustable.potential.
    Parameters named in the expressions are injected from potential.parameters;
    Omega_DE is injected from the cosmology context.

    If dV_dphi is omitted or empty, a central-difference numerical derivative
    is computed automatically (step 1e-6). Supplying the analytic form is
    preferred for ODE accuracy.

    Safe evaluation: __builtins__ is disabled; only explicit math functions and
    the declared parameters are available in the namespace.
    """

    spec = potential_from_settings(settings)
    V_expr = str(spec.get("V_of_phi", "")).strip()
    dV_expr = str(spec.get("dV_dphi", "")).strip()
    raw_params = spec.get("parameters", {})
    if not isinstance(raw_params, Mapping):
        raise TFAError(
            code="TFA_POTENTIAL_ERROR",
            message="potential.parameters must be a JSON object",
            phase="potential",
        )
    if not V_expr:
        raise TFAError(
            code="TFA_POTENTIAL_ERROR",
            message="potential.V_of_phi is required in user_adjustable settings",
            phase="potential",
        )

    params = {k: float(v) for k, v in raw_params.items()}
    namespace: dict = {
        "__builtins__": {},
        "exp": np.exp, "log": np.log, "log10": np.log10,
        "sqrt": np.sqrt, "abs": np.abs,
        "sin": np.sin, "cos": np.cos, "tan": np.tan,
        "sinh": np.sinh, "cosh": np.cosh, "tanh": np.tanh,
        "arcsin": np.arcsin, "arccos": np.arccos, "arctan": np.arctan,
        "pi": np.pi, "e": np.e,
        "Omega_DE": float(cosmology.Omega_DE),
        **params,
    }

    try:
        def V(phi: np.ndarray) -> np.ndarray:
            phi = np.asarray(phi, dtype=float)
            return np.asarray(eval(V_expr, {**namespace, "phi": phi}), dtype=float)  # noqa: S307

        # Smoke-test at a unit value to catch syntax errors immediately.
        V(np.asarray([1.0]))
    except TFAError:
        raise
    except Exception as exc:
        raise TFAError(
            code="TFA_POTENTIAL_ERROR",
            message=f"V_of_phi expression failed: {exc}",
            phase="potential",
            cause=exc,
        ) from exc

    if dV_expr:
        try:
            def dV_dphi(phi: np.ndarray) -> np.ndarray:
                phi = np.asarray(phi, dtype=float)
                return np.asarray(eval(dV_expr, {**namespace, "phi": phi}), dtype=float)  # noqa: S307

            dV_dphi(np.asarray([1.0]))
        except TFAError:
            raise
        except Exception as exc:
            raise TFAError(
                code="TFA_POTENTIAL_ERROR",
                message=f"dV_dphi expression failed: {exc}",
                phase="potential",
                cause=exc,
            ) from exc
    else:
        # Numerical central-difference fallback.
        _h = 1e-6

        def dV_dphi(phi: np.ndarray) -> np.ndarray:
            phi = np.asarray(phi, dtype=float)
            return (V(phi + _h) - V(phi - _h)) / (2.0 * _h)

    return V, dV_dphi


def _read_json(path: str | Path) -> dict:
    """Read a JSON file into a dict."""

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


def _write_trajectory_csv(
    path: str | Path,
    N: np.ndarray,
    z: np.ndarray,
    phi: np.ndarray,
    phi_N: np.ndarray,
    E_X: np.ndarray,
    H_X: np.ndarray,
    w_phi: np.ndarray,
    Omega_phi: np.ndarray,
) -> int:
    """Write the dense trajectory table. Returns the row count."""

    with Path(path).open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["N", "z", "a", "phi", "dphi_dN", "E_X", "H_X", "w_phi", "Omega_phi"])
        for i in range(len(N)):
            writer.writerow(
                [
                    f"{N[i]:.12g}",
                    f"{z[i]:.12g}",
                    f"{np.exp(N[i]):.12g}",
                    f"{phi[i]:.12g}",
                    f"{phi_N[i]:.12g}",
                    f"{E_X[i]:.12g}",
                    f"{H_X[i]:.12g}",
                    f"{w_phi[i]:.12g}",
                    f"{Omega_phi[i]:.12g}",
                ]
            )
    return int(len(N))


def _export_config_from_settings(settings: Mapping[str, object]) -> Mapping[str, object]:
    """Read export grid/tolerances and the band export gate from settings."""

    user = user_adjustable_settings(settings)
    exp = _require_mapping(user, "export")
    gate = _require_mapping(user, "export_gate")
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
    """Standard low-z export grid plus the acoustic-anchor redshift."""

    grid = np.concatenate([np.arange(0.0, low_z_max + low_z_step / 2.0, low_z_step), [z_star]])
    return np.sort(np.unique(grid))


def _write_shape_csv(path, z, E_X, H0_X, H0_ref, delta_X, shape_residual, shape_check) -> None:
    """Write expansion_history_shape.csv (z, E_X) with the TFA contract header."""

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
    """Write expansion_history_h0x_normalized.csv (z, H_X) with the TFA contract header."""

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


def _eval_w_phi_at_z(
    route: PotentialRoute,
    cosmology: CosmologyContext,
    sol: object,
    z: float,
) -> float:
    """Evaluate scalar equation-of-state w_phi at one redshift from the dense solver."""

    N = np.asarray([-np.log1p(z)], dtype=float)
    y = sol.sol(N)
    phi, phi_N, H2, _ = _eval_route_state(route, cosmology, N, y)
    V_arr = np.asarray(route.V(phi), dtype=float)
    kinetic = 0.5 * H2 * phi_N**2
    denom = kinetic[0] + V_arr[0]
    if denom == 0.0:
        raise RuntimeError(f"w_phi denominator is zero at z={z}")
    return float((kinetic[0] - V_arr[0]) / denom)


def _write_w_of_z_csv(path, z, w_phi, H0_X, H0_ref, delta_X, band) -> None:
    """Write w_of_z.csv (z, w_phi) with the TFA contract header."""

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


def run_acoustic_validator(run_folder: str | Path) -> tuple[str, str]:
    """File-based engine entry point. Returns ``(Code, Desc)``.

    Reads the contract + frozen settings from ``run_folder``, rebuilds the
    potential, runs the acoustic/H0X physics once, writes ``trajectory.csv``,
    and enriches ``run_results_summary.json`` under
    ``results["acoustic_validator"]``. All results go to disk; the return value
    is only the (Code, Desc) signal for the hub.
    """

    try:
        run_folder = Path(run_folder)
        summary_path = run_folder / SUMMARY_FILENAME
        settings_path = run_folder / FROZEN_SETTINGS_FILENAME
        if not summary_path.exists():
            return ("Error", f"{SUMMARY_FILENAME} not found in {run_folder}")
        if not settings_path.exists():
            return ("Error", f"{FROZEN_SETTINGS_FILENAME} not found in {run_folder}")

        summary = _read_json(summary_path)
        contract = summary.get("contract")
        if not isinstance(contract, Mapping):
            return ("Error", "run_results_summary.json has no contract section")

        # Build runtime objects from the FROZEN settings in the run folder.
        env = runtime_environment_from_settings(settings_path)
        cosmology = env["cosmology"]
        acoustic_config = env["acoustic_config"]
        acoustic_bands = env["acoustic_bands"]
        integration_config = env["integration_config"]

        # Rebuild potential from the frozen settings potential section.
        V, dV_dphi = build_potential_from_settings(env["settings"], cosmology)
        potential_spec = potential_from_settings(env["settings"])
        benchmark_id = str(
            potential_spec.get("benchmark_id")
            or contract.get("benchmark_id")
            or "unnamed"
        )
        route = PotentialRoute(
            benchmark_id=benchmark_id,
            V=V,
            dV_dphi=dV_dphi,
            initial_phi=float(potential_spec["initial_phi"]),
            initial_phi_N=float(potential_spec.get("initial_phi_N", 0.0)),
        )

        # Physics — integrate ONCE; everyone downstream reads trajectory.csv.
        anchor = compute_acoustic_anchor(cosmology, acoustic_config)
        sol = integrate_scalar_route(route, cosmology, integration_config)
        h0x = solve_h0x(route, cosmology, anchor, sol, acoustic_config, acoustic_bands)

        # Dense trajectory on the solver grid (ascending N, z=0 included).
        N = np.sort(np.asarray(sol.t, dtype=float))
        y = sol.sol(N)
        phi, phi_N, H2, raw_E = _eval_route_state(route, cosmology, N, y)
        z = np.expm1(-N)
        raw_E0 = float(evaluate_raw_E_at_z(route, cosmology, sol, 0.0))
        E_X = raw_E / raw_E0
        H_X = h0x.H0_X_kms * E_X
        V_arr = np.asarray(route.V(phi), dtype=float)
        kinetic = 0.5 * H2 * phi_N**2
        w_phi = (kinetic - V_arr) / (kinetic + V_arr)
        Omega_phi = (kinetic + V_arr) / (3.0 * H2)

        rows = _write_trajectory_csv(
            run_folder / TRAJECTORY_FILENAME, N, z, phi, phi_N, E_X, H_X, w_phi, Omega_phi
        )

        # Two-file contract CSVs, evaluated EXACTLY on the low-z export grid via
        # the dense solver (no interpolation). The band export gate decides
        # whether they are written; the H0X verdict above bypasses the gate.
        cfg = _export_config_from_settings(env["settings"])
        gate_accepted = (not cfg["gate_enabled"]) or (h0x.status in cfg["accepted_bands"])
        history_files: dict[str, object] = {"shape": None, "normalized_history": None}
        shape_check = None
        normalization_check = None
        if gate_accepted:
            grid = _export_grid(anchor.z_star, cfg["low_z_step"], cfg["low_z_max"])
            raw_E_grid = np.array(
                [evaluate_raw_E_at_z(route, cosmology, sol, float(zz)) for zz in grid], dtype=float
            )
            raw_E_grid0 = float(evaluate_raw_E_at_z(route, cosmology, sol, 0.0))
            E_X_grid = raw_E_grid / raw_E_grid0
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
            w_phi_grid = np.array(
                [_eval_w_phi_at_z(route, cosmology, sol, float(zz)) for zz in grid], dtype=float
            )
            _write_w_of_z_csv(
                run_folder / W_OF_Z_CSV_FILENAME, grid, w_phi_grid,
                h0x.H0_X_kms, h0x.H0_ref_kms, h0x.delta_X, h0x.status,
            )
            history_files = {
                "shape": SHAPE_CSV_FILENAME,
                "normalized_history": HISTORY_CSV_FILENAME,
                "w_of_z": W_OF_Z_CSV_FILENAME,
            }

        # Enrich the summary (re-read fresh, set our section, atomic write).
        summary = _read_json(summary_path)
        results = summary.setdefault("results", {})
        results["acoustic_validator"] = {
            "status": "OK",
            "script": script_identity(),
            "H0_X_kms": h0x.H0_X_kms,
            "delta_X": h0x.delta_X,
            "band": h0x.status,
            "H0_ref_kms": h0x.H0_ref_kms,
            "Omega_m_X": h0x.Omega_m_X,
            "D_M_X_Mpc": h0x.D_M_X_Mpc,
            "D_M_LCDM_Mpc": h0x.D_M_LCDM_Mpc,
            "acoustic_anchor": {
                "z_star": anchor.z_star,
                "r_s_raw_Mpc": anchor.r_s_raw_Mpc,
                "rs_calibration": anchor.rs_calibration,
                "r_s_Mpc": anchor.r_s_Mpc,
                "D_M_LCDM_Mpc": anchor.D_M_LCDM_Mpc,
                "theta_star": anchor.theta_star,
                "anchor_check": anchor.anchor_check,
                "z_drag": anchor.z_drag,
                "r_drag_Mpc": anchor.r_drag_Mpc,
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
        }
        _atomic_write_json(summary_path, summary)

        if gate_accepted:
            return ("OK", f"acoustic_validator complete: H0_X={h0x.H0_X_kms:.4f} band={h0x.status} (history written)")
        return ("OK", f"acoustic_validator complete: H0_X={h0x.H0_X_kms:.4f} band={h0x.status} (export gate rejected; no history)")

    except TFAError as exc:
        return ("Error", f"{exc.code}: {exc.message}")
    except BaseException as exc:
        return ("Error", f"{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    # CLI entry for the file-based hub: `python tfa_acoustic_validator.py <run_folder>`.
    # Prints one JSON line {"code","desc"} and exits 0 (OK) / 1 (Error).
    import sys

    _run_folder = sys.argv[1] if len(sys.argv) > 1 else "."
    _code, _desc = run_acoustic_validator(_run_folder)
    print(json.dumps({"code": _code, "desc": _desc}))
    sys.exit(0 if _code == "OK" else 1)

