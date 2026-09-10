"""Adversarial regressions for the experimental local SQLite lifecycle.

No training, live public service, institutional approval, distributed systems
verification or crash-proof hardware guarantee is implied by these tests.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest

from model_release_assurance.lifecycle_reference import (
    Authority, Checkpoint, CommitRequest, LifecycleDenied, LifecycleRegistry,
)


class LifecycleReferenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "registry.sqlite"
        self.now = 100
        self.registry = LifecycleRegistry.create(
            self.path, registry_id="test-registry", budget_limit=10, clock=lambda: self.now)
        self.checkpoint = self.registry.set_authority(
            Authority("reviewer", 1, "valid", 200), expected=self.registry.checkpoint()).checkpoint

    def request(self, **changes):
        request = CommitRequest(
            release_id="one", nonce="nonce-one", artifact_sha256="a" * 64,
            interface_sha256="b" * 64, context_sha256="c" * 64, selection_sha256="d" * 64,
            authority_id="reviewer", authority_epoch=1, expires_at=180,
            evidence_expires_at=170, policy_expires_at=160, max_accesses=2,
            expected_disclosed_release_ids=(), assessment_disposition="RELEASE",
            obligations_status="pass", joint_portfolio_status="pass", commit_budget_cost=1,
        )
        return replace(request, **changes)

    def commit(self, request=None):
        receipt = self.registry.commit(request or self.request(), expected=self.checkpoint)
        self.checkpoint = receipt.checkpoint
        return receipt

    def activate(self, lease_until=150):
        receipt = self.registry.activate("one", expected=self.checkpoint,
                                         artifact_sha256="a" * 64, interface_sha256="b" * 64,
                                         lease_until=lease_until)
        self.checkpoint = receipt.checkpoint
        return receipt

    def grant(self, registry=None, checkpoint=None):
        return (registry or self.registry).grant_access(
            "one", expected=checkpoint or self.checkpoint,
            artifact_sha256="a" * 64, interface_sha256="b" * 64)

    def revoke(self, registry=None, checkpoint=None):
        return (registry or self.registry).revoke(
            "one", expected=checkpoint or self.checkpoint, authority_id="reviewer",
            authority_epoch=1, reason="test incident")

    def snapshot(self):
        return self.registry.snapshot(expected=self.checkpoint)

    def test_positive_commit_activate_grant_revoke_and_history(self):
        self.commit()
        self.activate()
        self.checkpoint = self.grant().checkpoint
        self.assertEqual(self.snapshot()["budget_used"], 2)
        self.checkpoint = self.revoke().checkpoint
        with self.assertRaisesRegex(LifecycleDenied, "active"):
            self.grant()
        state = self.snapshot()
        self.assertEqual(state["release_statuses"], {"one": "revoked"})
        self.assertEqual(state["disclosed_release_ids"], ["one"])
        self.assertEqual(state["grant_count"], 1)

    def test_stale_expected_head_is_not_silently_rebased(self):
        stale = self.checkpoint
        self.commit()
        with self.assertRaisesRegex(LifecycleDenied, "checkpoint mismatch"):
            self.registry.commit(self.request(release_id="two", nonce="two"), expected=stale)
        self.assertEqual(self.snapshot()["nonce_count"], 1)

    def test_nonce_replay_is_rejected_even_with_current_head(self):
        self.commit()
        with self.assertRaisesRegex(LifecycleDenied, "nonce"):
            self.commit(self.request(release_id="two", expected_disclosed_release_ids=("one",)))
        self.assertEqual(self.snapshot()["nonce_count"], 1)

    def test_registered_release_identity_cannot_be_rebound_with_a_new_nonce(self):
        self.commit()
        with self.assertRaisesRegex(LifecycleDenied, "immutable"):
            self.commit(self.request(nonce="fresh-nonce", artifact_sha256="e" * 64,
                                     expected_disclosed_release_ids=("one",)))
        self.assertEqual(self.snapshot()["nonce_count"], 1)

    def test_authorized_but_inactive_release_cannot_grant(self):
        self.commit()
        with self.assertRaisesRegex(LifecycleDenied, "active"):
            self.grant()
        self.assertEqual(self.snapshot()["grant_count"], 0)

    def test_failed_state_write_and_failed_precommit_roll_back_every_component(self):
        baseline = self.snapshot()
        for stage in ("after_state_write", "before_commit"):
            with self.subTest(stage=stage):
                def fault(at):
                    if at == stage:
                        raise RuntimeError("injected transaction failure")
                registry = LifecycleRegistry(self.path, clock=lambda: self.now, failpoint=fault)
                with self.assertRaisesRegex(RuntimeError, "injected"):
                    registry.commit(self.request(), expected=self.checkpoint)
                self.assertEqual(self.snapshot(), baseline)
        self.commit()  # The aborted attempt did not consume its nonce or budget.

    def test_process_termination_before_commit_recovers_without_receipt_or_partial_state(self):
        baseline = self.snapshot()
        code = """
import json, os, sys
from model_release_assurance.lifecycle_reference import Checkpoint, CommitRequest, LifecycleRegistry
payload=json.loads(sys.argv[2])
def crash(stage):
    if stage == 'before_commit':
        os._exit(71)
registry=LifecycleRegistry(sys.argv[1], clock=lambda:100, failpoint=crash)
registry.commit(CommitRequest(**payload['request']), expected=Checkpoint(**payload['checkpoint']))
raise AssertionError('unreachable: no receipt should be returned')
"""
        from dataclasses import asdict
        import json
        result = subprocess.run([sys.executable, "-B", "-c", code, str(self.path),
                                 json.dumps({"request": asdict(self.request()),
                                             "checkpoint": asdict(self.checkpoint)})],
                                capture_output=True, text=True, timeout=30, env=os.environ.copy())
        self.assertEqual(result.returncode, 71, result.stderr)
        self.assertEqual(self.snapshot(), baseline)
        self.commit()

    def test_two_independent_connections_racing_for_one_head_have_one_winner(self):
        barrier = threading.Barrier(2)
        expected = self.checkpoint
        def race(index):
            registry = LifecycleRegistry(self.path, clock=lambda: 100)
            barrier.wait(timeout=5)
            try:
                return registry.commit(self.request(release_id=f"release-{index}", nonce=f"nonce-{index}"),
                                       expected=expected)
            except LifecycleDenied as error:
                return str(error)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(race, (0, 1)))
        winners = [result for result in results if not isinstance(result, str)]
        self.assertEqual(len(winners), 1)
        self.assertIn("checkpoint mismatch", next(result for result in results if isinstance(result, str)))
        self.checkpoint = winners[0].checkpoint
        self.assertEqual(self.snapshot()["nonce_count"], 1)

    def test_grant_linearizes_before_revocation_and_retry_revokes(self):
        self.commit()
        self.activate()
        entered, release = threading.Event(), threading.Event()
        expected = self.checkpoint
        def pause(stage):
            if stage == "after_state_write":
                entered.set()
                if not release.wait(5):
                    raise RuntimeError("test handshake timeout")
        paused_gateway = LifecycleRegistry(self.path, clock=lambda: 100, failpoint=pause)
        revoker = LifecycleRegistry(self.path, clock=lambda: 100)
        with ThreadPoolExecutor(max_workers=2) as pool:
            grant = pool.submit(self.grant, paused_gateway, expected)
            self.assertTrue(entered.wait(5))
            revocation = pool.submit(self.revoke, revoker, expected)
            release.set()
            self.checkpoint = grant.result(timeout=10).checkpoint
            with self.assertRaisesRegex(LifecycleDenied, "checkpoint mismatch"):
                revocation.result(timeout=10)
        self.checkpoint = self.revoke().checkpoint
        with self.assertRaisesRegex(LifecycleDenied, "active"):
            self.grant()
        self.assertEqual(self.snapshot()["grant_count"], 1)

    def test_revocation_linearizes_before_grant_and_no_later_grant_succeeds(self):
        self.commit()
        self.activate()
        stale = self.checkpoint
        self.checkpoint = self.revoke().checkpoint
        with self.assertRaisesRegex(LifecycleDenied, "checkpoint mismatch"):
            self.grant(checkpoint=stale)
        with self.assertRaisesRegex(LifecycleDenied, "active"):
            self.grant()
        self.assertEqual(self.snapshot()["grant_count"], 0)

    def test_revoked_disclosure_must_remain_in_later_portfolio_roster(self):
        self.commit()
        self.checkpoint = self.revoke().checkpoint
        with self.assertRaisesRegex(LifecycleDenied, "disclosure history"):
            self.commit(self.request(release_id="two", nonce="nonce-two"))
        self.commit(self.request(release_id="two", nonce="nonce-two", expected_disclosed_release_ids=("one",)))
        self.assertEqual(self.snapshot()["disclosed_release_ids"], ["one", "two"])

    def test_disclosure_reservation_survives_uncertain_client_completion(self):
        self.commit()
        self.assertEqual(self.snapshot()["disclosed_release_ids"], ["one"])
        self.activate()
        self.grant()  # Simulate dropping the returned receipt before client acknowledgement.
        self.checkpoint = self.registry.checkpoint()
        self.checkpoint = self.revoke().checkpoint
        self.assertEqual(self.snapshot()["disclosed_release_ids"], ["one"])
        self.assertEqual(self.snapshot()["budget_used"], 2)

    def assert_authority_change_denies_access(self, status):
        self.commit()
        self.activate()
        self.checkpoint = self.registry.set_authority(
            Authority("reviewer", 2, status, 200), expected=self.checkpoint).checkpoint
        with self.assertRaisesRegex(LifecycleDenied, "authority"):
            self.grant()
        self.assertEqual(self.snapshot()["grant_count"], 0)

    def test_unknown_current_authority_denies_access(self):
        self.assert_authority_change_denies_access("unknown")

    def test_revoked_current_authority_denies_access(self):
        self.assert_authority_change_denies_access("revoked")

    def test_changed_authority_epoch_denies_access_even_if_replacement_is_valid(self):
        self.assert_authority_change_denies_access("valid")

    def test_expired_authority_denies_access(self):
        self.commit()
        self.activate()
        self.now = 200
        with self.assertRaisesRegex(LifecycleDenied, "authority expired"):
            self.grant()
        self.assertEqual(self.snapshot()["grant_count"], 0)

    def test_unknown_authority_and_expiry_deny_commit(self):
        with self.assertRaisesRegex(LifecycleDenied, "unknown"):
            self.commit(self.request(authority_id="missing"))
        self.now = 200
        with self.assertRaisesRegex(LifecycleDenied, "authority expired"):
            self.commit(self.request(expires_at=300, evidence_expires_at=300, policy_expires_at=300))

    def test_exact_evidence_policy_and_authorization_expiry_boundaries(self):
        for field in ("expires_at", "evidence_expires_at", "policy_expires_at"):
            with self.subTest(field=field):
                with self.assertRaisesRegex(LifecycleDenied, "expired"):
                    self.commit(self.request(**{field: 100}))
        self.commit()
        self.activate()
        self.now = 150
        with self.assertRaisesRegex(LifecycleDenied, "lease expired"):
            self.grant()

    def test_lease_cannot_outlive_current_prerequisite(self):
        self.commit()
        with self.assertRaisesRegex(LifecycleDenied, "lease"):
            self.activate(161)
        self.assertEqual(self.snapshot()["release_statuses"]["one"], "authorized")

    def test_clock_sampled_under_transaction_and_backward_clock_denied(self):
        self.now = 99
        with self.assertRaisesRegex(LifecycleDenied, "clock moved backwards"):
            self.commit()

    def test_access_waiting_for_write_lock_rechecks_expiry_after_lock_acquisition(self):
        self.commit()
        self.activate()
        started = threading.Event()
        def waiting_grant():
            started.set()
            return self.grant()
        with closing(sqlite3.connect(self.path)) as blocker:
            blocker.execute("BEGIN IMMEDIATE")
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(waiting_grant)
                self.assertTrue(started.wait(5))
                self.now = 150
                blocker.rollback()
                with self.assertRaisesRegex(LifecycleDenied, "lease expired"):
                    future.result(timeout=10)
        self.assertEqual(self.snapshot()["grant_count"], 0)

    def test_slow_grant_rechecks_expiry_after_event_preparation_before_commit(self):
        self.commit()
        self.activate()
        baseline = self.snapshot()
        def advance(stage):
            if stage == "before_commit":
                self.now = 150
        gateway = LifecycleRegistry(self.path, clock=lambda: self.now, failpoint=advance)
        with self.assertRaisesRegex(LifecycleDenied, "expired"):
            self.grant(registry=gateway)
        self.assertEqual(self.snapshot(), baseline)

    def test_slow_commit_rechecks_authority_expiry_before_publishing_receipt(self):
        baseline = self.snapshot()
        def advance(stage):
            if stage == "before_commit":
                self.now = 200
        registry = LifecycleRegistry(self.path, clock=lambda: self.now, failpoint=advance)
        with self.assertRaisesRegex(LifecycleDenied, "authority expired"):
            registry.commit(self.request(), expected=self.checkpoint)
        self.assertEqual(self.snapshot(), baseline)

    def test_clock_reversal_during_transaction_aborts_prepared_event(self):
        baseline = self.snapshot()
        def reverse(stage):
            if stage == "before_commit":
                self.now = 99
        registry = LifecycleRegistry(self.path, clock=lambda: self.now, failpoint=reverse)
        with self.assertRaisesRegex(LifecycleDenied, "backwards during"):
            registry.commit(self.request(), expected=self.checkpoint)
        self.assertEqual(self.snapshot(), baseline)

    def test_failed_grant_preserves_prior_disclosure_and_rolls_back_new_budget(self):
        self.commit()
        self.activate()
        baseline = self.snapshot()
        def fault(stage):
            if stage == "before_commit":
                raise RuntimeError("failed grant")
        gateway = LifecycleRegistry(self.path, clock=lambda: self.now, failpoint=fault)
        with self.assertRaisesRegex(RuntimeError, "failed grant"):
            self.grant(registry=gateway)
        self.assertEqual(self.snapshot(), baseline)
        self.checkpoint = self.grant().checkpoint
        self.assertEqual(self.snapshot()["disclosed_release_ids"], ["one"])

    def test_artifact_or_interface_drift_denies_activation_and_each_access(self):
        self.commit()
        with self.assertRaisesRegex(LifecycleDenied, "snapshot"):
            self.registry.activate("one", expected=self.checkpoint, artifact_sha256="e" * 64,
                                   interface_sha256="b" * 64, lease_until=150)
        self.activate()
        with self.assertRaisesRegex(LifecycleDenied, "snapshot"):
            self.registry.grant_access("one", expected=self.checkpoint, artifact_sha256="a" * 64,
                                       interface_sha256="e" * 64)
        self.assertEqual(self.snapshot()["grant_count"], 0)

    def test_cumulative_budget_and_access_limit_are_enforced_without_partial_grants(self):
        self.commit(self.request(commit_budget_cost=9, max_accesses=3))
        self.activate()
        self.checkpoint = self.grant().checkpoint
        baseline = self.snapshot()
        with self.assertRaisesRegex(LifecycleDenied, "budget exhausted"):
            self.grant()
        self.assertEqual(self.snapshot(), baseline)

    def test_per_release_access_allowance_is_not_a_resettable_client_counter(self):
        self.commit(self.request(max_accesses=1))
        self.activate()
        self.checkpoint = self.grant().checkpoint
        with self.assertRaisesRegex(LifecycleDenied, "access allowance"):
            self.grant()
        self.assertEqual(self.snapshot()["grant_count"], 1)

    def test_clear_gates_required_and_unsupported_rwr_cannot_commit(self):
        for changes in ({"assessment_disposition": "RWR"}, {"obligations_status": "unknown"},
                        {"joint_portfolio_status": "unknown"}):
            with self.subTest(changes=changes), self.assertRaisesRegex(LifecycleDenied, "attestations"):
                self.commit(self.request(**changes))
        self.assertEqual(self.snapshot()["nonce_count"], 0)

    def test_delayed_disclosure_mode_is_refused_before_any_reservation(self):
        baseline = self.snapshot()
        with self.assertRaisesRegex(LifecycleDenied, "reservation at commit"):
            self.commit(self.request(reserve_disclosure_on_commit=False))
        self.assertEqual(self.snapshot(), baseline)

    def test_new_disclosure_suspends_old_active_endpoint_without_inheriting_new_certificate(self):
        self.commit()
        self.activate()
        self.checkpoint = self.grant().checkpoint
        self.commit(self.request(release_id="two", nonce="nonce-two",
                                 expected_disclosed_release_ids=("one",)))
        self.assertEqual(self.snapshot()["release_statuses"], {"one": "suspended", "two": "authorized"})
        with self.assertRaisesRegex(LifecycleDenied, "active"):
            self.grant()
        self.checkpoint = self.registry.activate(
            "two", expected=self.checkpoint, artifact_sha256="a" * 64,
            interface_sha256="b" * 64, lease_until=150).checkpoint
        self.checkpoint = self.registry.grant_access(
            "two", expected=self.checkpoint, artifact_sha256="a" * 64,
            interface_sha256="b" * 64).checkpoint
        self.assertEqual(self.snapshot()["disclosed_release_ids"], ["one", "two"])

    def test_new_disclosure_invalidates_unactivated_candidate_too(self):
        self.commit()
        self.commit(self.request(release_id="two", nonce="nonce-two",
                                 expected_disclosed_release_ids=("one",)))
        with self.assertRaisesRegex(LifecycleDenied, "authorized"):
            self.activate()
        self.assertEqual(self.snapshot()["release_statuses"]["one"], "suspended")

    def test_failed_history_extension_rolls_back_suspension_of_existing_service(self):
        self.commit()
        self.activate()
        baseline = self.snapshot()
        with self.assertRaisesRegex(LifecycleDenied, "budget exhausted"):
            self.commit(self.request(release_id="two", nonce="nonce-two", commit_budget_cost=10,
                                     expected_disclosed_release_ids=("one",)))
        self.assertEqual(self.snapshot(), baseline)
        self.checkpoint = self.grant().checkpoint

    def test_external_checkpoint_detects_rollback_but_local_self_read_does_not(self):
        old_checkpoint = self.checkpoint
        backup = self.path.with_name("old.sqlite")
        shutil.copy2(self.path, backup)
        self.commit()
        current_checkpoint = self.checkpoint
        shutil.copy2(backup, self.path)
        with self.assertRaisesRegex(LifecycleDenied, "checkpoint mismatch"):
            self.registry.checkpoint(expected=current_checkpoint)
        self.assertEqual(self.registry.checkpoint(), old_checkpoint)
        with self.assertRaisesRegex(LifecycleDenied, "checkpoint mismatch"):
            self.registry.commit(self.request(), expected=current_checkpoint)

    def test_uncommitted_mutable_state_tampering_is_detected(self):
        with closing(sqlite3.connect(self.path)) as db:
            db.execute("UPDATE authorities SET valid_until=9999")
            db.commit()
        with self.assertRaisesRegex(LifecycleDenied, "state commitment mismatch"):
            self.registry.checkpoint(expected=self.checkpoint)

    def test_history_tables_reject_in_place_deletion(self):
        self.commit()
        with closing(sqlite3.connect(self.path)) as db:
            for table in ("disclosures", "nonces", "charges", "events"):
                with self.subTest(table=table), self.assertRaisesRegex(sqlite3.IntegrityError, "append-only"):
                    db.execute(f"DELETE FROM {table}")
        self.assertEqual(self.snapshot()["disclosed_release_ids"], ["one"])

    def test_existing_or_missing_registry_is_not_recreated(self):
        with self.assertRaises(FileExistsError):
            LifecycleRegistry.create(self.path, registry_id="replacement", budget_limit=1)
        with self.assertRaises(FileNotFoundError):
            LifecycleRegistry(self.path.with_name("missing.sqlite"))


if __name__ == "__main__":
    unittest.main()
