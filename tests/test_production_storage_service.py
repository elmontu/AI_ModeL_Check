"""Public storage service grants stay case scoped, current and single use."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from model_release_assurance.production_identity.policy import (
    AuthorityState, CaseGrant, CaseRecord, Conflict, FixtureIdentityService,
    IdentityUnavailable, PermissionDenied, PrincipalAuthority,
)
from model_release_assurance.production_storage.backend import FixtureObjectStore, StorageError
from model_release_assurance.production_storage.contracts import FIXTURE_ID, ObjectReference, ReferenceError
from model_release_assurance.production_storage import service as service_module
from model_release_assurance.production_storage.service import FixtureStorageService


@dataclass(frozen=True)
class VerifiedIdentity:
    issuer: str
    subject: str
    client_id: str
    token_id: str
    key_id: str
    issued_at: int
    expires_at: int
    scopes: frozenset[str]
    case_ids: frozenset[str]
    acr: str | None
    auth_time: int | None


class Verifier:
    """Trusted verified-token fixture; cryptographic rejection has separate tests."""
    def __init__(self, tokens):
        self.tokens = tokens

    def verify(self, token, *, now):
        if type(token) is not str or token not in self.tokens:
            raise ValueError("Fixture token rejected")
        return self.tokens[token]


class ProductionStorageServiceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="mra-scoped-storage-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.now = 1000
        control = frozenset({"object:register", "object:metadata", "object:grant", "object:hold", "snapshot:freeze", "case:read"})
        workers = frozenset({"object:read", "job:job-a", "job:run", "object:metadata"})
        self.tokens = {}
        principals = {}
        kinds = {"steward": "human", "auditor": "human", "operator": "human", "worker": "workload", "worker-alias": "workload", "other-worker": "workload"}
        for name, kind in kinds.items():
            person = "person-worker" if name == "worker-alias" else "person-" + name
            self.tokens[name] = VerifiedIdentity("https://fixture.invalid", name, "fixture-client", "jti-" + name,
                "fixture-key", 1000, 1290, control if name == "steward" else workers if kind == "workload" or name == "operator" else frozenset({"object:metadata", "case:read"}),
                frozenset({"case-a", "case-b"}), "urn:mra:fixture:mfa" if kind == "human" else None,
                1000 if kind == "human" else None)
            principals[("https://fixture.invalid", name)] = PrincipalAuthority("https://fixture.invalid", name, person, kind,
                client_ids=frozenset({"fixture-client", "other-client"}))
        grants = [CaseGrant("person-steward", "agency-a", "project-a", "case-a", frozenset({"data_steward"})),
                  CaseGrant("person-steward", "agency-b", "project-b", "case-b", frozenset({"data_steward"})),
                  CaseGrant("person-auditor", "agency-a", "project-a", "case-a", frozenset({"auditor"})),
                  CaseGrant("person-operator", "agency-a", "project-a", "case-a", frozenset({"test_operator", "worker"})),
                  CaseGrant("person-worker", "agency-a", "project-a", "case-a", frozenset({"worker"})),
                  CaseGrant("person-other-worker", "agency-a", "project-a", "case-a", frozenset({"worker"}))]
        self.state = AuthorityState(1, 2000, True, frozenset({"fixture-key"}), frozenset(), principals, tuple(grants))
        self.verifier = Verifier(self.tokens)
        self.identity = FixtureIdentityService(self.verifier, self.state,
            [CaseRecord("case-a", "agency-a", "project-a", "owner-a"), CaseRecord("case-b", "agency-b", "project-b", "owner-b")],
            now=lambda: self.now)
        self.backend = FixtureObjectStore(self.root / "objects")
        self.service = FixtureStorageService(self.identity, self.backend)

    def register(self, *, case="case-a", retention=120):
        return self.service.register_fixture("steward", case, FIXTURE_ID, retention)["reference"]

    def grant(self, reference, *, worker="worker", ttl=30, job="job-a"):
        return self.service.issue_read_grant("steward", "case-a", reference, worker, job, ttl)

    def update(self, **changes):
        self.state = replace(self.state, revision=self.state.revision + 1, **changes)
        self.identity._replace_authority_for_fixture(self.state)

    def test_registration_metadata_and_single_read_are_exact_and_fixture_only(self):
        reference = self.register()
        metadata = self.service.metadata("auditor", "case-a", ObjectReference.from_dict(reference))
        self.assertEqual(metadata["reference"], reference)
        self.assertFalse(metadata["held"])
        grant = self.grant(reference)
        content = self.service.read("worker", "case-a", reference, grant["grant_id"])
        self.assertEqual(json.loads(content)["fixture_id"], FIXTURE_ID)
        self.assertEqual(len(content), reference["size_bytes"])
        for result in (metadata, grant):
            self.assertTrue(result["fixture_only"])
            self.assertFalse(result["authorization_eligible"])
            self.assertFalse(result["model_delivery"])
            self.assertNotIn("jti-", json.dumps(result))
        with self.assertRaises(PermissionDenied):
            self.service.read("worker", "case-a", reference, grant["grant_id"])

    def test_metadata_and_invalid_grants_never_read_object_bytes(self):
        reference = self.register()
        with mock.patch.object(self.backend, "read", side_effect=AssertionError("Unexpected byte read")):
            self.service.metadata("auditor", "case-a", reference)
            self.service.set_hold("steward", "case-a", reference, True)
            with self.assertRaises(PermissionDenied):
                self.service.read("worker", "case-a", reference, "0" * 32)
            with self.assertRaises(PermissionDenied):
                self.service.read("operator", "case-a", reference, "0" * 32)

    def test_human_job_operator_and_workload_without_worker_role_cannot_receive_bytes(self):
        reference = self.register()
        self.assertTrue(self.identity.check_job("operator", "case-a")["allowed"])
        with self.assertRaises(PermissionDenied):
            self.grant(reference, worker="operator")
        grant = self.grant(reference)
        with self.assertRaises(PermissionDenied):
            self.service.read("operator", "case-a", reference, grant["grant_id"])
        changed = tuple(replace(item, roles=frozenset({"test_operator"})) if item.person_id == "person-worker" else item for item in self.state.grants)
        self.update(grants=changed)
        with self.assertRaises(PermissionDenied):
            self.grant(reference)

    def test_humans_without_steward_role_cannot_mutate_fixture_custody(self):
        reference = self.register()
        for action in (lambda: self.service.register_fixture("auditor", "case-a", FIXTURE_ID, 10),
                       lambda: self.service.issue_read_grant("auditor", "case-a", reference, "worker", "job-a", 10),
                       lambda: self.service.set_hold("auditor", "case-a", reference, True),
                       lambda: self.service.freeze_snapshot("auditor", "case-a", [reference])):
            with self.assertRaises(PermissionDenied):
                action()
        with self.assertRaises(PermissionDenied):
            self.service.metadata("worker", "case-a", reference)

    def test_case_scope_and_exact_reference_identity_precede_byte_read(self):
        reference = self.register()
        other_case = self.register(case="case-b")
        grant = self.grant(reference)
        with mock.patch.object(self.backend, "read", side_effect=AssertionError("Unexpected byte read")):
            with self.assertRaises(PermissionDenied):
                self.service.metadata("steward", "case-a", other_case)
            with self.assertRaises(PermissionDenied):
                self.service.read("worker", "case-b", other_case, grant["grant_id"])
            with self.assertRaises(PermissionDenied):
                self.service.metadata("steward", "case-a", dict(reference, agency_id="other-agency"))
            with self.assertRaises(StorageError):
                self.service.metadata("steward", "case-a", dict(reference, sha256="f" * 64))
            with self.assertRaises(StorageError):
                self.service.metadata("steward", "case-a", dict(reference, version_id="0" * 32))
            with self.assertRaises(ReferenceError):
                self.service.metadata("steward", "case-a", dict(reference, path="/arbitrary"))

    def test_grant_is_bound_to_exact_object_and_entire_verified_worker_identity(self):
        reference, other = self.register(), self.register()
        grant = self.grant(reference)
        with self.assertRaises(PermissionDenied):
            self.service.read("worker", "case-a", other, grant["grant_id"])
        original = self.tokens["worker"]
        variants = [replace(original, client_id="other-client"), replace(original, token_id="new-jti"),
                    replace(original, issued_at=999), replace(original, expires_at=1289),
                    replace(original, scopes=original.scopes - {"job:run"}), self.tokens["worker-alias"], self.tokens["other-worker"]]
        for variant in variants:
            self.tokens["replacement"] = variant
            with self.assertRaises(PermissionDenied):
                self.service.read("replacement", "case-a", reference, grant["grant_id"])
        self.assertFalse(self.service._grants[grant["grant_id"]].consumed)
        self.assertTrue(self.service.read("worker", "case-a", reference, grant["grant_id"]))

    def test_grant_requires_signed_job_scope_and_explicit_target_token(self):
        reference = self.register()
        with self.assertRaises(PermissionDenied):
            self.grant(reference, job="job-b")
        with self.assertRaises(ValueError):
            self.grant(reference, worker=self.tokens["worker"])
        with self.assertRaises(ValueError):
            self.grant(reference, worker="unknown-token")
        self.assertFalse(self.service._grants)

    def test_grant_lifetime_cannot_exceed_either_token_or_sixty_seconds(self):
        reference = self.register()
        self.tokens["worker"] = replace(self.tokens["worker"], expires_at=1020)
        grant = self.grant(reference, ttl=60)
        self.assertEqual(grant["expires_at"], 1020)
        self.tokens["steward"] = replace(self.tokens["steward"], expires_at=1008)
        self.assertEqual(self.grant(reference, ttl=60)["expires_at"], 1008)
        for ttl in (True, 0, 61, 1.0):
            with self.assertRaises(ValueError):
                self.grant(reference, ttl=ttl)

    def test_steward_expiry_during_target_verification_prevents_grant_mutation(self):
        reference = self.register()
        self.tokens["steward"] = replace(self.tokens["steward"], expires_at=1005)
        original = self.verifier.verify
        def delayed(token, *, now):
            value = original(token, now=now)
            if token == "worker":
                self.now = 1005
            return value
        with mock.patch.object(self.verifier, "verify", side_effect=delayed):
            with self.assertRaises(PermissionDenied):
                self.grant(reference)
        self.assertFalse(self.service._grants)

    def test_post_io_grant_deadline_boundary_returns_no_bytes_and_does_not_consume(self):
        reference = self.register()
        grant = self.grant(reference, ttl=10)
        original = self.backend.read
        def delayed(value):
            content = original(value)
            self.now = grant["expires_at"]
            return content
        with mock.patch.object(self.backend, "read", side_effect=delayed):
            with self.assertRaises(PermissionDenied):
                self.service.read("worker", "case-a", reference, grant["grant_id"])
        self.assertFalse(self.service._grants[grant["grant_id"]].consumed)

    def test_post_io_worker_or_authority_expiry_is_denied(self):
        reference = self.register()
        self.tokens["worker"] = replace(self.tokens["worker"], expires_at=1010)
        grant = self.grant(reference, ttl=30)
        original = self.backend.read
        def delayed(value):
            content = original(value)
            self.now = 1010
            return content
        with mock.patch.object(self.backend, "read", side_effect=delayed):
            with self.assertRaises(PermissionDenied):
                self.service.read("worker", "case-a", reference, grant["grant_id"])
        self.assertFalse(self.service._grants[grant["grant_id"]].consumed)

    def test_corrupt_bytes_do_not_consume_grant_and_verified_repair_may_retry(self):
        reference = self.register()
        grant = self.grant(reference)
        path = self.backend._root / (reference["object_id"] + "." + reference["version_id"] + ".json")
        original = path.read_bytes()
        path.write_bytes(original.replace(b'12', b'13'))
        with self.assertRaises(StorageError):
            self.service.read("worker", "case-a", reference, grant["grant_id"])
        self.assertFalse(self.service._grants[grant["grant_id"]].consumed)
        path.write_bytes(original)
        self.assertEqual(self.service.read("worker", "case-a", reference, grant["grant_id"]), original)

    def test_concurrent_redemption_releases_at_most_one_copy(self):
        reference = self.register()
        grant = self.grant(reference)
        def read_once():
            try:
                return isinstance(self.service.read("worker", "case-a", reference, grant["grant_id"]), bytes)
            except PermissionDenied:
                return "denied"
        with ThreadPoolExecutor(max_workers=2) as executor:
            result = list(executor.map(lambda _: read_once(), range(2)))
        self.assertCountEqual(result, [True, "denied"])

    def test_revoke_then_new_grant_never_revives_or_reuses_old_grant(self):
        reference = self.register()
        old = self.grant(reference)
        self.assertTrue(self.service.revoke_grant("steward", "case-a", old["grant_id"])["revoked"])
        new = self.grant(reference)
        self.assertNotEqual(old["grant_id"], new["grant_id"])
        with self.assertRaises(PermissionDenied):
            self.service.read("worker", "case-a", reference, old["grant_id"])
        self.assertTrue(self.service.read("worker", "case-a", reference, new["grant_id"]))
        self.assertIn(old["grant_id"], self.service._grants)

    def test_current_authority_outage_change_and_revoked_worker_deny_old_grants(self):
        reference = self.register()
        old = self.grant(reference)
        self.update(available=False)
        with self.assertRaises(IdentityUnavailable):
            self.service.read("worker", "case-a", reference, old["grant_id"])
        self.update(available=True)
        with self.assertRaises(PermissionDenied):
            self.service.read("worker", "case-a", reference, old["grant_id"])
        self.update(revoked_token_ids=frozenset({self.tokens["worker"].token_id}))
        with self.assertRaises(PermissionDenied):
            self.grant(reference)
        self.update(revoked_token_ids=frozenset())
        with self.assertRaises(PermissionDenied):
            self.grant(reference)

    def test_retention_hold_and_active_grant_all_block_eligibility_without_deletion(self):
        reference = self.register(retention=5)
        grant = self.grant(reference)
        self.service.set_hold("steward", "case-a", reference, True)
        result = self.service.deletion_eligibility("steward", "case-a", reference)
        self.assertCountEqual(result["blockers"], ["retention_active", "hold_active", "active_read_grant"])
        self.assertFalse(result["eligible_for_deletion"])
        self.assertFalse(result["deletion_performed"])
        self.now = 1005
        self.service.set_hold("steward", "case-a", reference, False)
        self.assertEqual(self.service.deletion_eligibility("steward", "case-a", reference)["blockers"], ["active_read_grant"])
        self.service.revoke_grant("steward", "case-a", grant["grant_id"])
        self.assertTrue(self.service.deletion_eligibility("steward", "case-a", reference)["eligible_for_deletion"])
        self.assertTrue(self.backend.read(ObjectReference.from_dict(reference)))

    def test_hold_is_deletion_only_and_does_not_bypass_or_revoke_read_authority(self):
        reference = self.register()
        grant = self.grant(reference)
        self.service.set_hold("steward", "case-a", reference, True)
        self.assertTrue(self.service.read("worker", "case-a", reference, grant["grant_id"]))
        with self.assertRaises(ValueError):
            self.service.set_hold("steward", "case-a", reference, 1)

    def test_snapshot_freezes_exact_references_and_minimum_retention_without_user_provenance(self):
        first, second = self.register(retention=100), self.register(retention=50)
        snapshot = self.service.freeze_snapshot("steward", "case-a", [first, ObjectReference.from_dict(second)])
        self.assertEqual(snapshot["snapshot"]["objects"], [first, second])
        self.assertEqual(snapshot["snapshot"]["retention_until"], 1050)
        self.assertFalse(snapshot["authorization_eligible"])
        for refs in ([], [first, first], [first] * 9):
            with self.assertRaises(ValueError):
                self.service.freeze_snapshot("steward", "case-a", refs)
        with self.assertRaises(PermissionDenied):
            self.service.freeze_snapshot("steward", "case-a", [self.register(case="case-b")])

    def test_capacity_preserves_consumed_tombstones_and_rejects_reused_identifiers(self):
        reference = self.register()
        grant = self.grant(reference)
        self.service.read("worker", "case-a", reference, grant["grant_id"])
        with mock.patch.object(service_module, "MAX_GRANTS", 1):
            with self.assertRaises(Conflict):
                self.grant(reference)
        with mock.patch.object(service_module.uuid, "uuid4", return_value=type("Id", (), {"hex": grant["grant_id"]})()):
            with self.assertRaises(Conflict):
                self.grant(reference)
        self.assertTrue(self.service._grants[grant["grant_id"]].consumed)

    def test_catalog_only_and_retention_bounds_refuse_arbitrary_input_before_backend_io(self):
        with mock.patch.object(self.backend, "register_fixture", side_effect=AssertionError("Unexpected registration")):
            for fixture in ("/tmp/private.json", "https://example.invalid/data", "unknown", b"raw bytes"):
                with self.assertRaises(ValueError):
                    self.service.register_fixture("steward", "case-a", fixture, 10)
            for retention in (0, True, 86401, 1.5):
                with self.assertRaises(ValueError):
                    self.service.register_fixture("steward", "case-a", FIXTURE_ID, retention)


    def test_authority_snapshot_expiry_during_read_denies_without_consuming(self):
        self.update(fresh_until=1005)
        reference = self.register()
        grant = self.grant(reference)
        original = self.backend.read
        def delayed(value):
            content = original(value)
            self.now = 1005
            return content
        with mock.patch.object(self.backend, "read", side_effect=delayed):
            with self.assertRaises(IdentityUnavailable):
                self.service.read("worker", "case-a", reference, grant["grant_id"])
        self.assertFalse(self.service._grants[grant["grant_id"]].consumed)


if __name__ == "__main__":
    unittest.main()
