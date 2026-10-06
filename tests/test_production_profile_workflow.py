"""Real fresh Wine, live fixture authority and explicitly fictional SACRO output.

These portable tests do not claim SACRO executed, scientific qualification or
production clearance. No source, prior evidence or persistent keys are changed.
"""
from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch, Mock

from model_release_assurance.production_identity.policy import PermissionDenied, IdentityUnavailable
from model_release_assurance.production_review.rehearsal import ISSUER
from model_release_assurance.production_profile import workflow as module, rehearsal, runtime
from model_release_assurance.production_profile.contracts import FLAGS, ProfileError
from model_release_assurance.production_profile.journal import StoreConflict
from model_release_assurance.production_sacro import workflow as sacro_workflow
from test_production_sacro_evidence import fictional_worker


def fictional_worker_with_logs(python, input_path, output):
    """Reuse the declared test double, adding the two empty retained log files."""
    result = fictional_worker(python, input_path, output)
    for name in ("stdout.log", "stderr.log"):
        (Path(output) / name).write_bytes(b"")
    return result


class PublicProfileWorkflowTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="mra-public-profile-flow-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.worker = patch.object(sacro_workflow, "run_worker", side_effect=fictional_worker_with_logs).start()
        self.addCleanup(patch.stopall)

    def new(self, name="run"):
        return module.PublicProfileWorkflow(self.root / name, python="fictional-python",
            versions=dict(runtime._PINNED_VERSIONS), lock_sha256=runtime.LOCK_SHA256,
            profile="local_public_fixture")

    def native(self, flow):
        policy, operator = flow.token("policy"), flow.token("operator")
        planned = flow.freeze(policy)
        completed = flow.execute(operator)
        self.assertEqual(planned["stage"], "planned")
        self.assertEqual(completed["stage"], "native")
        return operator

    def approved(self, flow):
        operator = self.native(flow)
        external = flow.compare(operator)
        assessed = flow.assess(flow.token("assessor"))
        releaser = flow.token("releaser")
        approved = flow.approve(releaser)
        combined = external["stages"]["external"]["payload"]["combined_sha256"]
        self.assertEqual(assessed["stages"]["assess"]["payload"]["combined_sha256"], combined)
        self.assertEqual(approved["stages"]["approve"]["payload"]["combined_sha256"], combined)
        return releaser

    def test_production_default_and_invalid_runtime_refused_before_output(self):
        for kwargs in ({}, {"profile": "agency_private_cloud"}):
            path = self.root / "production"
            with self.subTest(kwargs=kwargs), self.assertRaises(PermissionDenied):
                module.PublicProfileWorkflow(path, python="fictional-python", versions={}, lock_sha256="a" * 64, **kwargs)
            self.assertFalse(path.exists())
        versions = dict(runtime._PINNED_VERSIONS)
        versions["sacroml"] = "0.0.0"
        path = self.root / "wrong-runtime"
        with self.assertRaises(ValueError):
            module.PublicProfileWorkflow(path, python="fictional-python", versions=versions,
                lock_sha256=runtime.LOCK_SHA256, profile="local_public_fixture")
        self.assertFalse(path.exists())
        self.worker.assert_not_called()

    def test_runtime_versions_and_snapshot_are_owned_and_clock_cannot_reverse(self):
        versions = dict(runtime._PINNED_VERSIONS)
        flow = module.PublicProfileWorkflow(self.root / "owned", python="fictional-python", versions=versions,
            lock_sha256=runtime.LOCK_SHA256, profile="local_public_fixture")
        versions["sacroml"] = "untrusted mutation"
        self.assertEqual(flow._versions, dict(runtime._PINNED_VERSIONS))
        state = flow.freeze(flow.token("policy"))
        state["plan"]["required_cases"].clear()
        self.assertEqual(flow._state()["plan"]["required_cases"], ["target", "positive", "null"])
        with self.assertRaises(ProfileError):
            flow.advance_to(flow.clock() - 1)
        with self.assertRaises(ProfileError):
            flow.advance_to(True)
        with self.assertRaises(PermissionDenied):
            flow.freeze(flow.token("policy"))
        self.assertFalse(flow._fixture.output.exists())

    def test_external_is_mandatory_original_credential_only_and_reviews_do_not_self_lock(self):
        flow = self.new()
        operator = self.native(flow)
        self.assertTrue((flow._fixture.output / "native/candidate.json").is_file())
        self.assertTrue((flow._fixture.output / "replay-envelope.json").is_file())
        for action in (lambda: flow.assess(flow.token("assessor")),
                       lambda: flow.authorize(flow.token("releaser"))):
            with self.assertRaises(PermissionDenied):
                action()
        with self.assertRaises(PermissionDenied):
            flow.compare(flow.token("operator"))
        self.worker.assert_not_called()
        self.assertFalse((flow.root / "external").exists())
        flow.compare(operator)
        with self.assertRaises(PermissionDenied):
            flow.assess(flow.token("owner"))
        assessed = flow.assess(flow.token("assessor"))
        self.assertEqual(assessed["stage"], "assess")
        with self.assertRaises(PermissionDenied):
            flow.approve(operator)
        releaser = flow.token("releaser")
        approved = flow.approve(releaser)
        authorized = flow.authorize(releaser)
        self.assertEqual(approved["stage"], "approve")
        self.assertEqual(authorized["stage"], "authorize")
        self.assertEqual(authorized["pin"]["sequence"], 6)
        self.assertEqual(self.worker.call_count, 1)
        self.assertEqual(len(flow.status(flow.token("auditor"))["delivery"]["activations"]), 1)
        for key, expected in FLAGS.items():
            self.assertIs(authorized[key], expected)

    def test_native_external_combined_implementation_and_authority_tamper_block_writer(self):
        flow = self.new()
        releaser = self.approved(flow)
        flow.authorize(releaser)
        recipient = flow.token("recipient")
        grant_id, grant = flow.grant(releaser, recipient)
        transfer = grant["payload"]["transfer_id"]
        captured = []
        def writer(content):
            captured.append(content)
            return len(content)
        paths = [flow._fixture.output / "native/candidate.json", flow.root / "combined-binding.json",
                 *(flow.root / "external" / name for name in ("input.json", "plan.json", "worker/worker.json",
                    "worker/process.json", "comparison.json", "result.json"))]
        for path in paths:
            original = path.read_bytes()
            with self.subTest(path=path.name):
                try:
                    path.write_bytes(original + b" ")
                    with self.assertRaises((PermissionDenied, ValueError)):
                        flow.deliver_chunk(recipient, grant_id, transfer, 0, 128, writer=writer)
                finally:
                    path.write_bytes(original)
                self.assertEqual(captured, [])
        with patch.object(module, "implementation_sha256", return_value="f" * 64):
            with self.assertRaises(PermissionDenied):
                flow.deliver_chunk(recipient, grant_id, transfer, 0, 128, writer=writer)
        self.assertEqual(captured, [])
        state = flow.status(flow.token("auditor"))["delivery"]
        self.assertEqual(state["grants"][grant_id]["attempted_bytes"], 0)
        receipt = flow.deliver_chunk(recipient, grant_id, transfer, 0, 128, writer=writer)
        self.assertEqual(receipt["bytes_written"], 128)
        self.assertEqual(b"".join(captured), (flow._fixture.output / "native/candidate.json").read_bytes()[:128])
        foundation = flow._fixture.review_fixture
        principals = dict(foundation.authority.principals)
        principals[(ISSUER, "assessor")] = replace(principals[(ISSUER, "assessor")], enabled=False)
        foundation.update(principals=principals)
        with self.assertRaises((PermissionDenied, IdentityUnavailable)):
            flow.deliver_chunk(recipient, grant_id, transfer, 128, 128, writer=writer)
        self.assertEqual(len(captured), 1)

    def test_final_shared_timestamp_checks_original_evidence_and_activation_exclusively(self):
        # A narrow helper unit test: the fake authority returns a supplied trusted
        # timestamp; no fit, journal append or authorization success is simulated.
        flow = object.__new__(module.PublicProfileWorkflow)
        actor, extra = object(), object()
        flow._contexts = [actor]
        flow._campaign_id = "test-campaign"
        authority = SimpleNamespace(recheck_many=Mock(return_value=1010))
        flow._review = SimpleNamespace(authorization=authority,
            _evidence_deadlines={flow._campaign_id: (1000, 1010)})
        with self.assertRaises(PermissionDenied):
            flow._current_contexts(extra=(extra,))
        authority.recheck_many.assert_called_once_with((actor, extra))
        authority.recheck_many.reset_mock(return_value=True)
        authority.recheck_many.return_value = 1005
        with self.assertRaises(PermissionDenied):
            flow._current_contexts(extra=(extra,), deadlines=((1000, 1005),))
        authority.recheck_many.assert_called_once_with((actor, extra))
        authority.recheck_many.return_value = 1004
        self.assertEqual(flow._current_contexts(extra=(extra,), deadlines=((1000, 1005),)), 1004)

    def test_durable_activation_survives_journal_failure_but_facade_cannot_grant(self):
        flow = self.new()
        releaser = self.approved(flow)
        def fail(*args, **kwargs):
            raise StoreConflict("explicit fixture journal write failure")
        with patch.object(flow._journal, "append", side_effect=fail):
            with self.assertRaises(StoreConflict):
                flow.authorize(releaser)
        status = flow.status(flow.token("auditor"))
        self.assertEqual(status["journal"]["stage"], "approve")
        self.assertEqual(len(status["delivery"]["activations"]), 1)
        self.assertEqual(next(iter(status["delivery"]["activations"].values()))["state"], "active")
        self.assertIsNone(flow._activation_id)
        with self.assertRaises(PermissionDenied):
            flow.grant(releaser, flow.token("recipient"))
        self.assertEqual(flow.status(flow.token("auditor"))["delivery"]["grants"], {})

    def test_activation_expiry_between_stores_denies_authorize_without_erasing_commit(self):
        flow = self.new()
        releaser = self.approved(flow)
        original = flow._gateway.activate
        def expire_after_commit(*args, **kwargs):
            result = original(*args, **kwargs)
            deadline = max(row["payload"]["expires_at"] for row in result["activations"].values())
            flow.advance_to(deadline)
            return result
        with patch.object(flow._gateway, "activate", side_effect=expire_after_commit):
            with self.assertRaises(PermissionDenied):
                flow.authorize(releaser)
        state = flow.status(flow.token("auditor"))
        self.assertEqual(state["journal"]["stage"], "approve")
        self.assertEqual(len(state["delivery"]["activations"]), 1)
        self.assertIsNone(flow._activation_id)
        with self.assertRaises(PermissionDenied):
            flow.grant(releaser, flow.token("recipient"))

    def test_finish_requires_revocation_and_is_audit_only(self):
        flow = self.new()
        releaser = self.approved(flow)
        flow.authorize(releaser)
        with self.assertRaises(PermissionDenied):
            flow.finish(flow.token("auditor"), {}, {})
        self.assertFalse((flow.root / "delivery-summary.json").exists())
        flow.revoke(releaser)
        completed = flow.finish(flow.token("auditor"), {"fixture_test": "summary"}, {"fixture_test": "lifecycle"})
        self.assertEqual(completed["stage"], "complete")
        self.assertFalse(completed["authorization_eligible"])
        self.assertFalse(completed["production_ready"])
        with self.assertRaises(PermissionDenied):
            flow.grant(releaser, flow.token("recipient"))
        # Placeholder metadata here deliberately cannot become a valid sealed
        # receipt; semantic receipt integration is covered by exercise below.

    def test_full_rehearsal_real_native_fictional_worker_and_semantic_historical_receipt(self):
        # Keep the positive lifecycle independent of filesystem/CPU speed. Its
        # explicit advance_to(expiry) still exercises exclusive expiry denial;
        # separate deadline tests cover expiry during expensive guarded work.
        # Only this fixture clock is controlled; process deadlines remain real.
        with patch.object(module.PublicProfileWorkflow, "clock", lambda flow: 1000 + flow._offset):
            result = rehearsal.exercise(self.root / "exercise", python="fictional-python",
                versions=dict(runtime._PINNED_VERSIONS), lock_sha256=runtime.LOCK_SHA256)
        self.assertEqual(result["status"], "passed")
        self.assertEqual({item["name"] for item in result["checks"]}, rehearsal.REQUIRED_CHECKS)
        self.assertTrue(all(item["passed"] for item in result["checks"]))
        self.assertEqual(result["summary"]["fresh_native_runs"], 1)
        self.assertEqual(result["summary"]["external_repetitions"], 9)
        self.assertTrue(result["summary"]["public_fixture_bytes_delivered"])
        self.assertFalse(result["summary"]["recipient_receipt_verified"])
        replay = json.loads((self.root / "exercise/replay-result.json").read_bytes())
        self.assertEqual(replay["status"], "historical_fixture_replay_verified")
        self.assertFalse(replay["external_execution_attested"])
        self.assertFalse(replay["current_authorization_checked"])
        for key, value in FLAGS.items():
            self.assertIs(replay[key], value)
        retained = self.root / "exercise/run"
        self.assertEqual(hashlib.sha256((retained / "receipt.json").read_bytes()).hexdigest(),
                         result["evidence"]["receipt_pin"]["receipt_sha256"])
        self.assertFalse(any(b"PRIVATE KEY" in path.read_bytes() for path in retained.rglob("*.pem")))


if __name__ == "__main__":
    unittest.main()
