"""Adversarial admission tests across trust, frozen context and replay custody."""
from __future__ import annotations
import copy
from contextlib import closing
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
from concurrent.futures import ThreadPoolExecutor
import unittest
from unittest.mock import patch

import numpy as np
from model_release_assurance.production_adapters import native
from model_release_assurance.production_evidence.contracts import EvidenceError, OBSERVATIONS, canonical_bytes, digest
from model_release_assurance.production_evidence.ledger import ReplayLedger
from model_release_assurance.production_evidence.replay import artifact_manifest, snapshot_native_bundle
from model_release_assurance.production_evidence.signing import MemoryFixtureEvidenceSigner
from model_release_assurance.production_evidence import verifier as module
from model_release_assurance.production_trust.registry import FixtureTrustRegistry, TrustProfile


class EvidenceVerifierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.parent = tempfile.TemporaryDirectory(prefix="evidence-admission-")
        cls.source = Path(cls.parent.name) / "original"
        rng = np.random.default_rng(1212)
        x = rng.normal(size=(240, 4)); y = (x[:, 0] > 0).astype(int)
        result = native.run_native(x, y, dataset_id="synthetic-public", source_sha256="a" * 64,
            feature_names=["a", "b", "c", "d"], output=cls.source)
        if result["status"] != "completed":
            raise AssertionError(result)

    @classmethod
    def tearDownClass(cls):
        cls.parent.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=self.parent.name)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bundle = self.root / "bundle"
        shutil.copytree(self.source, self.bundle)
        self.now = [1000]
        self.profile = TrustProfile("agency", "public_fixture", "https://worker.invalid", "urn:replay", "worker_evidence")
        self.registry = FixtureTrustRegistry(now=lambda: self.now[0], fresh_until=1300)
        self.signer = MemoryFixtureEvidenceSigner(profile=self.profile, owner_id="worker", key_id="key", not_before=1000, not_after=1300)
        self.registry.enroll(self.signer.registration, expected_revision=self.registry.revision)
        self.ledger = ReplayLedger.create(self.root / "ledger")
        self.verifier = module.LocalEvidenceVerifier(self.registry, self.profile, "worker", self.ledger)
        self.context = {"schema": "mra-execution-context/v1", "operation": "retained_native_replay",
            "environment": "public_fixture", "agency_id": "agency", "project_id": "project", "case_id": "case",
            "job_id": "1" * 32, "attempt_id": "2" * 32, "fence": 1, "worker_id": "worker",
            "job_sha256": "b" * 64, "source_sha256": "a" * 64, "policy_sha256": "c" * 64,
            "plan_sha256": hashlib.sha256((self.bundle / "plan.json").read_bytes()).hexdigest(),
            "adapter_sha256": native.implementation_sha256(), "runtime_sha256": digest(module.runtime_observation()), "image_sha256": None}
        self.current = copy.deepcopy(self.context)
        self.challenge = self.verifier.issue(self.context, current_context=self.observe, ttl_seconds=100)
        self.statement = {"schema": "mra-worker-evidence/v1", "context": self.context, "challenge": self.challenge,
            "artifacts": artifact_manifest(snapshot_native_bundle(self.bundle)), "observations": dict(OBSERVATIONS),
            "issued_at": 1000, "expires_at": 1100}
        self.raw = self.signer.sign(self.statement, self.registry)

    def observe(self):
        return copy.deepcopy(self.current)

    def accept(self, raw=None, **kwargs):
        args = dict(expected_context=self.context, artifact_root=self.bundle,
                    current_context=self.observe, required_profile="local_public_replay")
        args.update(kwargs)
        return self.verifier.accept(self.raw if raw is None else raw, **args)

    def test_valid_signature_exact_replay_commits_non_authorizing_result_once(self):
        result = self.accept()
        self.assertEqual(result["status"], "accepted_local_replay")
        self.assertEqual(result["consumption"]["envelope_sha256"], hashlib.sha256(self.raw).hexdigest())
        for key, value in module.FLAGS.items(): self.assertIs(result[key], value)
        self.assertEqual(result["replay"]["status"], "passed")
        with self.assertRaises(EvidenceError): self.accept()

    def test_default_production_and_unknown_profiles_fail_without_burning_challenge(self):
        with self.assertRaises(EvidenceError):
            self.verifier.accept(self.raw, expected_context=self.context, artifact_root=self.bundle, current_context=self.observe)
        for value in ("agency_private_cloud", "unknown", "", None, True):
            with self.subTest(profile=value), self.assertRaises(EvidenceError): self.accept(required_profile=value)
        self.assertEqual(self.accept()["status"], "accepted_local_replay")

    def test_forged_signature_and_another_expected_job_are_rejected(self):
        envelope = json.loads(self.raw)
        value = envelope["signature"]
        envelope["signature"] = ("A" if value[0] != "A" else "B") + value[1:]
        with self.assertRaises(EvidenceError): self.accept(canonical_bytes(envelope))
        changed = {**self.context, "job_id": "3" * 32}
        with self.assertRaises(EvidenceError): self.accept(expected_context=changed, current_context=lambda: changed)
        self.accept()

    def test_every_changed_current_binding_is_rejected(self):
        for name in ("job_sha256", "source_sha256", "policy_sha256", "plan_sha256", "adapter_sha256", "runtime_sha256", "image_sha256"):
            self.current = {**self.context, name: "f" * 64}
            with self.subTest(binding=name), self.assertRaises(EvidenceError): self.accept()
        for name, value in (("attempt_id", "4" * 32), ("fence", 2), ("project_id", "other"), ("case_id", "other")):
            self.current = {**self.context, name: value}
            with self.subTest(binding=name), self.assertRaises(EvidenceError): self.accept()
        self.current = copy.deepcopy(self.context)
        self.accept()

    def test_context_observer_failure_or_cancellation_is_not_cached(self):
        with self.assertRaises(RuntimeError): self.accept(current_context=lambda: (_ for _ in ()).throw(RuntimeError("revoked")))
        original = module.replay_native_bundle
        def canceled(blobs):
            replay = original(blobs)
            self.current["fence"] = 2
            return replay
        with patch.object(module, "replay_native_bundle", canceled), self.assertRaises(EvidenceError): self.accept()
        self.current = copy.deepcopy(self.context)
        self.accept()

    def test_revocation_during_numerical_replay_prevents_commit(self):
        original = module.replay_native_bundle
        def revoked(blobs):
            replay = original(blobs)
            self.registry.revoke("key", expected_revision=self.registry.revision)
            return replay
        with patch.object(module, "replay_native_bundle", revoked), self.assertRaises(EvidenceError): self.accept()

    def test_expiry_during_numerical_replay_prevents_commit(self):
        original = module.replay_native_bundle
        def expired(blobs):
            replay = original(blobs); self.now[0] = 1100
            return replay
        with patch.object(module, "replay_native_bundle", expired), self.assertRaises(EvidenceError): self.accept()

    def test_artifact_replacement_after_snapshot_is_rejected(self):
        original = module.replay_native_bundle
        saved = (self.bundle / "result.json").read_bytes()
        def changed(blobs):
            replay = original(blobs)
            (self.bundle / "result.json").write_bytes(saved + b" ")
            return replay
        with patch.object(module, "replay_native_bundle", changed), self.assertRaises(EvidenceError): self.accept()
        (self.bundle / "result.json").write_bytes(saved)
        self.accept()

    def test_validly_signed_forged_metrics_cannot_replace_numeric_replay(self):
        path = self.bundle / "report.json"
        report = json.loads(path.read_bytes()); report["controls_passed"] = False
        path.write_bytes(canonical_bytes(report) + b"\n")
        receipt_path = self.bundle / "result.json"
        receipt = json.loads(receipt_path.read_bytes())
        receipt["files"]["report.json"] = hashlib.sha256(path.read_bytes()).hexdigest()
        receipt_path.write_bytes(canonical_bytes(receipt) + b"\n")
        statement = {**self.statement, "artifacts": artifact_manifest(snapshot_native_bundle(self.bundle))}
        raw = self.signer.sign(statement, self.registry)
        with self.assertRaises(EvidenceError): self.accept(raw)

    def test_changed_plan_even_with_matching_signature_is_rejected(self):
        changed = {**self.context, "plan_sha256": "e" * 64, "attempt_id": "6" * 32}
        challenge = self.verifier.issue(changed, current_context=lambda: changed)
        statement = {**self.statement, "context": changed, "challenge": challenge}
        raw = self.signer.sign(statement, self.registry)
        with self.assertRaises(EvidenceError): self.accept(raw, expected_context=changed, current_context=lambda: changed)

    def test_asserted_image_cannot_be_promoted_to_verified_local_runtime(self):
        changed = {**self.context, "image_sha256": "e" * 64, "attempt_id": "6" * 32}
        challenge = self.verifier.issue(changed, current_context=lambda: changed)
        statement = {**self.statement, "context": changed, "challenge": challenge}
        raw = self.signer.sign(statement, self.registry)
        with self.assertRaises(EvidenceError): self.accept(raw, expected_context=changed, current_context=lambda: changed)

    def test_restart_preserves_replay_refusal_and_attempt_nonce_uniqueness(self):
        self.accept()
        reopened = ReplayLedger.open(self.ledger.root, self.ledger.ledger_id)
        self.verifier = module.LocalEvidenceVerifier(self.registry, self.profile, "worker", reopened)
        with self.assertRaises(EvidenceError): self.accept()
        with self.assertRaises(EvidenceError): self.verifier.issue(self.context, current_context=self.observe)

    def test_concurrent_admissions_commit_only_once(self):
        def attempt():
            try: return self.accept()["status"]
            except EvidenceError: return "denied"
        with ThreadPoolExecutor(max_workers=2) as executor: results = list(executor.map(lambda _: attempt(), range(2)))
        self.assertCountEqual(results, ["accepted_local_replay", "denied"])

    def test_final_issuance_sample_cannot_cross_registry_freshness(self):
        self.registry.refresh(fresh_until=1050, expected_revision=self.registry.revision)
        context = {**self.context, "attempt_id": "7" * 32}
        original = self.registry.current_time
        calls = [0]
        def boundary():
            calls[0] += 1
            if calls[0] == 2: self.now[0] = 1050
            return original()
        with patch.object(self.registry, "current_time", boundary), self.assertRaises(RuntimeError):
            self.verifier.issue(context, current_context=lambda: context, ttl_seconds=120)
        with closing(sqlite3.connect(self.ledger.root / "replay.sqlite")) as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM challenges").fetchone()[0], 1)

    def test_even_consistent_wrong_runtime_label_is_rejected(self):
        changed = {**self.context, "runtime_sha256": "e" * 64, "attempt_id": "8" * 32}
        with self.assertRaises(EvidenceError):
            self.verifier.issue(changed, current_context=lambda: changed)

    def test_database_failure_never_returns_acceptance(self):
        with patch.object(self.ledger, "consume", side_effect=RuntimeError("unavailable")), self.assertRaises(RuntimeError): self.accept()
        self.accept()


if __name__ == "__main__": unittest.main()
