"""
tfa_core - shared core utilities for the TFA package.

This module centralizes the logic every TFA specialist needs, so that no
specialist re-implements the integrator, the settings loader, the potential
builder, the FLRW helpers, the run record, or the encoding policy. It holds the
generic physics (the canonical scalar ODE and the FLRW distance integral); the
acoustic-anchor physics (z_star, r_s, theta matching) deliberately stays in the
acoustic validator.

Design rules honored here:

* No script carries a local settings file. The single unified
  ``tfa-environment-settings.json`` at the package root is located by walking up
  from this file (``_unified_settings_path``).
* ASCII-only source and ASCII-only console output. File writes are UTF-8 without
  a BOM. These remove the recurring codepage / BOM / non-ASCII failures on
  Windows native runtimes. Use ``console_print`` for stdout and
  ``write_text_utf8`` / ``atomic_write_json`` for files.
* The scalar ODE uses the exact logarithmic Hubble derivative
  ``H_N / H = -3/2 (1 + w_eff)`` (theoretical-foundations eq. 14), not the
  numerator-only approximation used by earlier engine builds. The difference is
  numerically negligible; this form is exact and matches the manuscript.

This build is standalone: it is not imported by any other script yet.

Identity: tfa_core 0.1.0 build 0001 (API 0.1, settings schema 0.1).
"""

from __future__ import annotations

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


# ===========================================================================
# Identity
# ===========================================================================

SCRIPT_NAME = "tfa_core"
SCRIPT_VERSION = "0.1.0"
SCRIPT_BUILD = "0001"
SCRIPT_API_VERSION = "0.1"
SETTINGS_SCHEMA_VERSION = "0.1"
TFA_PROJECT_RELEASE = "0.0.4"

ArrayLike = Sequence[float] | np.ndarray
PotentialFn = Callable[[np.ndarray], np.ndarray]


def script_identity() -> Mapping[str, str]:
    """Return module metadata for audit payloads, logs, and release notes."""

    return {
        "tfa_project_release": TFA_PROJECT_RELEASE,
        "script_name": SCRIPT_NAME,
        "script_version": SCRIPT_VERSION,
        "script_build": SCRIPT_BUILD,
        "script_api_version": SCRIPT_API_VERSION,
        "settings_schema_version": SETTINGS_SCHEMA_VERSION,
    }


# ===========================================================================
# Errors
# ===========================================================================

PHASE_ERROR_CODES = {
    "environment": "TFA_ENVIRONMENT_ERROR",
    "potential": "TFA_POTENTIAL_ERROR",
    "ode_integration": "TFA_ODE_INTEGRATION_ERROR",
    "io": "TFA_IO_ERROR",
    "unknown": "TFA_UNKNOWN_ERROR",
}


class TFAError(RuntimeError):
    """Structured runtime error with a stable code and a phase label.

    The ``code`` is a machine-stable identifier; ``phase`` names the pipeline
    stage that failed. ``to_dict`` produces a JSON-serializable payload.
    """

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
        data = {"code": self.code, "phase": self.phase, "message": self.message}
        if self.cause is not None:
            data["cause_type"] = type(self.cause).__name__
            data["cause_message"] = str(self.cause)
        if self.trace_path is not None:
            data["trace_path"] = self.trace_path
        return data


def phase_error(phase: str, exc: BaseException) -> TFAError:
    """Wrap an arbitrary exception in a phase-specific ``TFAError``.

    A ``TFAError`` is returned unchanged so codes are not double-wrapped.
    """

    if isinstance(exc, TFAError):
        return exc
    code = PHASE_ERROR_CODES.get(phase, PHASE_ERROR_CODES["unknown"])
    return TFAError(code=code, message=f"{phase} failed: {exc}", phase=phase, cause=exc)


# ===========================================================================
# Encoding policy (ASCII console, UTF-8-no-BOM files)
# ===========================================================================

# Map the non-ASCII characters that commonly appear in physics text to ASCII so
# console output never triggers a Windows codepage error. Keys are written as
# unicode escapes to keep this source file pure ASCII.
_ASCII_MAP = {
    chr(0x2014): "-",        # em dash
    chr(0x2013): "-",        # en dash
    chr(0x2018): "'",        # left single quote
    chr(0x2019): "'",        # right single quote
    chr(0x201C): '"',        # left double quote
    chr(0x201D): '"',        # right double quote
    chr(0x2026): "...",      # ellipsis
    chr(0x00D7): "x",        # multiplication sign
    chr(0x2248): "~",        # almost equal
    chr(0x2264): "<=",       # less-or-equal
    chr(0x2265): ">=",       # greater-or-equal
    chr(0x2192): "->",       # right arrow
    chr(0x0394): "Delta",    # Delta
    chr(0x039B): "Lambda",   # Lambda
    chr(0x03A9): "Omega",    # Omega
    chr(0x03B1): "alpha",    # alpha
    chr(0x03B8): "theta",    # theta
    chr(0x03C1): "rho",      # rho
    chr(0x03C3): "sigma",    # sigma
    chr(0x03C6): "phi",      # phi
    chr(0x03D5): "phi",      # phi (symbol variant)
}


def ascii_safe(text: object) -> str:
    """Return an ASCII-only rendering of ``text``.

    Known physics symbols are transliterated (Greek letters, dashes, math
    signs); any other non-ASCII character is replaced with ``?``. This is safe
    for stdout on any codepage.
    """

    out = []
    for ch in str(text):
        if ord(ch) < 128:
            out.append(ch)
        elif ch in _ASCII_MAP:
            out.append(_ASCII_MAP[ch])
        else:
            out.append("?")
    return "".join(out)


def console_print(*parts: object) -> None:
    """Print to stdout after forcing ASCII, so no codepage can reject it."""

    print(" ".join(ascii_safe(p) for p in parts))


def write_text_utf8(path: str | Path, text: str) -> None:
    """Write text as UTF-8 *without* a BOM (never utf-8-sig)."""

    with open(Path(path), "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def read_json(path: str | Path) -> dict:
    """Read a JSON file (UTF-8) into a dict."""

    with open(Path(path), "r", encoding="utf-8") as f:
        return json.load(f)


def atomic_write_json(path: str | Path, obj: object) -> None:
    """Write JSON atomically: temp file + fsync + os.replace.

    UTF-8 without a BOM. The temp-then-replace pattern means a reader never sees
    a half-written file even if the process is interrupted.
    """

    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, indent=2, sort_keys=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def utc_timestamp() -> str:
    """Return an ISO-8601 UTC timestamp (millisecond precision)."""

    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


# ===========================================================================
# Settings resolution and typed configuration objects
# ===========================================================================

def _unified_settings_path() -> Path:
    """Locate the single package-level ``tfa-environment-settings.json``.

    Walks up from this file until the settings file is found. No script carries
    a local copy.
    """

    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "tfa-environment-settings.json"
        if candidate.exists():
            return candidate
    # Fall back to the conventional package root relative to this build folder.
    return here.parents[3] / "tfa-environment-settings.json"


DEFAULT_ENVIRONMENT_SETTINGS = _unified_settings_path()


def _require_mapping(parent: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    """Return a required nested mapping from a settings object."""

    value = parent.get(key)
    if not isinstance(value, Mapping):
        raise TFAError(
            code=PHASE_ERROR_CODES["environment"],
            message=f"settings section '{key}' must be an object",
            phase="environment",
        )
    return value


def _tuple_pair(value: Any, key: str) -> tuple[float, float]:
    """Parse a two-number JSON list as an ordered float pair."""

    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise TFAError(
            code=PHASE_ERROR_CODES["environment"],
            message=f"'{key}' must be a two-number array",
            phase="environment",
        )
    if len(value) != 2:
        raise TFAError(
            code=PHASE_ERROR_CODES["environment"],
            message=f"'{key}' must contain exactly two numbers",
            phase="environment",
        )
    lo = float(value[0])
    hi = float(value[1])
    if lo > hi:
        raise TFAError(
            code=PHASE_ERROR_CODES["environment"],
            message=f"'{key}' lower bound must be <= upper bound",
            phase="environment",
        )
    return lo, hi


@dataclass(frozen=True)
class CosmologyContext:
    """Reference FLRW constants used by the ODE and the distance helpers.

    ``Omega_DE`` is filled by flat closure (1 - Omega_m0 - Omega_r0) when given
    as ``None``.
    """

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
    """Candidate-independent early-universe physical-density anchor inputs.

    The anchor *functions* (z_star, r_s) live in the acoustic validator; this
    typed container is shared so every script reads the same values.
    """

    OBH2: float = 0.02237
    OMH2: float = 0.1430
    T0_K: float = 2.7255
    NEFF: float = 3.046
    OGH2: float = 2.4728e-5
    theta_star_target: float = 0.010411
    z_integral_max: float = 1e8
    theta_tolerance: float = 1e-10

    def __post_init__(self) -> None:
        for name in ("OBH2", "OMH2", "T0_K", "NEFF", "OGH2", "theta_star_target"):
            if getattr(self, name) <= 0.0:
                raise ValueError(f"{name} must be positive")


@dataclass(frozen=True)
class AcousticBands:
    """Ordered H0 verdict bands, narrowest first."""

    strict: tuple[float, float] = (66.82, 67.90)
    loose_2s: tuple[float, float] = (66.28, 68.44)
    loose_3s: tuple[float, float] = (65.74, 68.98)

    def classify(self, H0_kms: float) -> str:
        """Classify an H0 value into STRICT / LOOSE_2S / LOOSE_3S / EXCLUDED."""

        if self.strict[0] <= H0_kms <= self.strict[1]:
            return "STRICT"
        if self.loose_2s[0] <= H0_kms <= self.loose_2s[1]:
            return "LOOSE_2S"
        if self.loose_3s[0] <= H0_kms <= self.loose_3s[1]:
            return "LOOSE_3S"
        return "EXCLUDED"


@dataclass(frozen=True)
class IntegrationConfig:
    """Canonical scalar-ODE solver configuration."""

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
            raise ValueError("tfa_core expects z_final = 0")
        if self.rtol <= 0.0 or self.atol <= 0.0:
            raise ValueError("solver tolerances must be positive")
        if self.max_step <= 0.0:
            raise ValueError("max_step must be positive")


@dataclass(frozen=True)
class PotentialRoute:
    """A canonical scalar route: callables plus frozen initial field data."""

    benchmark_id: str
    V: PotentialFn
    dV_dphi: PotentialFn
    initial_phi: float
    initial_phi_N: float = 0.0
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


def load_environment_settings(path: str | Path | None = None) -> Mapping[str, Any]:
    """Read and lightly validate the TFA environment settings JSON."""

    settings_path = Path(path) if path is not None else DEFAULT_ENVIRONMENT_SETTINGS
    settings = read_json(settings_path)
    if not isinstance(settings, Mapping):
        raise TFAError(
            code=PHASE_ERROR_CODES["environment"],
            message="environment settings root must be a JSON object",
            phase="environment",
        )
    _require_mapping(settings, "read_only_hardcoded_defaults")
    _require_mapping(settings, "user_adjustable")
    return settings


def user_adjustable_settings(settings: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return the runtime-consumed ``user_adjustable`` section."""

    return _require_mapping(settings, "user_adjustable")


def cosmology_from_settings(settings: Mapping[str, Any]) -> CosmologyContext:
    """Build a ``CosmologyContext`` from settings."""

    section = _require_mapping(user_adjustable_settings(settings), "cosmology")
    return CosmologyContext(
        Omega_m0=float(section["Omega_m0"]),
        Omega_r0=float(section["Omega_r0"]),
        Omega_DE=None if section.get("Omega_DE") is None else float(section["Omega_DE"]),
        H0_ref_kms=float(section["H0_ref_kms"]),
        c_kms=float(section["c_kms"]),
    )


def acoustic_config_from_settings(settings: Mapping[str, Any]) -> AcousticConfig:
    """Build an ``AcousticConfig`` from settings."""

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
    """Build an ``AcousticBands`` from the configured band block.

    Reads ``h0_bands`` (the policy-neutral key) when present, else falls back to
    the legacy ``planck_h0_bands`` key so older frozen settings keep working.
    The band labels (STRICT / LOOSE_2S / LOOSE_3S) are nesting levels; the
    values define whatever evaluation policy the settings encode.
    """

    user = user_adjustable_settings(settings)
    key = "h0_bands" if "h0_bands" in user else "planck_h0_bands"
    section = _require_mapping(user, key)
    return AcousticBands(
        strict=_tuple_pair(section["strict"], "strict"),
        loose_2s=_tuple_pair(section["loose_2s"], "loose_2s"),
        loose_3s=_tuple_pair(section["loose_3s"], "loose_3s"),
    )


def integration_config_from_settings(settings: Mapping[str, Any]) -> IntegrationConfig:
    """Build an ``IntegrationConfig`` from settings."""

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
    """Return runtime execution / trace controls from settings.

    ``trace_dir`` is resolved relative to the settings file when it is given as a
    relative path, so traces land in the same place regardless of the caller's
    working directory.
    """

    section = _require_mapping(user_adjustable_settings(settings), "execution")
    trace_dir = Path(str(section["trace_dir"]))
    if not trace_dir.is_absolute():
        base = (
            Path(settings_path).resolve().parent
            if settings_path is not None
            else DEFAULT_ENVIRONMENT_SETTINGS.parent
        )
        trace_dir = (base / trace_dir).resolve()
    return {
        "debug_print": bool(section["debug_print"]),
        "trace_enabled": bool(section["trace_enabled"]),
        "trace_dir": trace_dir,
        "trace_filename_prefix": str(section["trace_filename_prefix"]),
        "safe_runner_returns_error_object": bool(section["safe_runner_returns_error_object"]),
    }


def potential_from_settings(settings: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return the ``user_adjustable.potential`` spec mapping."""

    return _require_mapping(user_adjustable_settings(settings), "potential")


# ===========================================================================
# Potential builder (sandboxed expression strings)
# ===========================================================================

def build_potential_from_settings(
    settings: Mapping[str, Any],
    cosmology: CosmologyContext,
) -> tuple[PotentialFn, PotentialFn]:
    """Build ``(V, dV_dphi)`` callables from the potential expression strings.

    The researcher writes ``V_of_phi`` and ``dV_dphi`` as numpy-compatible
    strings. ``Omega_DE`` is injected from the cosmology context; parameters are
    injected from ``potential.parameters``. If ``dV_dphi`` is omitted, a
    central-difference numerical derivative is used.

    Safety: ``__builtins__`` is disabled, so only the explicit math namespace and
    the declared parameters are reachable; arbitrary Python cannot run. Both
    expressions are smoke-tested at ``phi = 1.0`` so syntax errors surface here,
    not inside the ODE.
    """

    spec = potential_from_settings(settings)
    V_expr = str(spec.get("V_of_phi", "")).strip()
    dV_expr = str(spec.get("dV_dphi", "")).strip()
    raw_params = spec.get("parameters", {})
    if not isinstance(raw_params, Mapping):
        raise TFAError(
            code=PHASE_ERROR_CODES["potential"],
            message="potential.parameters must be a JSON object",
            phase="potential",
        )
    if not V_expr:
        raise TFAError(
            code=PHASE_ERROR_CODES["potential"],
            message="potential.V_of_phi is required",
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

        V(np.asarray([1.0]))  # smoke test
    except TFAError:
        raise
    except Exception as exc:
        raise TFAError(
            code=PHASE_ERROR_CODES["potential"],
            message=f"V_of_phi expression failed: {exc}",
            phase="potential",
            cause=exc,
        ) from exc

    if dV_expr:
        try:
            def dV_dphi(phi: np.ndarray) -> np.ndarray:
                phi = np.asarray(phi, dtype=float)
                return np.asarray(eval(dV_expr, {**namespace, "phi": phi}), dtype=float)  # noqa: S307

            dV_dphi(np.asarray([1.0]))  # smoke test
        except TFAError:
            raise
        except Exception as exc:
            raise TFAError(
                code=PHASE_ERROR_CODES["potential"],
                message=f"dV_dphi expression failed: {exc}",
                phase="potential",
                cause=exc,
            ) from exc
    else:
        _h = 1e-6

        def dV_dphi(phi: np.ndarray) -> np.ndarray:
            phi = np.asarray(phi, dtype=float)
            return (V(phi + _h) - V(phi - _h)) / (2.0 * _h)

    return V, dV_dphi


# ===========================================================================
# Canonical scalar ODE (generic; the acoustic anchor stays in the validator)
# ===========================================================================

def eval_route_state(
    route: PotentialRoute,
    cosmology: CosmologyContext,
    N_arr: ArrayLike,
    y_arr: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Evaluate (phi, phi_N, H2, raw_E) from solver state at e-folds ``N_arr``.

    ``raw_E`` is the dimensionless expansion H/H0_ref. It is NOT normalized to
    1 at z=0; normalization to E_X(0)=1 is an acoustic-validator step.

    Units follow the reduced-Planck convention with M_Pl = 1, where the matter
    and radiation terms appear as ``3 * Omega * a^-n`` and the critical density
    today is 3.
    """

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
        raise TFAError(
            code=PHASE_ERROR_CODES["ode_integration"],
            message="phi_N^2 >= 6: kinetic energy exceeds the canonical bound",
            phase="ode_integration",
        )
    H2 = rhs_fried / denom
    return phi, phi_N, H2, np.sqrt(H2)


def make_scalar_rhs(
    route: PotentialRoute,
    cosmology: CosmologyContext,
) -> Callable[[float, Sequence[float]], list[float]]:
    """Build the canonical scalar-field RHS in e-fold time ``N = ln a``.

    State is ``y = [phi, phi_N]`` with ``phi_N = dphi/dN``. The logarithmic
    Hubble derivative uses the exact total effective equation of state,
    ``H_N / H = -3/2 (1 + w_eff)`` with
    ``w_eff = (rho_r/3 + p_phi) / rho_total`` (theoretical-foundations eq. 14).
    """

    Om = cosmology.Omega_m0
    Or = cosmology.Omega_r0

    def rhs(N: float, y: Sequence[float]) -> list[float]:
        phi = np.asarray([y[0]], dtype=float)
        phi_N = float(y[1])
        a = np.exp(N)
        V = float(route.V(phi)[0])
        dV = float(route.dV_dphi(phi)[0])

        rho_m = 3.0 * Om * a**-3
        rho_r = 3.0 * Or * a**-4
        rhs_fried = rho_m + rho_r + V
        denom = 3.0 - 0.5 * phi_N**2
        if denom <= 0.0:
            raise TFAError(
                code=PHASE_ERROR_CODES["ode_integration"],
                message="phi_N^2 >= 6: kinetic energy exceeds the canonical bound",
                phase="ode_integration",
            )
        H2 = rhs_fried / denom

        # Exact H_N/H from the total effective equation of state.
        p_phi = 0.5 * H2 * phi_N**2 - V
        rho_total = 3.0 * H2
        p_total = rho_r / 3.0 + p_phi
        w_eff = p_total / rho_total
        dlnH = -1.5 * (1.0 + w_eff)

        phi_NN = -(3.0 + dlnH) * phi_N - dV / H2
        return [phi_N, phi_NN]

    return rhs


def integrate_scalar_route(
    route: PotentialRoute,
    cosmology: CosmologyContext,
    config: IntegrationConfig,
) -> object:
    """Integrate one canonical scalar route from ``z_ini`` to ``z = 0``.

    Returns the dense solver object (``scipy`` OdeResult). ``dense_output`` must
    be enabled so callers can evaluate the trajectory at arbitrary redshift.
    """

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
        raise TFAError(
            code=PHASE_ERROR_CODES["ode_integration"],
            message=f"ODE failed for {route.benchmark_id}: {sol.message}",
            phase="ode_integration",
        )
    if sol.sol is None:
        raise TFAError(
            code=PHASE_ERROR_CODES["ode_integration"],
            message="dense ODE solution is required",
            phase="ode_integration",
        )
    return sol


def evaluate_raw_E_at_z(
    route: PotentialRoute,
    cosmology: CosmologyContext,
    sol: object,
    z: float,
) -> float:
    """Evaluate the raw (un-normalized) dimensionless expansion at one z."""

    if z < 0.0:
        raise ValueError("z must be non-negative")
    N = np.asarray([-np.log1p(z)], dtype=float)
    y = sol.sol(N)
    _phi, _phi_N, _H2, raw_E = eval_route_state(route, cosmology, N, y)
    return float(raw_E[0])


# ===========================================================================
# FLRW helpers
# ===========================================================================

def H_lcdm_kms(z: float | np.ndarray, cosmology: CosmologyContext) -> np.ndarray:
    """Reference flat-LCDM H(z) in km/s/Mpc."""

    z_arr = np.asarray(z, dtype=float)
    E2 = (
        cosmology.Omega_m0 * (1.0 + z_arr) ** 3
        + cosmology.Omega_r0 * (1.0 + z_arr) ** 4
        + cosmology.Omega_DE
    )
    return cosmology.H0_ref_kms * np.sqrt(E2)


def comoving_distance_Mpc(
    H_kms: Callable[[float], float],
    z_max: float,
    cosmology: CosmologyContext,
    epsabs: float = 1e-4,
    epsrel: float = 1e-8,
) -> float:
    """Comoving distance ``D_M(z_max) = integral_0^z_max c / H(z) dz`` in Mpc.

    ``H_kms`` is any callable returning H(z) in km/s/Mpc.
    """

    value, _ = quad(
        lambda z: cosmology.c_kms / H_kms(float(z)),
        0.0,
        z_max,
        limit=500,
        epsabs=epsabs,
        epsrel=epsrel,
    )
    return float(value)


# ===========================================================================
# Run trace (JSON-lines, UTF-8 no BOM)
# ===========================================================================

class RunTrace:
    """A JSON-lines phase trace for one run.

    Records route id, phase names, status, durations, and error metadata. It
    intentionally never writes physics arrays or results. Lines are UTF-8
    without a BOM.
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
            filename = f"{filename_prefix}-core-{route_id}-{self.run_id}.jsonl"
            self.trace_path = directory / filename
            self.event("run", "START", "tfa_core run started")

    def event(
        self,
        phase: str,
        status: str,
        message: str = "",
        code: str | None = None,
        duration_s: float | None = None,
    ) -> None:
        if self.debug_print:
            console_print(f"[tfa_core] {phase}: {status} {message}".strip())
        if not self.enabled or self.trace_path is None:
            return
        record: dict[str, object] = {
            "timestamp_utc": utc_timestamp(),
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
        with open(self.trace_path, "a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(record, sort_keys=True) + "\n")

    def run_phase(self, phase: str, func: Callable[[], Any]) -> Any:
        """Run one named phase with START / PASS / ERROR trace events."""

        start = time.perf_counter()
        self.event(phase, "START")
        try:
            value = func()
        except BaseException as exc:
            err = phase_error(phase, exc)
            self.event(phase, "ERROR", err.message, err.code, time.perf_counter() - start)
            raise err from exc
        self.event(phase, "PASS", duration_s=time.perf_counter() - start)
        return value

    def close(self, status: str, message: str = "") -> None:
        self.event("run", status, message)


__all__ = [
    "SCRIPT_NAME", "SCRIPT_VERSION", "SCRIPT_BUILD", "script_identity",
    "TFAError", "PHASE_ERROR_CODES", "phase_error",
    "ascii_safe", "console_print", "write_text_utf8", "read_json",
    "atomic_write_json", "utc_timestamp",
    "CosmologyContext", "AcousticConfig", "AcousticBands", "IntegrationConfig",
    "PotentialRoute",
    "_unified_settings_path", "DEFAULT_ENVIRONMENT_SETTINGS",
    "load_environment_settings", "user_adjustable_settings",
    "cosmology_from_settings", "acoustic_config_from_settings",
    "acoustic_bands_from_settings", "integration_config_from_settings",
    "execution_settings_from_settings",
    "potential_from_settings", "build_potential_from_settings",
    "eval_route_state", "make_scalar_rhs", "integrate_scalar_route",
    "evaluate_raw_E_at_z", "H_lcdm_kms", "comoving_distance_Mpc",
    "RunTrace",
]
