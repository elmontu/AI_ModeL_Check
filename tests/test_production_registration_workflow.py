"""Prospective fit barriers, current custody, immutable history and no import path."""
from __future__ import annotations
import copy
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

from model_release_assurance.production_registration import workflow as module
from model_release_assurance.production_registration.contracts import digest
from model_release_assurance.production_registration.store import RegistrationStore
from model_release_assurance.production_evidence.ledger import ReplayLedger
from model_release_assurance.production_evidence.signing import MemoryFixtureEvidenceSigner
from model_release_assurance.production_trust.registry import FixtureTrustRegistry, TrustProfile


class ProspectiveWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="prospective-workflow-"); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.output = self.root / "run"; self.now = [1000]
        self.profile = TrustProfile("agency", "public_fixture", "https://registration.invalid", "urn:registration", "worker_evidence")
        self.registry = FixtureTrustRegistry(now=lambda: self.now[0], fresh_until=1300)
        self.signer = MemoryFixtureEvidenceSigner(self.profile, "worker", "key", 1000, 1300)
        self.registry.enroll(self.signer.registration, expected_revision=self.registry.revision)
        self.store = RegistrationStore.create(self.root / "registrations")
        self.ledger = ReplayLedger.create(self.root / "evidence")
        self.workflow = module.LocalRegistrationWorkflow(self.registry, self.signer, self.store, self.ledger)

    def run_fixture(self, **kwargs):
        values = dict(output=self.output, agency_id="agency", project_id="project", case_id="case", max_rows=128)
        values.update(kwargs)
        return self.workflow.run("sklearn-wine", **values)

    def record(self, result):
        return self.store.get(result["registration_id"], guard=lambda: self.now[0])

    def test_registration_and_start_are_durable_before_first_scaler_fit(self):
        from sklearn.preprocessing import StandardScaler
        original = StandardScaler.fit; seen = []
        def check(scaler, *args, **kwargs):
            registration = json.loads((self.output / "registration.json").read_bytes())
            reopened = RegistrationStore.open(self.store.root, self.store.store_id)
            record = reopened.get(registration["registration_id"], guard=lambda: self.now[0])
            self.assertEqual(record["state"], "training")
            self.assertEqual(record["registration_sha256"], digest(registration))
            self.assertTrue((self.output / "training-start.json").exists())
            self.assertFalse((self.output / "native/candidate.json").exists())
            seen.append(registration["registration_id"])
            return original(scaler, *args, **kwargs)
        with patch.object(StandardScaler, "fit", check): result = self.run_fixture()
        self.assertEqual(result["status"], "review_recorded", result)
        self.assertEqual(len(seen), 1)
        record = self.record(result)
        self.assertEqual(record["completion"]["review"], result["review"])
        for key, value in module.FLAGS.items(): self.assertIs(result[key], value)
        self.assertIs(result["review"]["production_authorized"], False)

    def test_output_and_history_refuse_overwrite_but_new_registration_retains_prior(self):
        first = self.run_fixture(); self.assertEqual(first["status"], "review_recorded", first)
        before = (self.output / "result.json").read_bytes()
        with self.assertRaises(FileExistsError): self.run_fixture()
        self.assertEqual(before, (self.output / "result.json").read_bytes())
        second = self.run_fixture(output=self.root / "second", case_id="renamed-case")
        self.assertEqual(second["status"], "review_recorded", second)
        self.assertNotEqual(first["registration_id"], second["registration_id"])
        history = self.store.history("agency", "project", guard=lambda: self.now[0])
        self.assertEqual(history["local_registrations"], 2)
        self.assertEqual(history["external_history"], "unknown")
        self.assertIs(history["privacy_accounting_supported"], False)

    def test_arbitrary_model_imports_and_parent_parameters_have_no_entry_point(self):
        for argument in ("model_path", "artifact", "estimator", "parents", "epsilon", "privacy_budget"):
            with self.subTest(argument=argument), patch.object(module, "load_profile") as loader, self.assertRaises(TypeError):
                self.run_fixture(**{argument: "untrusted.joblib"})
            loader.assert_not_called()
        self.assertFalse(self.output.exists())
        for profile in ("../private", "private", "openml-61-v1", "mnist", ""):
            with self.subTest(profile=profile), self.assertRaises(ValueError):
                self.workflow.run(profile, output=self.output, agency_id="agency", project_id="project", case_id="case")
        self.assertFalse(self.output.exists())

    def test_foreign_agency_is_refused_before_loading_or_output(self):
        with patch.object(module, "load_profile") as loader, self.assertRaises(ValueError): self.run_fixture(agency_id="other")
        loader.assert_not_called(); self.assertFalse(self.output.exists())

    def test_source_change_after_fitting_fails_and_is_retained(self):
        active = [False]; load = module.load_profile; train = module.native.run_native
        def changed(*args, **kwargs):
            data = load(*args, **kwargs)
            if active[0]: data["metadata"] = {**data["metadata"], "unexpected_change": True}
            return data
        def fitted(*args, **kwargs):
            result = train(*args, **kwargs); active[0] = True; return result
        with patch.object(module, "load_profile", changed), patch.object(module.native, "run_native", fitted): result = self.run_fixture()
        self.assertEqual(result["status"], "failed")
        self.assertEqual(self.record(result)["state"], "failed")
        self.assertIsNone(self.record(result)["completion"])
        self.assertTrue((self.output / "native/candidate.json").exists())

    def test_mutated_registration_file_cannot_be_used_after_fit(self):
        original = module.native.run_native
        def changed(*args, **kwargs):
            result = original(*args, **kwargs)
            path = self.output / "registration.json"; path.write_bytes(path.read_bytes() + b" ")
            return result
        with patch.object(module.native, "run_native", changed): result = self.run_fixture()
        self.assertEqual(result["status"], "failed")
        self.assertEqual(self.record(result)["state"], "failed")

    def test_new_disclosure_during_fit_invalidates_completion_and_keeps_both_events(self):
        original = module.native.run_native
        def disclosed(*args, **kwargs):
            result = original(*args, **kwargs)
            history = self.store.history("agency", "project", guard=lambda: self.now[0])
            disclosure = {"disclosure_id": "a" * 32, "artifact_sha256": "b" * 64,
                "source_reference_sha256": "c" * 64, "recipient_id": "prior-recipient", "channel": "metrics", "occurred_at": 1000}
            self.store.record_disclosure("agency", "project", disclosure, expected_history=history, guard=lambda: self.now[0])
            return result
        with patch.object(module.native, "run_native", disclosed): result = self.run_fixture()
        self.assertEqual(result["status"], "failed")
        self.assertEqual(self.record(result)["state"], "failed")
        history = self.store.history("agency", "project", guard=lambda: self.now[0])
        self.assertEqual(history["known_disclosures"], 1)
        self.assertEqual(history["local_registrations"], 1)

    def test_revoked_signer_after_fit_cannot_suppress_failure_history(self):
        original = module.native.run_native
        def revoked(*args, **kwargs):
            result = original(*args, **kwargs)
            self.registry.revoke("key", expected_revision=self.registry.revision)
            return result
        with patch.object(module.native, "run_native", revoked): result = self.run_fixture()
        self.assertEqual(result["status"], "failed")
        self.assertEqual(self.record(result)["state"], "failed")
        self.assertNotIn("failure_recording_error", result)

    def test_training_failure_remains_after_restart_without_resume_or_refund(self):
        with patch.object(module.native, "run_native", return_value={"status": "failed"}): result = self.run_fixture()
        self.assertEqual(result["status"], "failed")
        reopened = RegistrationStore.open(self.store.root, self.store.store_id)
        record = reopened.get(result["registration_id"], guard=lambda: self.now[0])
        self.assertEqual(record["state"], "failed")
        self.assertEqual(record["failure_reason"], "training_failed")
        self.assertEqual(reopened.history("agency", "project", guard=lambda: self.now[0])["local_registrations"], 1)

    def test_code_drift_during_fitting_cannot_finish(self):
        actual = module.workflow_sha256(); active = [False]; original = module.native.run_native
        def changed(*args, **kwargs):
            result = original(*args, **kwargs); active[0] = True; return result
        with patch.object(module, "workflow_sha256", side_effect=lambda: "f" * 64 if active[0] else actual), patch.object(module.native, "run_native", changed): result = self.run_fixture()
        self.assertEqual(result["status"], "failed"); self.assertEqual(self.record(result)["state"], "failed")

    def test_required_source_file_cannot_be_missing_at_initial_freeze(self):
        package = self.root / "package"; (package / "production_registration").mkdir(parents=True)
        names = {"__init__.py", "analyzers/attack.py", "portfolio_statistics.py", "production_identity/tokens.py"}
        for group, modules in (("production_registration", ("__init__", "workflow", "contracts", "profiles", "store")),
            ("production_adapters", ("__init__", "native", "contracts", "datasets", "catalog")),
            ("production_evidence", ("__init__", "contracts", "signing", "verifier", "replay", "ledger")),
            ("production_trust", ("__init__", "registry", "signer", "verification"))):
            names.update(group + "/" + name + ".py" for name in modules)
        for name in names:
            path = package / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b"# public source fixture\n")
        with patch.object(module, "__file__", str(package / "production_registration/workflow.py")):
            self.assertEqual(len(module.workflow_sha256()), 64)
            (package / "production_registration/contracts.py").unlink()
            with self.assertRaises(ValueError): module.workflow_sha256()

    def test_replay_verification_failure_never_records_completed_training_review(self):
        with patch.object(module.LocalEvidenceVerifier, "accept", side_effect=ValueError("refused")): result = self.run_fixture()
        self.assertEqual(result["status"], "failed")
        self.assertEqual(self.record(result)["state"], "failed")
        self.assertIsNone(self.record(result)["completion"])


if __name__ == "__main__": unittest.main()
