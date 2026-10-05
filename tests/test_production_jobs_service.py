"""Real-token authority checks around durable jobs and process-local storage."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import hashlib
from pathlib import Path
import tempfile
from threading import Event, Thread
import unittest
from unittest.mock import patch
import uuid

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import jwt

from model_release_assurance.production_identity.policy import (
    AuthorityState, CaseGrant, CaseRecord, FixtureIdentityService, IdentityUnavailable,
    PermissionDenied, PrincipalAuthority,
)
from model_release_assurance.production_identity.tokens import TokenError
from model_release_assurance.production_jobs.executor import (
    ADAPTER_ID, FixtureProcessRunner, MAX_STDERR_BYTES, MAX_STDOUT_BYTES, worker_sha256)
from model_release_assurance.production_jobs.service import FixtureJobService
from model_release_assurance.production_jobs.store import JobStore
from model_release_assurance.production_storage.backend import FixtureObjectStore
from model_release_assurance.production_storage.service import FixtureStorageService
from model_release_assurance.production_trust.registry import FixtureTrustRegistry, KeyRegistration, TrustProfile
from model_release_assurance.production_trust.verification import RegistryAccessTokenVerifier

ISSUER = "https://job-fixture.example.invalid"
AUDIENCE = "urn:mra:fixture:jobs"
ROLES = {"owner": {"model_owner"}, "operator": {"test_operator", "assessor"},
         "steward": {"data_steward"}, "auditor": {"auditor"}, "worker": {"worker"},
         "human-worker": {"worker"}}


class _Result:
    def __init__(self, value):
        self.value = value

    def to_dict(self):
        return dict(self.value)


class _Runner:
    """No subprocess here; executor process and cleanup behavior has separate tests."""
    def __init__(self):
        self.hook = None
        self.calls = []

    def run(self, **kwargs):
        self.calls.append(kwargs)
        if self.hook:
            self.hook(kwargs)
        digest = hashlib.sha256(kwargs["fixture_bytes"]).hexdigest()
        return _Result({"status": "completed", "output": {"schema": ADAPTER_ID, "input_sha256": digest,
            "categories": 2, "total": 19, "job_id": kwargs["job_id"], "attempt_id": kwargs["attempt_id"]},
            "input_sha256": digest, "worker_sha256": worker_sha256(), "exit_code": 0,
            "stdout_bytes": 250, "stderr_bytes": 0, "cleanup_confirmed": True, "elapsed_seconds": 0.01,
            "fixture_only": True, "hostile_code_isolated": False, "network_isolated": False})


class ProductionJobServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.keys = {name: rsa.generate_private_key(public_exponent=65537, key_size=2048)
                    for name in ("human-key", "worker-key")}

    def setUp(self):
        self.now = 1000
        self.temporary = tempfile.TemporaryDirectory(prefix="mra-job-service-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        profile = TrustProfile(agency_id="agency", environment="public_fixture",
            issuer=ISSUER, audience=AUDIENCE, purpose="access_token")
        self.registry = FixtureTrustRegistry(now=lambda: self.now, fresh_until=1120)
        for name, key in self.keys.items():
            record = KeyRegistration(key_id=name, profile=profile, owner_id="fixture-idp",
                public_key_pem=key.public_key().public_bytes(
                    serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo),
                not_before=990, not_after=1300)
            self.registry.enroll(record, expected_revision=self.registry.revision)
        verifier = RegistryAccessTokenVerifier(self.registry, profile)
        principals = {(ISSUER, name): PrincipalAuthority(ISSUER, name, "person-" + name,
            "workload" if name == "worker" else "human", client_ids=frozenset({"client", "other-client"}))
            for name in ROLES}
        grants = tuple(CaseGrant("person-" + name, "agency", "project", "case-a", frozenset(roles))
                       for name, roles in ROLES.items())
        self.authority = AuthorityState(1, 1290, True, frozenset(self.keys), frozenset(), principals, grants)
        self.identity = FixtureIdentityService(verifier, self.authority,
            [CaseRecord("case-a", "agency", "project", "person-owner"),
             CaseRecord("case-b", "agency", "other-project", "other-owner")], now=lambda: self.now)
        self.storage = FixtureStorageService(self.identity, FixtureObjectStore(self.root / "objects"))
        self.store = JobStore.create(self.root / "jobs")
        self.runner = _Runner()
        self.service = FixtureJobService(self.identity, self.storage, self.store, self.runner)
        self.tokens = {name: self.token(name) for name in ROLES if name != "worker"}
        self.reference = self.storage.register_fixture(self.tokens["steward"], "case-a", "public-counts-v1", 100)["reference"]

    def token(self, subject="operator", *, job_id=None, **changes):
        scopes = {"case:read", "object:metadata"}
        if subject == "owner":
            scopes.add("proposal:submit")
        if subject in {"operator", "human-worker"}:
            scopes.update({"job:run", "review:assess"})
        if subject == "steward":
            scopes.update({"object:register", "object:grant"})
        if subject == "worker":
            scopes = {"job:run", "object:read"}
        if job_id:
            scopes.add("job:" + job_id)
        claims = {"iss": ISSUER, "aud": AUDIENCE, "sub": subject, "iat": self.now, "nbf": self.now,
                  "exp": 1290, "jti": uuid.uuid4().hex, "client_id": "client",
                  "scope": " ".join(sorted(scopes)), "case_ids": ["case-a", "case-b"]}
        if subject != "worker":
            claims.update(acr="urn:mra:fixture:mfa", auth_time=self.now)
        claims.update(changes)
        key = "worker-key" if subject == "worker" else "human-key"
        return jwt.encode(claims, self.keys[key], algorithm="RS256", headers={"kid": key, "typ": "at+jwt"})

    def submit(self, request_id="request-a"):
        return self.service.submit(self.tokens["operator"], "case-a", ADAPTER_ID, self.reference, request_id)

    def prepared(self):
        job = self.submit()
        worker = self.token("worker", job_id=job["job_id"])
        grant = self.service.authorize_input(self.tokens["steward"], "case-a", job["job_id"], worker, 30)
        return job, worker, grant

    def run_job(self, job, worker):
        return self.service.run(worker, "case-a", job["job_id"], job["digest"])

    def update(self, **changes):
        self.authority = replace(self.authority, revision=self.authority.revision + 1, **changes)
        self.identity._replace_authority_for_fixture(self.authority)

    def test_valid_real_signed_job_consumes_public_input_and_returns_fixture_only(self):
        job, worker, _ = self.prepared()
        result = self.run_job(job, worker)
        self.assertEqual(19, result["result"]["total"])
        self.assertTrue(result["result_authorization_current"])
        self.assertFalse(result["authorization_eligible"])
        self.assertFalse(result["model_delivery"])
        self.assertFalse(result["hostile_code_isolated"])
        self.assertFalse(result["network_isolated"])
        self.assertEqual({"job_id", "attempt_id", "fixture_bytes", "timeout_seconds", "cancel_event"},
                         set(self.runner.calls[0]))
        read = self.service.read_job(self.tokens["auditor"], "case-a", job["job_id"])
        self.assertEqual(result["result"], read["result"])

    def test_request_id_is_idempotent_for_same_authoritative_actor(self):
        first = self.submit()
        second = self.submit()
        self.assertEqual(first["job_id"], second["job_id"])
        self.assertEqual(first["digest"], second["digest"])
        with self.assertRaises(ValueError):
            self.service.submit(self.tokens["operator"], "case-a", ADAPTER_ID, self.reference, "../path")

    def test_only_fixed_recipe_exact_registered_reference_and_case_are_accepted(self):
        for recipe in ("arbitrary", "/tmp/program.py", ["command"]):
            with self.assertRaises(ValueError):
                self.service.submit(self.tokens["operator"], "case-a", recipe, self.reference, "request")
        changed = {**self.reference, "sha256": "f" * 64}
        with self.assertRaises(Exception):
            self.service.submit(self.tokens["operator"], "case-a", ADAPTER_ID, changed, "request")
        with self.assertRaises(PermissionDenied):
            self.service.submit(self.tokens["operator"], "case-b", ADAPTER_ID, self.reference, "request")
        self.assertFalse(self.runner.calls)

    def test_roles_and_raw_token_boundaries_do_not_upgrade_human_worker(self):
        with self.assertRaises(PermissionDenied):
            self.service.submit(self.tokens["human-worker"], "case-a", ADAPTER_ID, self.reference, "request")
        with self.assertRaises(PermissionDenied):
            self.service.submit(self.tokens["auditor"], "case-a", ADAPTER_ID, self.reference, "request")
        with self.assertRaises(TokenError):
            self.service.submit({"roles": ["test_operator"]}, "case-a", ADAPTER_ID, self.reference, "request")
        job = self.submit()
        with self.assertRaises(PermissionDenied):
            self.service.authorize_input(self.tokens["operator"], "case-a", job["job_id"],
                                         self.token("worker", job_id=job["job_id"]), 10)
        with self.assertRaises(PermissionDenied):
            self.service.authorize_input(self.tokens["steward"], "case-a", job["job_id"],
                                         self.token("operator", job_id=job["job_id"]), 10)

    def test_signed_job_scope_and_both_worker_actions_are_required(self):
        job = self.submit()
        for scopes in ("job:run object:read", "job:run job:" + job["job_id"],
                       "object:read job:" + job["job_id"]):
            with self.assertRaises(PermissionDenied):
                self.service.authorize_input(self.tokens["steward"], "case-a", job["job_id"],
                                             self.token("worker", scope=scopes), 30)

    def test_same_jti_with_changed_signed_claims_cannot_use_another_binding(self):
        job, worker, _ = self.prepared()
        identity = self.identity._verifier.verify(worker, now=self.now)
        altered = self.token("worker", job_id=job["job_id"], jti=identity.token_id, client_id="other-client")
        with self.assertRaises(PermissionDenied):
            self.run_job(job, altered)
        self.assertFalse(self.runner.calls)

    def test_wrong_descriptor_or_implementation_hash_prevents_execution(self):
        job, worker, _ = self.prepared()
        with self.assertRaises(ValueError):
            self.service.run(worker, "case-a", job["job_id"], "f" * 64)
        with patch("model_release_assurance.production_jobs.service.worker_sha256", return_value="f" * 64):
            with self.assertRaises(ValueError):
                self.run_job(job, worker)
        self.assertFalse(self.runner.calls)

    def test_failed_input_read_never_reuses_durable_reservation(self):
        job, worker, _ = self.prepared()
        with patch.object(self.storage, "read", side_effect=PermissionDenied("fixture unavailable")):
            with self.assertRaises(PermissionDenied):
                self.run_job(job, worker)
        with self.assertRaises(Exception):
            self.run_job(job, worker)
        self.assertFalse(self.runner.calls)

    def test_worker_key_revocation_during_execution_blocks_output_without_holding_identity_lock(self):
        job, worker, _ = self.prepared()
        def revoke(_):
            finished = Event()
            errors = []
            def revocation():
                try:
                    self.registry.revoke("worker-key", expected_revision=self.registry.revision)
                except Exception as error:
                    errors.append(error)
                finally:
                    finished.set()
            thread = Thread(target=revocation, daemon=True)
            thread.start()
            self.assertTrue(finished.wait(3), "Identity lock was held during child execution")
            thread.join(timeout=1)
            self.assertFalse(errors)
        self.runner.hook = revoke
        with self.assertRaises(TokenError):
            self.run_job(job, worker)
        result = self.service.read_job(self.tokens["auditor"], "case-a", job["job_id"])
        self.assertIsNone(result["result"])

    def test_current_authority_revision_or_outage_during_execution_denies_result(self):
        for change in ({"available": False}, {}):
            with self.subTest(change=change):
                if change == {}:
                    self.setUp()
                job, worker, _ = self.prepared()
                self.runner.hook = lambda _: self.update(**change)
                with self.assertRaises((PermissionDenied, IdentityUnavailable)):
                    self.run_job(job, worker)

    def test_expiry_after_process_output_cannot_commit_success(self):
        job, worker, _ = self.prepared()
        self.runner.hook = lambda _: setattr(self, "now", 1031)
        with self.assertRaises(Exception):
            self.run_job(job, worker)
        row = self.service.read_job(self.tokens["auditor"], "case-a", job["job_id"])
        self.assertIsNone(row["result"])

    def test_invalid_worker_receipt_never_commits_output(self):
        job, worker, _ = self.prepared()
        original = self.runner.run
        def corrupt(**kwargs):
            result = original(**kwargs)
            result.value["output"]["total"] = 999
            return result
        with patch.object(self.runner, "run", side_effect=corrupt):
            with self.assertRaises(ValueError):
                self.run_job(job, worker)
        self.assertIsNone(self.service.read_job(self.tokens["auditor"], "case-a", job["job_id"])["result"])

    def test_completed_result_is_redacted_when_prior_worker_is_revoked(self):
        job, worker, _ = self.prepared()
        self.run_job(job, worker)
        self.registry.revoke("worker-key", expected_revision=self.registry.revision)
        result = self.service.read_job(self.tokens["auditor"], "case-a", job["job_id"])
        self.assertIsNone(result["result"])
        self.assertFalse(result["result_authorization_current"])

    def test_restart_fences_old_broker_and_never_reconstructs_old_grants_or_output_authority(self):
        job, worker, _ = self.prepared()
        self.run_job(job, worker)
        reopened = JobStore.open(self.root / "jobs", expected_store_id=self.store.store_id)
        new_service = FixtureJobService(self.identity, self.storage, reopened, self.runner)
        with self.assertRaises(Exception):
            self.service.read_job(self.tokens["auditor"], "case-a", job["job_id"])
        historical = new_service.read_job(self.tokens["auditor"], "case-a", job["job_id"])
        self.assertIsNone(historical["result"])
        self.assertFalse(historical["result_authorization_current"])
        with self.assertRaises(PermissionDenied):
            new_service.run(worker, "case-a", job["job_id"], job["digest"])

    def test_cancel_signals_only_owned_attempt_and_denies_late_result(self):
        job, worker, _ = self.prepared()
        entered, resume = Event(), Event()
        def wait(kwargs):
            entered.set()
            self.assertTrue(resume.wait(3))
        self.runner.hook = wait
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(self.run_job, job, worker)
            self.assertTrue(entered.wait(3))
            self.service.cancel(self.tokens["operator"], "case-a", job["job_id"])
            self.assertTrue(self.runner.calls[0]["cancel_event"].is_set())
            resume.set()
            with self.assertRaises(Exception):
                future.result(timeout=3)
        self.assertIsNone(self.service.read_job(self.tokens["auditor"], "case-a", job["job_id"])["result"])

    def test_concurrent_run_has_one_lease_and_one_input_read(self):
        job, worker, _ = self.prepared()
        entered, resume = Event(), Event()
        def wait(_):
            entered.set()
            self.assertTrue(resume.wait(3))
        self.runner.hook = wait
        with patch.object(self.storage, "read", wraps=self.storage.read) as read:
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(self.run_job, job, worker)
                self.assertTrue(entered.wait(3))
                try:
                    with self.assertRaises(Exception):
                        self.run_job(job, worker)
                finally:
                    resume.set()
                result = future.result(timeout=3)
        self.assertEqual(19, result["result"]["total"])
        self.assertEqual(1, read.call_count)
        self.assertEqual(1, len(self.runner.calls))

    def test_retry_requires_new_steward_grant_and_exact_new_worker_credential(self):
        job, worker, _ = self.prepared()
        with patch.object(self.storage, "read", side_effect=PermissionDenied("fixture unavailable")):
            with self.assertRaises(PermissionDenied):
                self.run_job(job, worker)
        replacement = self.token("worker", job_id=job["job_id"])
        self.service.authorize_input(self.tokens["steward"], "case-a", job["job_id"], replacement, 30)
        with self.assertRaises(PermissionDenied):
            self.run_job(job, worker)
        result = self.run_job(job, replacement)
        self.assertEqual(19, result["result"]["total"])

    def test_running_attempt_cannot_replace_input_authority_and_revoked_actor_result_is_hidden(self):
        job, worker, _ = self.prepared()
        replacement = self.token("worker", job_id=job["job_id"])
        def replace_during_run(_):
            with self.assertRaises(ValueError):
                self.service.authorize_input(self.tokens["steward"], "case-a", job["job_id"], replacement, 30)
        self.runner.hook = replace_during_run
        completed = self.run_job(job, worker)
        self.assertEqual(19, completed["result"]["total"])
        self.registry.revoke("worker-key", expected_revision=self.registry.revision)
        self.assertIsNone(self.service.read_job(self.tokens["auditor"], "case-a", job["job_id"])["result"])

    def test_lease_expiry_during_input_read_never_launches_child_and_reservation_stays_spent(self):
        job, worker, _ = self.prepared()
        original = self.storage.read
        def expire_after_read(*args, **kwargs):
            content = original(*args, **kwargs)
            self.now = 1031
            return content
        with patch.object(self.storage, "read", side_effect=expire_after_read):
            with self.assertRaises(Exception):
                self.run_job(job, worker)
        self.assertFalse(self.runner.calls)
        with self.assertRaises(Exception):
            self.run_job(job, worker)
        self.assertFalse(self.runner.calls)
        replacement = self.token("worker", job_id=job["job_id"])
        self.service.authorize_input(self.tokens["steward"], "case-a", job["job_id"], replacement, 30)
        self.assertEqual(19, self.run_job(job, replacement)["result"]["total"])

    def test_broker_replacement_after_reservation_prevents_read_and_child_launch(self):
        job, worker, _ = self.prepared()
        consume = self.store.consume_input
        def reserve_then_restart(*args, **kwargs):
            reserved = consume(*args, **kwargs)
            reopened = JobStore.open(self.root / "jobs", expected_store_id=self.store.store_id)
            FixtureJobService(self.identity, self.storage, reopened, self.runner)
            return reserved
        with patch.object(self.store, "consume_input", side_effect=reserve_then_restart), \
                patch.object(self.storage, "read", wraps=self.storage.read) as read:
            with self.assertRaises(Exception):
                self.run_job(job, worker)
        self.assertEqual(0, read.call_count)
        self.assertFalse(self.runner.calls)

    def test_actual_fixed_process_integrates_with_signed_grant_and_durable_result(self):
        self.service._runner = FixtureProcessRunner(self.root / "actual-runner")
        job, worker, _ = self.prepared()
        result = self.run_job(job, worker)
        self.assertEqual(19, result["result"]["total"])
        self.assertEqual(2, result["result"]["categories"])
        self.assertTrue(result["result_authorization_current"])
        self.assertFalse(result["hostile_code_isolated"])
        self.assertFalse(result["network_isolated"])

    def test_output_limit_records_drained_counts_above_capture_limits_without_output(self):
        for field, limit in (("stdout_bytes", MAX_STDOUT_BYTES), ("stderr_bytes", MAX_STDERR_BYTES)):
            with self.subTest(field=field):
                job = self.submit("overflow-" + field)
                worker = self.token("worker", job_id=job["job_id"])
                self.service.authorize_input(self.tokens["steward"], "case-a", job["job_id"], worker, 30)
                original = self.runner.run
                def overflow(**kwargs):
                    result = original(**kwargs)
                    result.value.update(status="output_limit", output=None, exit_code=-15)
                    result.value[field] = limit + 4096
                    return result
                with patch.object(self.runner, "run", side_effect=overflow):
                    result = self.run_job(job, worker)
                self.assertIsNone(result["result"])
                self.assertEqual("output_limit", result["attempts"][-1]["reason"])
                self.assertEqual("failed", result["attempts"][-1]["state"])

    def test_completed_receipts_cannot_exceed_stdout_or_stderr_capture_limit(self):
        for field, limit in (("stdout_bytes", MAX_STDOUT_BYTES), ("stderr_bytes", MAX_STDERR_BYTES)):
            with self.subTest(field=field):
                job = self.submit("completed-overflow-" + field)
                worker = self.token("worker", job_id=job["job_id"])
                self.service.authorize_input(self.tokens["steward"], "case-a", job["job_id"], worker, 30)
                original = self.runner.run
                def invalid_completed(**kwargs):
                    result = original(**kwargs)
                    result.value[field] = limit + 1
                    return result
                with patch.object(self.runner, "run", side_effect=invalid_completed):
                    with self.assertRaises(ValueError):
                        self.run_job(job, worker)
                self.assertIsNone(self.service.read_job(self.tokens["auditor"], "case-a", job["job_id"])["result"])

    def test_malformed_overflow_counters_remain_fail_closed(self):
        for index, count in enumerate((True, -1, 1.5, 2**40 + 1)):
            with self.subTest(count=count):
                job = self.submit("bad-counter-" + str(index))
                worker = self.token("worker", job_id=job["job_id"])
                self.service.authorize_input(self.tokens["steward"], "case-a", job["job_id"], worker, 30)
                original = self.runner.run
                def malformed(**kwargs):
                    result = original(**kwargs)
                    result.value.update(status="output_limit", output=None, exit_code=-15, stdout_bytes=count)
                    return result
                with patch.object(self.runner, "run", side_effect=malformed):
                    with self.assertRaises(ValueError):
                        self.run_job(job, worker)
                self.assertIsNone(self.service.read_job(self.tokens["auditor"], "case-a", job["job_id"])["result"])

    def test_failed_job_attempt_still_records_operator_for_review_independence(self):
        proposal = self.identity.submit_proposal(self.tokens["owner"], "case-a",
            {"artifact_sha256": "a" * 64, "evidence_sha256": "b" * 64, "policy_sha256": "c" * 64,
             "recipient_id": "public-recipient", "revision": 1})
        with self.assertRaises(ValueError):
            self.service.submit(self.tokens["operator"], "case-a", "unknown", self.reference, "request")
        with self.assertRaises(PermissionDenied):
            self.identity.assess(self.tokens["operator"], "case-a", proposal["proposal_digest"])


if __name__ == "__main__":
    unittest.main()




