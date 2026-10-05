"""Real native misuse observations plus strict prospective assessment receipts."""
from __future__ import annotations

import copy
import hashlib
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from model_release_assurance.production_assessment import probes as p
from model_release_assurance.production_assessment import contracts as c
from model_release_assurance.production_adapters import native
from model_release_assurance.production_delivery.rehearsal import DeliveryFixture
from model_release_assurance.production_identity.policy import PermissionDenied
from model_release_assurance.production_trust.signer import FixtureTokenIssuer


class AssessmentProbeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="mra-assessment-probes-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def successful_structure(self):
        return {"schema": "mra-local-adversarial-probes/v1", "status": "passed", "plan_sha256": c.digest(p.probe_plan()),
            "probes": [{"name": name, "status": "passed", "expected_denials": list(p._EXPECTED[name]),
                        "observed_denials": list(p._OBSERVED[name]), "observations": copy.deepcopy(p._OBSERVATIONS[name])}
                        for name in p.PROBE_NAMES], "summary": dict(p._SUMMARY),
            "evidence_hashes": {key: "a" * 64 for key in ("candidate_sha256", "policy_sha256", "binding_sha256",
                "final_delivery_head_sha256", "positive_chunks_sha256")}, **c.FLAGS}

    def test_actual_fresh_native_probes_are_prospective_nonvacuous_and_redacted(self):
        output = self.root / "actual"
        fixtures, issued, fit_calls = [], [], []
        original_fit, original_issue = native.run_native, FixtureTokenIssuer.issue
        def fixture_factory(root):
            fixture = DeliveryFixture(root)
            fixtures.append(fixture)
            return fixture
        def record_token(issuer, *args, **kwargs):
            token = original_issue(issuer, *args, **kwargs)
            issued.append(token)
            return token
        def fit(*args, **kwargs):
            self.assertEqual((output / "plan.json").read_bytes(), c.canonical_bytes(p.probe_plan()))
            fixture = fixtures[0]
            campaign = fixture.review_fixture.store.get("case-a", guard=fixture.review_fixture.clock)["campaigns"][fixture.campaign_id]
            self.assertEqual(campaign["state"], "started")
            self.assertIsNotNone(campaign["policy_approval"])
            self.assertIsNotNone(campaign["start"])
            self.assertIsNone(campaign["completion"])
            fit_calls.append(True)
            return original_fit(*args, **kwargs)
        frozen = [Path(native.__file__), Path(DeliveryFixture.__module__.replace('.', '/'))]
        native_before = hashlib.sha256(Path(native.__file__).read_bytes()).hexdigest()
        with mock.patch.object(p, "DeliveryFixture", side_effect=fixture_factory), \
                mock.patch.object(native, "run_native", side_effect=fit), \
                mock.patch.object(FixtureTokenIssuer, "issue", record_token):
            result = p.run_probes(output, profile="local_public_fixture")
        self.assertEqual(len(fit_calls), 1)
        self.assertEqual(result, p.validate_result(result))
        self.assertEqual(result["summary"]["positive_controls"], 4)
        self.assertEqual(result["summary"]["durable_admissions"], 6)
        self.assertEqual(result["summary"]["expected_exception_denials"], 19)
        self.assertFalse(result["summary"]["external_sacro_tested"])
        self.assertFalse(result["summary"]["recipient_receipt_verified"])
        self.assertEqual([row["name"] for row in result["probes"]], list(p.PROBE_NAMES))
        self.assertTrue(all(row["status"] == "passed" for row in result["probes"]))
        raw_result = c.canonical_bytes(result)
        self.assertEqual((output / "probes.json").read_bytes(), raw_result)
        self.assertNotIn(b"person-", raw_result)
        self.assertNotIn(str(self.root).encode(), raw_result)
        self.assertEqual(native_before, hashlib.sha256(Path(native.__file__).read_bytes()).hexdigest())
        self.assertTrue(issued)
        for path in output.rglob("*"):
            if path.is_file():
                raw = path.read_bytes()
                self.assertNotIn(b"PRIVATE KEY", raw)
                for token in issued:
                    self.assertNotIn(token.encode(), raw)
        self.assertEqual(fixtures[0].now, 1001)

    def test_production_refused_before_fixture_or_output_creation(self):
        with mock.patch.object(p, "DeliveryFixture") as factory:
            for profile in ("agency_private_cloud", "production", None, True):
                with self.subTest(profile=profile), self.assertRaises(c.AssessmentError):
                    p.run_probes(self.root / "absent", profile=profile)
            with self.assertRaises(c.AssessmentError): p.run_probes(self.root / "absent")
        factory.assert_not_called()
        self.assertFalse((self.root / "absent").exists())

    def test_output_is_new_and_does_not_overwrite_existing_evidence(self):
        output = self.root / "existing"
        output.mkdir()
        (output / "plan.json").write_bytes(b"preserve")
        with mock.patch.object(p, "DeliveryFixture") as factory, self.assertRaises(ValueError):
            p.run_probes(output, profile="local_public_fixture")
        factory.assert_not_called()
        self.assertEqual((output / "plan.json").read_bytes(), b"preserve")

    def test_plan_is_deterministic_owned_and_prevents_workload_switches(self):
        first = p.probe_plan()
        first["probes"][0]["name"] = "replacement"
        first["max_rows"] = 4096
        second = p.probe_plan()
        self.assertEqual(second["max_rows"], 128)
        self.assertEqual(second["probes"][0]["name"], p.PROBE_NAMES[0])
        self.assertEqual(c.digest(second), c.digest(p.probe_plan()))
        self.assertEqual(second["activation_ttl_seconds"], 30)
        self.assertEqual(second["grant_ttl_seconds"], 20)
        self.assertEqual(second["expiry_probe_clock_advance_seconds"], 1)

    def test_unrelated_exception_and_success_cannot_count_as_denial(self):
        def crash(): raise RuntimeError("unrelated dependency error")
        with self.assertRaises(RuntimeError): p._denial(crash, (PermissionDenied,))
        with self.assertRaises(c.AssessmentError): p._denial(lambda: None, (PermissionDenied,))
        def reject(): raise PermissionDenied("expected")
        self.assertEqual(p._denial(reject, (PermissionDenied,)), "current_scope_denied")

    def test_denial_after_writer_or_phantom_admission_is_not_passing(self):
        def reject(): raise PermissionDenied("expected")
        fixture = SimpleNamespace(gateway=None,
            review_fixture=SimpleNamespace(store=mock.Mock(), clock=lambda: 1000))
        fixture.review_fixture.store.get.return_value = {"head_sha256": "a" * 64}
        observed = p._Probes(fixture)
        before = {"pin": {"sequence": 1}, "admissions": {}}
        for after, calls in (({"pin": {"sequence": 2}, "admissions": {"new": {}}}, 0), (before, 1)):
            with self.subTest(calls=calls), mock.patch.object(observed, "state", side_effect=[before, after]), \
                    self.assertRaises(c.AssessmentError):
                observed.rejected(reject, (PermissionDenied,), writer=SimpleNamespace(calls=calls))
        self.assertEqual(observed.denials, 0)

    def test_result_rejects_missing_reordered_duplicate_or_unexpected_probes(self):
        for mutation in ("missing", "reordered", "duplicate", "unexpected"):
            result = self.successful_structure()
            if mutation == "missing": result["probes"].pop()
            if mutation == "reordered": result["probes"].reverse()
            if mutation == "duplicate": result["probes"][-1] = copy.deepcopy(result["probes"][0])
            if mutation == "unexpected": result["probes"][0]["name"] = "external_penetration_passed"
            with self.subTest(mutation=mutation), self.assertRaises(c.AssessmentError): p.validate_result(result)

    def test_result_requires_expected_control_errors_not_arbitrary_crash_codes(self):
        for key, replacement in (("expected_denials", ["exception"]), ("observed_denials", ["runtime_failure"]),
                                 ("observed_denials", []), ("status", "failed")):
            result = self.successful_structure()
            result["probes"][0][key] = replacement
            with self.subTest(key=key, replacement=replacement), self.assertRaises(c.AssessmentError): p.validate_result(result)

    def test_false_positive_controls_changed_plan_and_non_authorizing_flags_fail(self):
        for mutate in (lambda r: r["summary"].update(positive_controls=0),
                       lambda r: r.update(plan_sha256="b" * 64),
                       lambda r: r.update(can_clear=True),
                       lambda r: r["summary"].update(external_sacro_tested=True),
                       lambda r: r["probes"][3]["observations"].update(writer_calls=1),
                       lambda r: r["summary"].update(durable_admissions=0)):
            result = self.successful_structure()
            mutate(result)
            with self.assertRaises(c.AssessmentError): p.validate_result(result)

    def test_boolean_count_aliases_unknown_fields_nonfinite_and_bad_hashes_fail(self):
        for mutate in (lambda r: r["summary"].update(fresh_native_runs=True),
                       lambda r: r["probes"][0]["observations"].update(rejected_output_created=0),
                       lambda r: r["summary"].update(private_note="person-secret"),
                       lambda r: r.update(private_path="C:/private"),
                       lambda r: r["summary"].update(max_rows=float('nan')),
                       lambda r: r["evidence_hashes"].update(candidate_sha256="A" * 64)):
            result = self.successful_structure()
            mutate(result)
            with self.assertRaises(c.AssessmentError): p.validate_result(result)

    def test_result_returns_owned_structure(self):
        original = self.successful_structure()
        validated = p.validate_result(original)
        original["probes"][0]["observations"]["policy_approved_before_fit"] = False
        self.assertTrue(validated["probes"][0]["observations"]["policy_approved_before_fit"])


if __name__ == "__main__":
    unittest.main()
