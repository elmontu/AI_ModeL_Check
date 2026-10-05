"""Real-signed key lifecycle integration with identity reviews and storage grants."""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
import tempfile
from threading import Event
import unittest
from unittest import mock
import uuid

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import jwt

from model_release_assurance.production_identity.policy import (
 AuthorityState, CaseGrant, CaseRecord, FixtureIdentityService, IdentityUnavailable,
 PermissionDenied, PrincipalAuthority)
from model_release_assurance.production_identity.tokens import AccessTokenVerifier, TokenError
from model_release_assurance.production_storage.backend import FixtureObjectStore
from model_release_assurance.production_storage.service import FixtureStorageService
from model_release_assurance.production_trust.registry import (
 FixtureTrustRegistry, KeyRegistration, TrustProfile)
from model_release_assurance.production_trust.verification import RegistryAccessTokenVerifier

ISSUER="https://fixture-trust.example.invalid"
AUDIENCE="urn:mra:fixture:trust"
SCOPE="case:read proposal:submit review:assess review:approve object:register object:metadata object:grant object:read job:fixture-job"
ROLES={"owner":{"model_owner"},"assessor":{"assessor"},"approver":{"release_authority"},
       "steward":{"data_steward"},"worker":{"worker"}}


class ProductionTrustIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.keys={name:rsa.generate_private_key(public_exponent=65537,key_size=2048)
                  for name in ("key-a","key-b","key-c")}

    def setUp(self):
        self.now=1000
        self.profile=TrustProfile(agency_id="agency",environment="public_fixture",
                                 issuer=ISSUER,audience=AUDIENCE,purpose="access_token")
        self.registry=FixtureTrustRegistry(now=lambda:self.now,fresh_until=1120)
        self.registry.enroll(self.record("key-a"),expected_revision=self.registry.revision)
        self.verifier=RegistryAccessTokenVerifier(self.registry,self.profile)
        principals={(ISSUER,name):PrincipalAuthority(ISSUER,name,"person-"+name,
                         "workload" if name=="worker" else "human",client_ids=frozenset({"client"}))
                    for name in ROLES}
        grants=tuple(CaseGrant("person-"+name,"agency","project","case-a",frozenset(roles))
                     for name,roles in ROLES.items())
        self.authority=AuthorityState(1,1290,True,frozenset(self.keys),frozenset(),principals,grants)
        self.identity=FixtureIdentityService(self.verifier,self.authority,
                     [CaseRecord("case-a","agency","project","person-owner")],now=lambda:self.now)
        self.temporary=tempfile.TemporaryDirectory(prefix="mra-trust-integration-")
        self.addCleanup(self.temporary.cleanup)
        self.backend=FixtureObjectStore(Path(self.temporary.name)/"store")
        self.storage=FixtureStorageService(self.identity,self.backend)

    def record(self,key_id,**changes):
        fields=dict(key_id=key_id,profile=self.profile,owner_id="fixture-idp",
                    public_key_pem=self.keys[key_id].public_key().public_bytes(
                     serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo),
                    not_before=990,not_after=2000)
        fields.update(changes)
        return KeyRegistration(**fields)

    def token(self,subject="owner",key_id="key-a",**changes):
        claims={"iss":ISSUER,"aud":AUDIENCE,"sub":subject,"iat":self.now,"nbf":self.now,
                "exp":self.now+90,"jti":uuid.uuid4().hex,"client_id":"client",
                "scope":SCOPE,"case_ids":["case-a"]}
        if subject!="worker":claims.update(acr="urn:mra:fixture:mfa",auth_time=self.now)
        claims.update(changes)
        return jwt.encode(claims,self.keys[key_id],algorithm="RS256",headers={"kid":key_id,"typ":"at+jwt"})

    def rotate(self,overlap=20):
        return self.registry.rotate("key-a",self.record("key-b"),
                     expected_revision=self.registry.revision,overlap_seconds=overlap)

    def make_grant(self):
        steward=self.token("steward")
        worker=self.token("worker")
        ref=self.storage.register_fixture(steward,"case-a","public-counts-v1",60)["reference"]
        grant=self.storage.issue_read_grant(steward,"case-a",ref,worker,"fixture-job",30)
        return ref,grant["grant_id"],worker

    def test_identity_and_registry_share_operation_lock_and_real_token_verifies(self):
        self.assertIs(self.identity._lock,self.registry.operation_lock)
        result=self.identity.read_case(self.token(),"case-a")
        self.assertFalse(result["authorization_eligible"])
        self.assertEqual(self.verifier.verify(self.token(),now=self.now).subject,"owner")

    def test_rotation_overlap_and_strict_old_key_issuance_cutoff(self):
        old=self.token()
        self.now=1001
        self.rotate(overlap=10)
        self.assertEqual(self.verifier.verify(old,now=self.now).key_id,"key-a")
        self.assertEqual(self.verifier.verify(self.token(key_id="key-b"),now=self.now).key_id,"key-b")
        with self.assertRaises(TokenError):
            self.verifier.verify(self.token(key_id="key-a"),now=self.now)
        self.now=1011
        with self.assertRaises(TokenError):
            self.verifier.verify(old,now=self.now)

    def test_enrollment_does_not_override_current_identity_authority_key_allowlist(self):
        self.registry.enroll(self.record("key-b"),expected_revision=self.registry.revision)
        self.authority=replace(self.authority,revision=2,active_key_ids=frozenset({"key-a"}))
        self.identity._replace_authority_for_fixture(self.authority)
        token=self.token(key_id="key-b")
        self.assertEqual(self.verifier.verify(token,now=self.now).key_id,"key-b")
        with self.assertRaises(PermissionDenied):
            self.identity.read_case(token,"case-a")

    def test_signature_profile_constraints_remain_strict_after_registry_integration(self):
        for changes in ({"aud":"other"},{"iss":"https://wrong.example.invalid"},
                        {"scope":"*"},{"role":"release_authority"},{"exp":1301},
                        {"case_ids":["case-a","case-a"]}):
            with self.subTest(changes=changes),self.assertRaises(TokenError):
                self.verifier.verify(self.token(**changes),now=self.now)
        token=self.token()
        parts=token.split(".")
        forged=parts[0]+"."+parts[1]+"."+("A" if parts[2][0]!="A" else "B")+parts[2][1:]
        with self.assertRaises(TokenError):self.verifier.verify(forged,now=self.now)

    def test_stale_and_unavailable_registry_never_use_previously_valid_cached_trust(self):
        token=self.token()
        self.verifier.verify(token,now=self.now)
        self.registry.set_available(False,expected_revision=self.registry.revision)
        with self.assertRaises(IdentityUnavailable):self.verifier.verify(token,now=self.now)
        with self.assertRaises(IdentityUnavailable):self.identity.read_case(token,"case-a")
        self.registry.set_available(True,expected_revision=self.registry.revision)
        self.now=1120
        with self.assertRaises(IdentityUnavailable):
            self.verifier.verify(self.token(),now=self.now)

    def test_revocation_cannot_be_bypassed_by_static_authority_or_recovery_refresh(self):
        token=self.token()
        self.registry.revoke("key-a",expected_revision=self.registry.revision)
        self.registry.refresh(fresh_until=1200,expected_revision=self.registry.revision)
        self.assertIn("key-a",self.authority.active_key_ids)
        with self.assertRaises(TokenError):self.identity.read_case(token,"case-a")

    def test_changed_trust_profile_and_purpose_do_not_select_another_domains_key(self):
        other=RegistryAccessTokenVerifier(self.registry,replace(self.profile,agency_id="another-agency"))
        with self.assertRaises(TokenError):other.verify(self.token(),now=self.now)
        with self.assertRaises(ValueError):
            RegistryAccessTokenVerifier(self.registry,replace(self.profile,purpose="worker_evidence"))

    def test_backward_registry_clock_and_future_identity_observation_fail_closed(self):
        token=self.token()
        self.verifier.verify(token,now=self.now)
        with self.assertRaises(IdentityUnavailable):
            self.verifier.verify(token,now=self.now+1)
        self.now=999
        with self.assertRaises(IdentityUnavailable):self.verifier.verify(token,now=self.now)

    def test_registry_deadline_crossed_during_crypto_returns_no_identity(self):
        token=self.token(exp=1290)
        original=AccessTokenVerifier.verify
        def delayed(verifier,value,*,now):
            identity=original(verifier,value,now=now)
            self.now=1120
            return identity
        with mock.patch.object(AccessTokenVerifier,"verify",new=delayed):
            with self.assertRaises(IdentityUnavailable):self.verifier.verify(token,now=1000)

    def test_rotation_overlap_crossed_during_crypto_returns_no_identity(self):
        token=self.token()
        self.now=1001
        self.rotate(overlap=10)
        original=AccessTokenVerifier.verify
        def delayed(verifier,value,*,now):
            identity=original(verifier,value,now=now)
            self.now=1011
            return identity
        with mock.patch.object(AccessTokenVerifier,"verify",new=delayed):
            with self.assertRaises(TokenError):self.verifier.verify(token,now=1001)

    def test_saved_reviews_are_invalidated_by_key_revocation_without_role_revision(self):
        payload={"artifact_sha256":"a"*64,"evidence_sha256":"b"*64,"policy_sha256":"c"*64,
                 "recipient_id":"fixture-recipient","revision":1}
        digest=self.identity.submit_proposal(self.token(),"case-a",payload)["proposal_digest"]
        self.identity.assess(self.token("assessor"),"case-a",digest)
        self.assertTrue(self.identity.approve(self.token("approver"),"case-a",digest)["reviews_usable"])
        self.registry.enroll(self.record("key-b"),expected_revision=self.registry.revision)
        self.registry.revoke("key-a",expected_revision=self.registry.revision)
        result=self.identity.read_case(self.token(key_id="key-b"),"case-a")
        self.assertFalse(result["reviews_usable"])
        self.assertEqual(self.identity._authority.revision,1)

    def test_outstanding_storage_grant_is_denied_on_key_revocation_before_body_io(self):
        ref,grant_id,worker=self.make_grant()
        self.registry.revoke("key-a",expected_revision=self.registry.revision)
        with mock.patch.object(self.backend,"read",side_effect=AssertionError("No content I/O allowed")):
            with self.assertRaises(TokenError):self.storage.read(worker,"case-a",ref,grant_id)
        self.assertFalse(self.storage._grants[grant_id].consumed)

    def test_outage_during_storage_io_returns_no_bytes_and_does_not_consume(self):
        ref,grant_id,worker=self.make_grant()
        original=self.backend.read
        def delayed(reference):
            content=original(reference)
            self.registry.set_available(False,expected_revision=self.registry.revision)
            return content
        with mock.patch.object(self.backend,"read",side_effect=delayed):
            with self.assertRaises(IdentityUnavailable):
                self.storage.read(worker,"case-a",ref,grant_id)
        self.assertFalse(self.storage._grants[grant_id].consumed)

    def test_concurrent_revocation_serializes_with_authorized_byte_read(self):
        ref,grant_id,worker=self.make_grant()
        reading,revoke_attempted,allow_read=Event(),Event(),Event()
        original=self.backend.read
        def delayed(reference):
            reading.set()
            if not allow_read.wait(5):raise AssertionError("Read synchronization failed")
            return original(reference)
        def revoke():
            revoke_attempted.set()
            return self.registry.revoke("key-a",expected_revision=self.registry.revision)
        with mock.patch.object(self.backend,"read",side_effect=delayed),ThreadPoolExecutor(max_workers=2) as pool:
            read_future=pool.submit(self.storage.read,worker,"case-a",ref,grant_id)
            try:
                self.assertTrue(reading.wait(5))
                revoke_future=pool.submit(revoke)
                self.assertTrue(revoke_attempted.wait(5))
                self.assertFalse(revoke_future.done())
            finally:
                allow_read.set()
            self.assertTrue(read_future.result(timeout=5))
            revoke_future.result(timeout=5)
        with self.assertRaises(TokenError):self.verifier.verify(worker,now=self.now)


    def test_registry_clock_governs_grant_deadline_even_if_legacy_clock_is_stale(self):
        identity=FixtureIdentityService(self.verifier,self.authority,
                 [CaseRecord("case-a","agency","project","person-owner")],now=lambda:1000)
        storage=FixtureStorageService(identity,self.backend)
        steward,worker=self.token("steward"),self.token("worker")
        ref=storage.register_fixture(steward,"case-a","public-counts-v1",60)["reference"]
        grant=storage.issue_read_grant(steward,"case-a",ref,worker,"fixture-job",5)
        self.now=1005
        with mock.patch.object(self.backend,"read",side_effect=AssertionError("Expired grant must not read bytes")):
            with self.assertRaises(PermissionDenied):
                storage.read(worker,"case-a",ref,grant["grant_id"])
        self.assertFalse(storage._grants[grant["grant_id"]].consumed)

    def test_identity_refuses_partial_dynamic_trust_capabilities(self):
        for supplied in (
            {"operation_lock":self.registry.operation_lock},
            {"check_current":self.verifier.check_current},
            {"operation_lock":self.registry.operation_lock,"check_current":self.verifier.check_current},
        ):
            verifier=type("IncompleteTrustedVerifier",(),{"verify":lambda *args,**kwargs:None,**supplied})()
            with self.subTest(fields=tuple(supplied)),self.assertRaises(ValueError):
                FixtureIdentityService(verifier,self.authority,
                 [CaseRecord("case-a","agency","project","person-owner")],now=lambda:self.now)


    def test_dynamic_trust_agency_cannot_be_reused_for_other_agency_cases(self):
        with self.assertRaises(ValueError):
            FixtureIdentityService(self.verifier,self.authority,
                [CaseRecord("case-b","another-agency","project","person-owner")],now=lambda:self.now)


if __name__=="__main__":unittest.main()
