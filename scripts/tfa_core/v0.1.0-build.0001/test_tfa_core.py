"""
Unit tests for tfa_core 0.1.0 build 0001.

Run from this folder:
    python -m unittest test_tfa_core -v
or:
    python test_tfa_core.py

The suite covers: identity, the encoding policy (ASCII console + UTF-8-no-BOM
files), the typed config objects and their validation, settings resolution and
the from-settings builders against the real package settings file, the sandboxed
potential builder, the canonical scalar ODE (including the exact frozen-field =
LCDM identity), the FLRW distance helper, JSON round-trip, and the run trace.
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tfa_core as core  # noqa: E402


def _build_route(cosmo, V_expr, dV_expr, phi0=1.0, phiN0=0.0, params=None):
    settings = {
        "read_only_hardcoded_defaults": {},
        "user_adjustable": {
            "potential": {
                "benchmark_id": "TEST",
                "V_of_phi": V_expr,
                "dV_dphi": dV_expr,
                "parameters": params or {},
                "initial_phi": phi0,
                "initial_phi_N": phiN0,
            }
        },
    }
    V, dV = core.build_potential_from_settings(settings, cosmo)
    return core.PotentialRoute(
        benchmark_id="TEST", V=V, dV_dphi=dV, initial_phi=phi0, initial_phi_N=phiN0
    )


class TestIdentity(unittest.TestCase):
    def test_identity(self):
        ident = core.script_identity()
        self.assertEqual(ident["script_name"], "tfa_core")
        self.assertEqual(ident["script_version"], "0.1.0")
        self.assertEqual(ident["script_build"], "0001")


class TestEncoding(unittest.TestCase):
    def test_ascii_safe_transliterates(self):
        # em dash, Greek, math signs -> ASCII
        raw = chr(0x2014) + "x " + chr(0x03A9) + chr(0x03C6) + " " + chr(0x2265)
        out = core.ascii_safe(raw)
        self.assertTrue(all(ord(c) < 128 for c in out))
        self.assertIn("Omega", out)
        self.assertIn("phi", out)
        self.assertIn(">=", out)
        self.assertIn("-", out)

    def test_ascii_safe_unknown_becomes_question(self):
        self.assertEqual(core.ascii_safe(chr(0x2603)), "?")  # snowman

    def test_write_text_utf8_no_bom(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "t.txt"
            core.write_text_utf8(p, "hello " + chr(0x03A9))
            data = p.read_bytes()
            self.assertNotEqual(data[:3], b"\xef\xbb\xbf")  # no BOM
            self.assertEqual(data.decode("utf-8")[:5], "hello")


class TestCosmology(unittest.TestCase):
    def test_flat_closure(self):
        c = core.CosmologyContext(Omega_m0=0.3152, Omega_r0=9.18e-5, Omega_DE=None)
        self.assertAlmostEqual(c.Omega_DE, 1.0 - 0.3152 - 9.18e-5, places=12)

    def test_explicit_omega_de(self):
        c = core.CosmologyContext(Omega_m0=0.3, Omega_r0=1e-4, Omega_DE=0.7)
        self.assertEqual(c.Omega_DE, 0.7)

    def test_validation(self):
        with self.assertRaises(ValueError):
            core.CosmologyContext(Omega_m0=-0.1)
        with self.assertRaises(ValueError):
            core.CosmologyContext(Omega_m0=0.6, Omega_r0=0.5)  # Omega_DE <= 0


class TestBands(unittest.TestCase):
    def test_classify(self):
        b = core.AcousticBands(
            strict=(66.82, 67.90), loose_2s=(66.28, 68.44), loose_3s=(65.74, 68.98)
        )
        self.assertEqual(b.classify(67.36), "STRICT")
        self.assertEqual(b.classify(66.82), "STRICT")   # boundary inclusive
        self.assertEqual(b.classify(68.20), "LOOSE_2S")
        self.assertEqual(b.classify(65.80), "LOOSE_3S")
        self.assertEqual(b.classify(60.0), "EXCLUDED")
        self.assertEqual(b.classify(70.0), "EXCLUDED")


class TestSettingsResolution(unittest.TestCase):
    def test_unified_path_found(self):
        p = core._unified_settings_path()
        self.assertTrue(p.exists(), f"settings not found at {p}")
        self.assertEqual(p.name, "tfa-environment-settings.json")

    def test_load_and_builders(self):
        s = core.load_environment_settings()
        cosmo = core.cosmology_from_settings(s)
        self.assertGreater(cosmo.H0_ref_kms, 0.0)
        self.assertGreater(cosmo.Omega_DE, 0.0)
        ac = core.acoustic_config_from_settings(s)
        self.assertGreater(ac.OMH2, 0.0)
        bands = core.acoustic_bands_from_settings(s)
        self.assertIn(bands.classify(cosmo.H0_ref_kms),
                      ("STRICT", "LOOSE_2S", "LOOSE_3S", "EXCLUDED"))
        intc = core.integration_config_from_settings(s)
        self.assertEqual(intc.z_final, 0.0)
        exe = core.execution_settings_from_settings(s, core.DEFAULT_ENVIRONMENT_SETTINGS)
        self.assertIn("trace_dir", exe)
        self.assertTrue(Path(exe["trace_dir"]).is_absolute())
        self.assertIsInstance(exe["trace_enabled"], bool)

    def test_missing_section_raises(self):
        with self.assertRaises(core.TFAError):
            core.cosmology_from_settings(
                {"user_adjustable": {}, "read_only_hardcoded_defaults": {}}
            )


class TestPotentialBuilder(unittest.TestCase):
    def setUp(self):
        self.cosmo = core.CosmologyContext()

    def test_wli_form(self):
        V, dV = core.build_potential_from_settings(
            {
                "read_only_hardcoded_defaults": {},
                "user_adjustable": {
                    "potential": {
                        "V_of_phi": "3 * Omega_DE * (phi_inf / phi) ** alpha",
                        "dV_dphi": "-alpha * 3 * Omega_DE * (phi_inf / phi) ** alpha / phi",
                        "parameters": {"alpha": 1.0, "phi_inf": 1.3},
                    }
                },
            },
            self.cosmo,
        )
        phi = np.asarray([1.3])
        expect_V = 3 * self.cosmo.Omega_DE * (1.3 / 1.3) ** 1.0
        self.assertAlmostEqual(float(V(phi)[0]), expect_V, places=10)
        expect_dV = -1.0 * 3 * self.cosmo.Omega_DE * (1.3 / 1.3) ** 1.0 / 1.3
        self.assertAlmostEqual(float(dV(phi)[0]), expect_dV, places=10)

    def test_numerical_derivative_fallback(self):
        V, dV = core.build_potential_from_settings(
            {
                "read_only_hardcoded_defaults": {},
                "user_adjustable": {
                    "potential": {"V_of_phi": "phi**2", "dV_dphi": "", "parameters": {}}
                },
            },
            self.cosmo,
        )
        self.assertAlmostEqual(float(dV(np.asarray([3.0]))[0]), 6.0, places=4)

    def test_sandbox_blocks_builtins(self):
        with self.assertRaises(core.TFAError):
            core.build_potential_from_settings(
                {
                    "read_only_hardcoded_defaults": {},
                    "user_adjustable": {
                        "potential": {"V_of_phi": "__import__('os').getcwd()", "parameters": {}}
                    },
                },
                self.cosmo,
            )

    def test_missing_V_raises(self):
        with self.assertRaises(core.TFAError):
            core.build_potential_from_settings(
                {
                    "read_only_hardcoded_defaults": {},
                    "user_adjustable": {"potential": {"V_of_phi": "", "parameters": {}}},
                },
                self.cosmo,
            )


class TestScalarODE(unittest.TestCase):
    def setUp(self):
        self.cosmo = core.CosmologyContext(
            Omega_m0=0.3152, Omega_r0=9.18e-5, H0_ref_kms=67.36
        )
        self.intc = core.IntegrationConfig(z_ini=1e4, max_step=0.02)

    def test_frozen_field_reproduces_lcdm(self):
        # A frozen field with V = 3*Omega_DE is exactly LCDM: raw_E(z) = E_lcdm(z).
        route = _build_route(self.cosmo, "3*Omega_DE + 0*phi", "0*phi", phi0=1.0, phiN0=0.0)
        sol = core.integrate_scalar_route(route, self.cosmo, self.intc)
        for z in (0.0, 0.5, 1.0, 5.0, 100.0):
            raw_E = core.evaluate_raw_E_at_z(route, self.cosmo, sol, z)
            lcdm = float(core.H_lcdm_kms(z, self.cosmo)) / self.cosmo.H0_ref_kms
            self.assertAlmostEqual(raw_E / lcdm, 1.0, places=9,
                                   msg=f"mismatch at z={z}")

    def test_raw_E_at_zero_is_one_for_frozen(self):
        route = _build_route(self.cosmo, "3*Omega_DE + 0*phi", "0*phi")
        sol = core.integrate_scalar_route(route, self.cosmo, self.intc)
        self.assertAlmostEqual(core.evaluate_raw_E_at_z(route, self.cosmo, sol, 0.0),
                               1.0, places=9)

    def test_kinetic_bound_raises(self):
        route = _build_route(self.cosmo, "3*Omega_DE + 0*phi", "0*phi")
        # phi_N^2 = 9 >= 6 -> denom <= 0 -> TFAError
        with self.assertRaises(core.TFAError):
            core.eval_route_state(route, self.cosmo,
                                  np.asarray([0.0]),
                                  np.asarray([[1.0], [3.0]]))

    def test_negative_z_rejected(self):
        route = _build_route(self.cosmo, "3*Omega_DE + 0*phi", "0*phi")
        sol = core.integrate_scalar_route(route, self.cosmo, self.intc)
        with self.assertRaises(ValueError):
            core.evaluate_raw_E_at_z(route, self.cosmo, sol, -1.0)


class TestFLRW(unittest.TestCase):
    def setUp(self):
        self.cosmo = core.CosmologyContext()

    def test_comoving_distance_sane(self):
        D = core.comoving_distance_Mpc(
            lambda z: float(core.H_lcdm_kms(z, self.cosmo)), 1.0, self.cosmo
        )
        # D_C(z=1) for this cosmology is around 3300 Mpc.
        self.assertGreater(D, 3000.0)
        self.assertLess(D, 3600.0)

    def test_distance_monotonic(self):
        d1 = core.comoving_distance_Mpc(lambda z: float(core.H_lcdm_kms(z, self.cosmo)), 0.5, self.cosmo)
        d2 = core.comoving_distance_Mpc(lambda z: float(core.H_lcdm_kms(z, self.cosmo)), 1.5, self.cosmo)
        self.assertGreater(d2, d1)


class TestIO(unittest.TestCase):
    def test_json_roundtrip_no_bom(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.json"
            obj = {"a": 1, "b": [1, 2, 3], "c": "ok"}
            core.atomic_write_json(p, obj)
            data = p.read_bytes()
            self.assertNotEqual(data[:3], b"\xef\xbb\xbf")  # no BOM
            self.assertEqual(core.read_json(p), obj)
            self.assertFalse((p.with_suffix(".json.tmp")).exists())  # temp cleaned


class TestRunTrace(unittest.TestCase):
    def test_trace_writes_jsonlines(self):
        with tempfile.TemporaryDirectory() as d:
            tr = core.RunTrace(route_id="R1", enabled=True, trace_dir=d)
            tr.event("phaseA", "START")
            tr.run_phase("phaseB", lambda: 42)
            tr.close("PASS", "done")
            self.assertIsNotNone(tr.trace_path)
            lines = Path(tr.trace_path).read_text(encoding="utf-8").strip().splitlines()
            self.assertGreaterEqual(len(lines), 4)
            for line in lines:
                rec = json.loads(line)
                self.assertIn("phase", rec)
                self.assertIn("status", rec)

    def test_run_phase_wraps_error(self):
        with tempfile.TemporaryDirectory() as d:
            tr = core.RunTrace(route_id="R2", enabled=True, trace_dir=d)

            def boom():
                raise ValueError("kaboom")

            with self.assertRaises(core.TFAError):
                tr.run_phase("ode_integration", boom)


class TestErrors(unittest.TestCase):
    def test_to_dict(self):
        e = core.TFAError(code="C", message="m", phase="potential")
        d = e.to_dict()
        self.assertEqual(d["code"], "C")
        self.assertEqual(d["phase"], "potential")

    def test_phase_error_passthrough(self):
        e = core.TFAError(code="C", message="m", phase="io")
        self.assertIs(core.phase_error("io", e), e)

    def test_phase_error_wraps(self):
        wrapped = core.phase_error("ode_integration", ValueError("x"))
        self.assertIsInstance(wrapped, core.TFAError)
        self.assertEqual(wrapped.code, core.PHASE_ERROR_CODES["ode_integration"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
