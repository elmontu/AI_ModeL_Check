"""Ephemeral signed identities and fixed public data for the registry rehearsal.

No external input, production identity, arbitrary model, listener or network
operation is accepted. The synthetic clock makes deadline tests reproducible.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import uuid

from ..production_identity.policy import (AuthorityState, CaseGrant, CaseRecord,
    FixtureIdentityService, PrincipalAuthority, PermissionDenied)
from ..production_storage.backend import FixtureObjectStore, StorageError
from ..production_storage.service import FixtureStorageService
from ..production_trust.registry import FixtureTrustRegistry, TrustProfile
from ..production_trust.signer import FixtureTokenIssuer, MemoryFixtureSigningProvider
from ..production_trust.verification import RegistryAccessTokenVerifier
from .contracts import FLAGS, digest
from .store import RegistryStore, StoreConflict, StoreUnavailable
from .service import FixtureRegistryService
from .receiver import FixtureEventReceiver

ISSUER = "https://fixture-registry.example.invalid"
AUDIENCE = "urn:mra:public-fixture:registry"
ROLES = {"operator": {"test_operator"}, "other": {"test_operator"},
         "steward": {"data_steward"}, "auditor": {"auditor"},
         "worker": {"worker"}, "worker2": {"worker"}}


class RegistryFixture:
    """Trusted test bootstrap only, deliberately in-memory authority/storage."""

    def __init__(self, root, *, schema_version=2):
        self.root = Path(root)
        self.root.mkdir(exist_ok=True)
        self.now = 1000
        self.clock = lambda: self.now
        profile = TrustProfile(agency_id="agency", environment="public_fixture", issuer=ISSUER,
                               audience=AUDIENCE, purpose="access_token")
        self.trust = FixtureTrustRegistry(now=self.clock, fresh_until=1250)
        provider = MemoryFixtureSigningProvider()
        for key_id in ("human-key", "worker-key"):
            record = provider.create_key(key_id=key_id, profile=profile, owner_id="fixture-idp",
                                         not_before=999, not_after=1300)
            self.trust.enroll(record, expected_revision=self.trust.revision)
        self.issuer = FixtureTokenIssuer(self.trust,
            provider.bind(profile=profile, owner_id="fixture-idp"), profile, "fixture-idp")
        verifier = RegistryAccessTokenVerifier(self.trust, profile)
        principals = {(ISSUER, subject): PrincipalAuthority(ISSUER, subject, "person-" + subject,
            "workload" if subject.startswith("worker") else "human", client_ids=frozenset({"client"}))
            for subject in ROLES}
        cases = [CaseRecord("case-a", "agency", "project", "person-owner"),
                 CaseRecord("case-b", "agency", "project", "person-owner"),
                 CaseRecord("case-c", "agency", "unconfigured", "person-owner")]
        grants = tuple(CaseGrant("person-" + subject, case.agency_id, case.project_id, case.case_id,
                                frozenset(roles)) for subject, roles in ROLES.items() for case in cases)
        self.authority = AuthorityState(1, 1250, True, frozenset({"human-key", "worker-key"}),
                                       frozenset(), principals, grants)
        self.identity = FixtureIdentityService(verifier, self.authority, cases, now=self.clock)
        self.storage = FixtureStorageService(self.identity, FixtureObjectStore(self.root / "objects"))
        self.store = RegistryStore.create(self.root / "registry", accounts=[
            {"agency_id": "agency", "project_id": "project"}], schema_version=schema_version)
        self.service = FixtureRegistryService(self.identity, self.storage, self.store)
        self.references = {case: self.storage.register_fixture(self.token("steward"), case,
                           "public-counts-v1", 240)["reference"] for case in ("case-a", "case-b", "case-c")}

    def token(self, subject, *, cases=None, scopes=None, expires_at=1240):
        if scopes is None:
            scopes = {"object:register", "case:read"} if subject == "steward" else (
                {"job:run"} if subject.startswith("worker") else (
                    {"case:read"} if subject == "auditor" else {"job:run", "case:read"}))
        claims = {"iss": ISSUER, "aud": AUDIENCE, "sub": subject, "client_id": "client",
            "jti": uuid.uuid4().hex, "iat": self.now, "nbf": self.now, "exp": expires_at,
            "scope": " ".join(sorted(scopes)), "case_ids": cases or ["case-a", "case-b", "case-c"]}
        if not subject.startswith("worker"):
            claims.update(acr="urn:mra:fixture:mfa", auth_time=self.now)
        return self.issuer.issue("worker-key" if subject.startswith("worker") else "human-key", claims)

    def request(self, case="case-a", *, subject="operator", request_id=None):
        return self.service.prepare(self.token(subject), case, self.references[case], request_id or uuid.uuid4().hex)

    def commit(self, request):
        return self.service.commit(self.token("operator"), request["case_id"], request)

    def update(self, **changes):
        self.authority = replace(self.authority, revision=self.authority.revision + 1, **changes)
        self.identity._replace_authority_for_fixture(self.authority)


def exercise(output):
    """Actual signed workflow, schema migration and local outbox deduplication."""
    fixture = RegistryFixture(output, schema_version=1)
    checks = []
    def check(name, condition):
        checks.append({"name": name, "passed": bool(condition)})
        if not condition:
            raise RuntimeError("Registry rehearsal failed: " + name)
    def denied(action, exceptions=(StoreConflict, StoreUnavailable, PermissionDenied, StorageError)):
        try:
            action()
        except exceptions:
            return True
        return False
    request = fixture.request()
    first = fixture.commit(request)
    check("exact_retry_with_new_token_returns_original_receipt", first == fixture.commit(request))
    alternate = {**request, "request_id": uuid.uuid4().hex}
    check("stale_shared_head_is_rejected", denied(lambda: fixture.commit(alternate)))
    other = fixture.request("case-b")
    second = fixture.commit(other)
    check("second_case_shares_charge_total", second["receipt"]["total_engineering_charge_units"] == 2)
    before = fixture.store.inspect(guard=fixture.clock)
    old_service = fixture.service
    store = RegistryStore.migrate(fixture.store.root, fixture.store.store_id,
                                  from_version=1, to_version=2, guard=fixture.clock)
    fixture.store = store
    fixture.service = FixtureRegistryService(fixture.identity, fixture.storage, store)
    check("migration_preserves_store_and_receipts", store.store_id == before["store_id"]
          and fixture.commit(request) == first and fixture.commit(other) == second)
    check("old_broker_is_fenced", denied(lambda: old_service.read(fixture.token("auditor"), "case-a", request["request_id"])))
    check("unconfigured_scope_cannot_create_capacity", denied(lambda: fixture.request("case-c")))
    receiver = FixtureEventReceiver.create(Path(output) / "receiver")
    worker = fixture.token("worker")
    claim = fixture.service.claim_outbox(worker, "case-a", 5)
    received = receiver.receive(claim["event"], guard=fixture.clock)
    fixture.now += 6  # Receiver applied; sender never got its acknowledgement.
    again = fixture.service.claim_outbox(fixture.token("worker"), "case-a", 5)
    repeated = receiver.receive(again["event"], guard=fixture.clock)
    check("lost_ack_redelivers_same_event_once_at_receiver", claim["event"] == again["event"]
          and claim["lease"] != again["lease"] and repeated == received)
    check("stale_lease_cannot_acknowledge", denied(lambda: fixture.service.acknowledge(worker, "case-a", claim["lease"])))
    check("different_worker_cannot_acknowledge", denied(lambda: fixture.service.acknowledge(fixture.token("worker2"), "case-a", again["lease"])))
    ack = fixture.service.acknowledge(fixture.token("worker"), "case-a", again["lease"])
    check("acknowledgement_is_idempotent", ack == fixture.service.acknowledge(fixture.token("worker"), "case-a", again["lease"]))
    check("outbox_claim_is_case_scoped", fixture.service.claim_outbox(fixture.token("worker"), "case-a") is None)
    pending = fixture.service.claim_outbox(fixture.token("worker"), "case-b")
    receiver.receive(pending["event"], guard=fixture.clock)
    fixture.service.acknowledge(fixture.token("worker"), "case-b", pending["lease"])
    state = fixture.service.state(fixture.token("auditor"), "case-a")
    check("publication_does_not_change_charge", state["account"]["total_engineering_charge_units"] == 2)
    reopened = FixtureEventReceiver.open(receiver.root, receiver.receiver_id)
    check("receiver_restart_retains_two_effects", reopened.snapshot(guard=fixture.clock)["applied_events"] == 2)
    # A true storage restart has no catalog for old references. Historical
    # metadata remains readable, but cannot reauthorize a fixture commit.
    empty = FixtureStorageService(fixture.identity, FixtureObjectStore(Path(output) / "fresh-objects"))
    restarted = FixtureRegistryService(fixture.identity, empty,
                                      RegistryStore.open(store.root, store.store_id))
    check("history_read_does_not_recreate_storage_authority",
        restarted.read(fixture.token("auditor"), "case-a", request["request_id"]) == first
        and denied(lambda: restarted.commit(fixture.token("operator"), "case-a", request)))
    final = store.inspect(guard=fixture.clock)
    check("one_charge_receipt_event_per_committed_request", final["receipt_count"] == 2
          and final["outbox_acknowledged"] == 2 and final["outbox_pending"] == 0)
    return {"schema": "mra-fixture-registry-rehearsal/v1", "status": "passed", "checks": checks,
        "summary": {"committed_requests": 2, "engineering_charge_units": 2,
                    "receiver_effects": 2, "migration": "v1_to_v2", "schema_version": 2},
        "evidence": {"first_receipt": first, "second_receipt": second,
                     "registry": final, "receiver": reopened.snapshot(guard=fixture.clock)},
        "independent_witness": False, "storage_authority_restart_durable": False,
        "postgresql_tested": False, "cloud_failover_tested": False, **FLAGS}
