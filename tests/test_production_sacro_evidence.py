"""Real native replay/crypto with fictional child scores; no SACRO dependency skip."""
from __future__ import annotations

import base64
import copy
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from model_release_assurance.production_adapters import native
from model_release_assurance.production_adapters.contracts import canonical_bytes, strict_json
from model_release_assurance.production_evidence import signing
from model_release_assurance.production_evidence.contracts import EvidenceError, digest
from model_release_assurance.production_evidence.replay import snapshot_native_bundle
from model_release_assurance.production_registration.profiles import load_profile
from model_release_assurance.production_sacro import evidence, workflow, protocol


def write(path, value):
    path.write_bytes(canonical_bytes(value) + b"\n")


def read(path):
    return json.loads(path.read_bytes())


def fictional_worker(python, input_path, output):
    """Explicit test double: no claim these probabilities came from SACRO."""
    output = Path(output)
    output.mkdir()
    raw = input_path.read_bytes()
    request = strict_json(raw)
    prepared = request["prepared"]
    cases = {}
    for name in ("target", "positive", "null"):
        repetitions = []
        for split in protocol.frozen_splits(prepared):
            labels = split["membership_labels"]
            values = ([.95 if value else .05 for value in labels] if name == "positive"
                      else [.5] * len(labels) if name == "null"
                      else [((index * 13) % 101) / 100. for index in split["test_indices"]])
            repetitions.append({**split, "member_probabilities": values,
                                "upstream_auc": round(protocol.rank_auc(labels, values), 8)})
        cases[name] = repetitions
    worker = {"schema": "mra-sacro-worker-output/v1", "status": "completed",
        "prepared_sha256": workflow.digest(prepared), "runtime": workflow.expected_binding(),
        "versions": request["versions"], "source_sha256": request["source_sha256"],
        "lock_sha256": request["lock_sha256"], "cases": cases, "fixture_only": True,
        "can_clear": False, "assessment_eligible": False, "authorization_eligible": False,
        "production_authorized": False}
    process = {"status": "completed", "input_sha256": hashlib.sha256(raw).hexdigest(),
        "source_sha256": request["source_sha256"], "runtime_descriptor": {
            "python": "fictional-python", "launcher_sha256": "a" * 64,
            "base_python": "fictional-base", "base_sha256": "b" * 64,
            "site_packages": "fictional-site-packages", "configuration_sha256": "c" * 64},
        "exit_code": 0, "cleanup_confirmed": True, "stdout_bytes": 0, "stderr_bytes": 0,
        "elapsed_seconds": .125, "hostile_code_isolated": False, "network_isolated": False,
        "filesystem_isolated": False, "resource_limits_verified": False}
    write(output / "worker.json", worker)
    write(output / "process.json", process)
    return {**process, "result": worker}


class SacroEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shared = tempfile.TemporaryDirectory(prefix="sacro-evidence-native-")
        cls.bundle = Path(cls.shared.name) / "native"
        data = load_profile("sklearn-wine", max_rows=128)
        result = native.run_native(data["x"], data["y"], dataset_id=data["dataset_id"],
            source_sha256=data["source_sha256"], feature_names=data["feature_names"], output=cls.bundle)
        if result["status"] != "completed":
            raise AssertionError(result)

    @classmethod
    def tearDownClass(cls):
        cls.shared.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="sacro-evidence-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.native = self.root / "native"
        shutil.copytree(self.bundle, self.native)
        self.comparison = self.root / "comparison"
        self.output = self.root / "evidence"
        with patch.object(workflow, "run_worker", fictional_worker):
            result = workflow.run_comparison(snapshot_native_bundle(self.native), profile_id="sklearn-wine",
                output=self.comparison, python="fictional-python", versions={"sacroml": "2.0.1",
                "numpy": "2.5.3", "scipy": "1.18.1", "scikit-learn": "1.6.1"}, lock_sha256="d" * 64)
        self.assertEqual(result["status"], "completed", result)

    def authenticate(self):
        return evidence.authenticate_comparison(self.native, self.comparison, output=self.output)

    def mutate(self, filename, operation):
        path = self.comparison / filename
        value = read(path)
        operation(value)
        write(path, value)

    def test_fresh_native_replay_signature_binds_comparison_without_external_attestation(self):
        result = self.authenticate()
        self.assertEqual(result["status"], "accepted_bound_native_replay")
        self.assertEqual(read(self.output / "result.json"), result)
        for name in ("external_execution_attested", "original_training_attested", "agency_trust_established",
                     "can_clear", "assessment_eligible", "authorization_eligible", "production_authorized", "model_delivery"):
            self.assertIs(result[name], False)
        self.assertIs(result["fixture_key_revoked"], True)
        bindings = read(self.output / "bindings.json")
        context = read(self.output / "context.json")
        self.assertEqual(context["job_sha256"], digest(bindings))
        for name, value in bindings["comparison_files"].items():
            raw = (self.comparison / name).read_bytes()
            self.assertEqual(value, {"sha256": hashlib.sha256(raw).hexdigest(), "size_bytes": len(raw)})
        envelope_raw = (self.output / "envelope.json").read_bytes()
        envelope = json.loads(envelope_raw)
        public = serialization.load_pem_public_key((self.output / "public-key.pem").read_bytes())
        public.verify(base64.b64decode(envelope["signature"]), signing.DOMAIN + canonical_bytes({
            key: value for key, value in envelope.items() if key != "signature"}), padding.PKCS1v15(), hashes.SHA256())
        self.assertEqual(envelope["statement"]["context"], context)
        admission = read(self.output / "admission.json")
        self.assertEqual(admission["status"], "accepted_local_replay")
        self.assertEqual(admission["replay"]["status"], "passed")
        self.assertEqual(admission["envelope_sha256"], hashlib.sha256(envelope_raw).hexdigest())
        self.assertNotIn(b"PRIVATE", (self.output / "public-key.pem").read_bytes())
        self.assertEqual({path.name for path in self.output.iterdir()}, {"ledger", "policy.json", "bindings.json",
            "context.json", "challenge.json", "envelope.json", "public-key.pem", "admission.json", "result.json"})

    def test_existing_output_is_preserved(self):
        self.output.mkdir()
        retained = self.output / "retained"
        retained.write_bytes(b"original")
        with self.assertRaises(EvidenceError):
            self.authenticate()
        self.assertEqual(retained.read_bytes(), b"original")
        self.assertEqual(list(self.output.iterdir()), [retained])

    def test_output_cannot_modify_retained_native_bundle(self):
        before = snapshot_native_bundle(self.native)
        with self.assertRaises(EvidenceError):
            evidence.authenticate_comparison(self.native, self.comparison, output=self.native / "new-evidence")
        self.assertEqual(snapshot_native_bundle(self.native), before)

    def test_tampered_worker_probabilities_rejected_before_output(self):
        self.mutate("worker/worker.json", lambda value: value["cases"]["target"][0]["member_probabilities"].__setitem__(0, 1.1))
        with self.assertRaises(EvidenceError):
            self.authenticate()
        self.assertFalse(self.output.exists())

    def test_tampered_prepared_input_is_rejected_before_output(self):
        self.mutate("input.json", lambda value: value["prepared"]["cases"]["target"]["probabilities"][0].__setitem__(0, .125))
        with self.assertRaises(EvidenceError):
            self.authenticate()
        self.assertFalse(self.output.exists())

    def test_comparison_and_result_cannot_substitute_success_or_metrics(self):
        path = self.comparison / "comparison.json"
        original = path.read_bytes()
        self.mutate("comparison.json", lambda value: value["target"]["summary"].update(attack_raw_auc_mean=True))
        with self.assertRaises(EvidenceError):
            self.authenticate()
        path.write_bytes(original)
        self.mutate("result.json", lambda value: value.update(status="failed"))
        with self.assertRaises(EvidenceError):
            self.authenticate()
        self.assertFalse(self.output.exists())

    def test_frozen_plan_parameters_or_extra_fields_are_rejected(self):
        self.mutate("plan.json", lambda value: value["attack_parameters"].update(n_estimators=500))
        with self.assertRaises(EvidenceError):
            self.authenticate()
        self.assertFalse(self.output.exists())

    def test_process_cleanup_boolean_and_input_digest_are_checked(self):
        path = self.comparison / "worker/process.json"
        original = path.read_bytes()
        for operation in (lambda value: value.update(cleanup_confirmed=False),
                          lambda value: value.update(exit_code=False),
                          lambda value: value.update(input_sha256="0" * 64)):
            path.write_bytes(original)
            self.mutate("worker/process.json", operation)
            with self.assertRaises(EvidenceError):
                self.authenticate()
        self.assertFalse(self.output.exists())

    def test_native_artifact_corruption_is_refused(self):
        path = self.native / "candidate.json"
        value = read(path)
        value["model"]["prior"][0] = .001
        write(path, value)
        with self.assertRaises(EvidenceError):
            self.authenticate()
        self.assertFalse(self.output.exists())

    def test_default_production_profile_still_denies(self):
        accept = evidence.LocalEvidenceVerifier.accept
        def production(verifier, raw, **kwargs):
            self.assertEqual(kwargs.pop("required_profile"), "local_public_replay")
            return accept(verifier, raw, **kwargs)
        with patch.object(evidence.LocalEvidenceVerifier, "accept", production):
            with self.assertRaises(EvidenceError):
                self.authenticate()
        self.assertEqual(read(self.output / "result.json")["status"], "failed")
        self.assertFalse((self.output / "admission.json").exists())

    def test_current_source_is_rechecked_at_challenge_issue(self):
        source = evidence.source_snapshot
        calls = [0]
        def changed():
            calls[0] += 1
            observed = source()
            return observed if calls[0] < 4 else {**observed, "changed.py": "a" * 64}
        with patch.object(evidence, "source_snapshot", changed):
            with self.assertRaises(EvidenceError):
                self.authenticate()
        self.assertEqual(read(self.output / "result.json")["status"], "failed")
        self.assertFalse((self.output / "envelope.json").exists())

    def test_comparison_changed_after_signature_cannot_be_admitted(self):
        sign = evidence.MemoryFixtureEvidenceSigner.sign
        def changed(signer, statement, registry):
            raw = sign(signer, statement, registry)
            path = self.comparison / "result.json"
            path.write_bytes(path.read_bytes() + b" ")
            return raw
        with patch.object(evidence.MemoryFixtureEvidenceSigner, "sign", changed):
            with self.assertRaises(EvidenceError):
                self.authenticate()
        self.assertEqual(read(self.output / "result.json")["status"], "failed")
        self.assertFalse((self.output / "admission.json").exists())

    def test_native_bytes_changed_after_challenge_cannot_be_admitted(self):
        issue = evidence.LocalEvidenceVerifier.issue
        def changed(verifier, *args, **kwargs):
            result = issue(verifier, *args, **kwargs)
            path = self.native / "candidate.json"
            path.write_bytes(path.read_bytes() + b" ")
            return result
        with patch.object(evidence.LocalEvidenceVerifier, "issue", changed):
            with self.assertRaises(EvidenceError):
                self.authenticate()
        self.assertEqual(read(self.output / "result.json")["status"], "failed")
        self.assertFalse((self.output / "admission.json").exists())

    def test_duplicate_json_keys_and_oversized_body_fail_before_output(self):
        path = self.comparison / "result.json"
        original = path.read_bytes()
        path.write_bytes(b'{"status":"completed","status":"failed"}')
        with self.assertRaises(EvidenceError):
            self.authenticate()
        path.write_bytes(original)
        bound = evidence.FILES["worker/worker.json"]
        with patch.dict(evidence.FILES, {"worker/worker.json": 16}):
            with self.assertRaises(EvidenceError):
                self.authenticate()
        self.assertGreater(bound, 16)
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
