"""One fresh public Wine run with policy-before-fit and independent reviews.

This trusted bootstrap generates only ephemeral fixture identities. It accepts
no model, policy evidence, private dataset, key material or caller admission.
"""
from __future__ import annotations

from dataclasses import asdict, replace
from pathlib import Path
import uuid

from ..production_identity.policy import (AuthorityState, CaseGrant, CaseRecord,
    FixtureIdentityService, PrincipalAuthority, PermissionDenied, IdentityUnavailable)
from ..production_trust.registry import FixtureTrustRegistry, TrustProfile
from ..production_trust.signer import FixtureTokenIssuer, MemoryFixtureSigningProvider
from ..production_trust.verification import RegistryAccessTokenVerifier
from ..production_evidence.ledger import ReplayLedger
from ..production_evidence.signing import MemoryFixtureEvidenceSigner
from ..production_registration.store import RegistrationStore
from ..production_registration.workflow import LocalRegistrationWorkflow
from .contracts import FLAGS, ReviewError
from .store import ReviewStore, StoreConflict, StoreUnavailable
from .service import FixtureReviewService

ISSUER = 'https://fixture-review.example.invalid'
AUDIENCE = 'urn:mra:public-fixture:review'
ROLES = {'owner': {'model_owner', 'assessor'},
    'operator': {'test_operator', 'release_authority'}, 'policy': {'policy_authority'},
    'assessor': {'assessor'}, 'releaser': {'release_authority'},
    'delegatepolicy': {'policy_authority'}, 'auditor': {'auditor'}}
SCOPES = frozenset({'case:read', 'proposal:submit', 'job:run', 'review:policy',
                    'review:assess', 'review:approve', 'review:delegate'})


class ReviewFixture:
    """Trusted local fixture only; generated credentials are never persisted."""
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(exist_ok=True)
        self.now = 1000
        self.clock = lambda: self.now
        profile = TrustProfile('agency', 'public_fixture', ISSUER, AUDIENCE, 'access_token')
        self.trust = FixtureTrustRegistry(now=self.clock, fresh_until=1250)
        provider = MemoryFixtureSigningProvider()
        key = provider.create_key(key_id='human-key', profile=profile, owner_id='fixture-idp',
                                  not_before=999, not_after=1300)
        self.trust.enroll(key, expected_revision=self.trust.revision)
        evidence_profile = TrustProfile('agency', 'public_fixture', ISSUER,
                                        'urn:mra:public-fixture:evidence', 'worker_evidence')
        signer = MemoryFixtureEvidenceSigner(evidence_profile, 'fixture-worker', 'review-evidence-key', 999, 1300)
        self.trust.enroll(signer.registration, expected_revision=self.trust.revision)
        self.issuer = FixtureTokenIssuer(self.trust,
            provider.bind(profile=profile, owner_id='fixture-idp'), profile, 'fixture-idp')
        subjects = {name: 'person-' + name for name in ROLES}
        subjects['owner-alias'] = 'person-owner'
        principals = {(ISSUER, subject): PrincipalAuthority(ISSUER, subject, person,
            'human', client_ids=frozenset({'client'})) for subject, person in subjects.items()}
        self.cases = [CaseRecord(name, 'agency', 'project', 'person-owner')
                      for name in ('case-a', 'case-b', 'case-c')]
        grants = tuple(CaseGrant('person-' + subject, case.agency_id, case.project_id,
            case.case_id, frozenset(roles)) for subject, roles in ROLES.items() for case in self.cases)
        self.authority = AuthorityState(1, 1250, True, frozenset({'human-key'}),
                                       frozenset(), principals, grants)
        self.identity = FixtureIdentityService(RegistryAccessTokenVerifier(self.trust, profile),
                                              self.authority, self.cases, now=self.clock)
        self.store = ReviewStore.create(self.root / 'reviews', cases=[asdict(case) for case in self.cases], guard=self.clock)
        self.workflow = LocalRegistrationWorkflow(self.trust, signer,
            RegistrationStore.create(self.root / 'registrations'), ReplayLedger.create(self.root / 'replay-ledger'))
        self.service = FixtureReviewService(self.identity, self.store, self.workflow)

    def token(self, subject, *, cases=None, scopes=None, expires_at=1240):
        claims = {'iss': ISSUER, 'aud': AUDIENCE, 'sub': subject, 'client_id': 'client',
            'jti': uuid.uuid4().hex, 'iat': self.now, 'nbf': self.now, 'exp': expires_at,
            'scope': ' '.join(sorted(SCOPES if scopes is None else scopes)),
            'case_ids': ['case-a', 'case-b', 'case-c'] if cases is None else cases,
            'acr': 'urn:mra:fixture:mfa', 'auth_time': self.now}
        return self.issuer.issue('human-key', claims)

    def propose(self, case='case-a', **kwargs):
        before = self.store.get(case, guard=self.clock)['campaigns']
        snapshot = self.service.propose(self.token('owner'), case, **kwargs)
        added = set(snapshot['campaigns']) - set(before)
        if len(added) != 1:
            raise RuntimeError('Expected one new immutable campaign')
        return added.pop(), snapshot

    def delegate(self, campaign, case='case-c', *, expires_at=1100):
        before = self.store.get(case, guard=self.clock)['delegations']
        snapshot = self.service.delegate(self.token('policy'), case, campaign,
            action='policy', delegate_person_id='person-delegatepolicy', expires_at=expires_at)
        return (set(snapshot['delegations']) - set(before)).pop()

    def update(self, **changes):
        self.authority = replace(self.authority, revision=self.authority.revision + 1, **changes)
        self.identity._replace_authority_for_fixture(self.authority)


def exercise(output):
    fixture = ReviewFixture(output)
    service = fixture.service
    checks = []
    def check(name, condition):
        checks.append({'name': name, 'passed': bool(condition)})
        if not condition:
            raise RuntimeError('Policy review rehearsal failed: ' + name)
    def denied(action):
        try:
            action()
        except (PermissionDenied, IdentityUnavailable, ReviewError, StoreUnavailable, FileExistsError):
            return True
        return False

    campaign_id, proposed = fixture.propose()
    destination = fixture.root / 'training'
    check('policy_required_before_any_fit', denied(lambda: service.execute(
        fixture.token('operator'), 'case-a', campaign_id, output=destination))
        and not destination.exists()
        and fixture.store.get('case-a', guard=fixture.clock)['campaigns'][campaign_id]['state'] == 'proposed')
    approved = service.approve_policy(fixture.token('policy'), 'case-a', campaign_id)
    check('policy_approved_before_registration_and_fit',
        approved['campaigns'][campaign_id]['state'] == 'approved' and not destination.exists()
        and approved['campaigns'][campaign_id]['policy_approval'] is not None)
    completed = service.execute(fixture.token('operator'), 'case-a', campaign_id, output=destination)
    campaign = completed['campaigns'][campaign_id]
    completion = campaign['completion']['payload']
    check('actual_native_training_and_authenticated_replay', campaign['state'] == 'completed'
        and campaign['start'] is not None and (destination / 'native/candidate.json').is_file()
        and (destination / 'replay-envelope.json').is_file()
        and completion['registration_id'] != campaign_id)
    check('owner_and_alias_cannot_assess', all(denied(lambda subject=subject: service.assess(
        fixture.token(subject), 'case-a', campaign_id)) for subject in ('owner', 'owner-alias')))
    service.assess(fixture.token('assessor'), 'case-a', campaign_id)
    check('operator_cannot_approve', denied(lambda: service.approve(fixture.token('operator'), 'case-a', campaign_id)))
    final = service.approve(fixture.token('releaser'), 'case-a', campaign_id)
    check('independent_current_reviews_are_usable', service.status(fixture.token('auditor'), 'case-a', campaign_id)['reviews_usable'])

    admission_path = destination / 'replay-admission.json'
    admission_bytes = admission_path.read_bytes()
    try:
        admission_path.write_bytes(admission_bytes + b' ')
        changed_unusable = not service.status(fixture.token('auditor'), 'case-a', campaign_id)['reviews_usable']
    finally:
        admission_path.write_bytes(admission_bytes)
    check('retained_evidence_tamper_invalidates_reviews', changed_unusable
        and service.status(fixture.token('auditor'), 'case-a', campaign_id)['reviews_usable'])
    check('post_result_policy_weakening_refused', denied(lambda: fixture.propose(max_membership_auc_bps=10000)))
    # A new recipient needs a new campaign and new run. Replacing this existing
    # campaign's immutable policy is refused even with a current owner context.
    with fixture.identity._lock:
        owner = service.authorization.access(fixture.token('owner'), 'case-a', 'propose')
        changed_policy = {**campaign['policy'], 'recipient_id': 'different-recipient'}
        replacement_denied = denied(lambda: fixture.store.apply('case-a', 'propose',
            changed_policy, owner.actor, guard=owner.recheck))
    check('recipient_change_refused', replacement_denied
        and fixture.store.get('case-a', guard=fixture.clock)['campaigns'][campaign_id]['policy'] == campaign['policy'])

    second, _ = fixture.propose('case-b')
    service.approve_policy(fixture.token('policy'), 'case-b', second)
    saved = (destination / 'replay-envelope.json').read_bytes()
    check('old_campaign_evidence_cannot_be_rebound', denied(lambda: service.execute(
        fixture.token('operator'), 'case-b', second, output=destination))
        and denied(lambda: service.assess(fixture.token('assessor'), 'case-b', second))
        and (destination / 'replay-envelope.json').read_bytes() == saved)

    third, _ = fixture.propose('case-c')
    delegation = fixture.delegate(third, expires_at=1001)
    check('delegation_is_campaign_scoped', denied(lambda: service.approve_policy(
        fixture.token('delegatepolicy'), 'case-a', campaign_id, delegation_id=delegation)))
    fixture.now = 1001
    expired = denied(lambda: service.approve_policy(fixture.token('delegatepolicy'), 'case-c', third, delegation_id=delegation))
    revoked = fixture.delegate(third)
    service.revoke(fixture.token('policy'), 'case-c', revoked)
    check('expired_or_revoked_delegation_denied', expired and denied(lambda: service.approve_policy(
        fixture.token('delegatepolicy'), 'case-c', third, delegation_id=revoked)))

    restarted = FixtureReviewService(fixture.identity, ReviewStore.open(fixture.store.root, fixture.store.store_id), fixture.workflow)
    historical = restarted.status(fixture.token('auditor'), 'case-a', campaign_id)
    check('restart_preserves_history_without_current_authority', not historical['reviews_usable']
        and historical['campaign'] == final['campaigns'][campaign_id])
    principals = dict(fixture.authority.principals)
    principals[(ISSUER, 'assessor')] = replace(principals[(ISSUER, 'assessor')], enabled=False)
    fixture.update(principals=principals)
    status = service.status(fixture.token('auditor'), 'case-a', campaign_id)
    check('current_revocation_invalidates_reviews', not status['reviews_usable'])
    check('all_results_remain_non_authorizing', all(status[key] is value for key, value in FLAGS.items())
        and all(campaign['policy'][key] is value for key, value in FLAGS.items()))
    return {'schema': 'mra-fixture-policy-review-exercise/v1', 'status': 'passed', 'checks': checks,
        'summary': {'fresh_native_runs': 1, 'profile_id': 'sklearn-wine', 'max_rows': 128,
            'utility_floor_bps': 0, 'max_membership_auc_bps': 9900,
            'utility_improvement_bps': completion['utility_improvement_bps'],
            'membership_auc_bps': completion['membership_auc_bps'],
            'historical_campaigns': 3, 'current_reviews_usable_after_revocation': False},
        'evidence': {'campaign_id': campaign_id, 'policy_sha256': campaign['policy_sha256'],
            'binding_sha256': campaign['binding_sha256'], 'completion': completion,
            'policy_approval_sha256': campaign['policy_approval']['sha256'],
            'assessment_sha256': final['campaigns'][campaign_id]['assessment']['sha256'],
            'approval_sha256': final['campaigns'][campaign_id]['approval']['sha256'],
            'review_store_id': fixture.store.store_id}, **FLAGS}
