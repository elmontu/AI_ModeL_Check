"""Fresh public training and bounded local gateway transfer exercises.

The fixed bootstrap is trusted Python, not an enrollment or artifact-import API.
Tokens and generated private keys stay in memory. No private data is accepted.
"""
from __future__ import annotations

from dataclasses import asdict
import hashlib
from pathlib import Path
import uuid

from ..production_identity.policy import PrincipalAuthority, CaseGrant, PermissionDenied, IdentityUnavailable
from ..production_review.rehearsal import ReviewFixture, SCOPES, ISSUER
from ..production_review.contracts import ReviewError
from .authorization import RecipientRecord
from .review_bridge import DeliveryReviewBridge
from .checkpoint import FileCheckpointSink
from .contracts import FLAGS, DeliveryError, MAX_CHUNK_BYTES
from .gateway import FixtureDeliveryGateway
from .store import DeliveryStore, StoreConflict, StoreUnavailable

DELIVERY_SCOPES = frozenset('delivery:' + action for action in
    ('activate', 'grant', 'receive', 'read', 'suspend', 'resume', 'revoke'))


class DeliveryFixture:
    """Explicit local fixture authority; enrollment finishes before any fit."""
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(exist_ok=True)
        self.review_fixture = ReviewFixture(self.root / 'review')
        foundation = self.review_fixture
        principals = dict(foundation.authority.principals)
        principals[(ISSUER, 'recipient')] = PrincipalAuthority(ISSUER, 'recipient',
            'person-recipient', 'human', client_ids=frozenset({'client'}))
        recipient_grants = tuple(CaseGrant('person-recipient', case.agency_id, case.project_id,
            case.case_id, frozenset({'auditor'})) for case in foundation.cases)
        foundation.update(principals=principals, grants=foundation.authority.grants + recipient_grants)
        self.review = foundation.service
        self.identity, self.trust = foundation.identity, foundation.trust
        self.bridge = DeliveryReviewBridge(self.review)
        self.store = DeliveryStore.create(self.root / 'delivery',
            cases=[asdict(case) for case in foundation.cases], guard=foundation.clock)
        self.checkpoint_sink = FileCheckpointSink(self.root / 'checkpoints', self.store.initial_pin)
        recipients = (RecipientRecord('fixture-recipient', 'agency', 'project', 'case-a',
                                      frozenset({'person-recipient'})),)
        self.gateway = FixtureDeliveryGateway(self.bridge, self.store, recipients,
            expected_pin=self.store.initial_pin, checkpoint_sink=self.checkpoint_sink)
        self.output = self.root / 'training'
        self.campaign_id = None

    @property
    def now(self):
        return self.review_fixture.now

    @now.setter
    def now(self, value):
        self.review_fixture.now = value

    def token(self, subject, **kwargs):
        kwargs.setdefault('scopes', SCOPES | DELIVERY_SCOPES)
        return self.review_fixture.token(subject, **kwargs)

    def prepare(self):
        campaign_id, _ = self.review_fixture.propose()
        self.review.approve_policy(self.token('policy'), 'case-a', campaign_id)
        self.bridge.execute(self.token('operator'), 'case-a', campaign_id, output=self.output)
        self.activation_blocked_before_reviews = False
        try:
            self.gateway.activate(self.token('releaser'), 'case-a', campaign_id,
                                  profile='local_public_fixture')
        except (PermissionDenied, IdentityUnavailable, ReviewError, DeliveryError, StoreConflict, StoreUnavailable):
            self.activation_blocked_before_reviews = True
        if not self.activation_blocked_before_reviews:
            raise RuntimeError('Activation preceded required independent acknowledgments')
        self.review.assess(self.token('assessor'), 'case-a', campaign_id)
        snapshot = self.review.approve(self.token('releaser'), 'case-a', campaign_id)
        self.campaign_id = campaign_id
        return campaign_id, snapshot

    def activate(self):
        before = self.gateway.status(self.token('auditor'), 'case-a')['activations']
        snapshot = self.gateway.activate(self.token('releaser'), 'case-a', self.campaign_id,
                                          ttl_seconds=30, profile='local_public_fixture')
        added = set(snapshot['activations']) - set(before)
        if len(added) != 1:
            raise RuntimeError('Expected one fresh activation')
        activation_id = added.pop()
        return activation_id, snapshot['activations'][activation_id]

    def grant(self, activation_id, recipient_token):
        before = self.gateway.status(self.token('auditor'), 'case-a')['grants']
        snapshot = self.gateway.grant(self.token('releaser'), 'case-a', activation_id,
                                      recipient_token, ttl_seconds=20)
        added = set(snapshot['grants']) - set(before)
        if len(added) != 1:
            raise RuntimeError('Expected one fresh transfer grant')
        grant_id = added.pop()
        return grant_id, snapshot['grants'][grant_id]


def exercise(output):
    """Exercise one real reviewed public model; never authorize production."""
    fixture = DeliveryFixture(output)
    gateway, review = fixture.gateway, fixture.review
    checks = []
    def check(name, condition):
        checks.append({'name': name, 'passed': bool(condition)})
        if not condition:
            raise RuntimeError('Controlled delivery rehearsal failed: ' + name)
    def denied(action, *, type_error=False):
        try:
            action()
        except (PermissionDenied, IdentityUnavailable, ReviewError, DeliveryError, StoreConflict, StoreUnavailable):
            return True
        except TypeError:
            if type_error:
                return True
            raise
        return False

    # Default and production selections are refused before candidate creation.
    check('production_profile_is_refused', denied(lambda: gateway.activate(
        fixture.token('releaser'), 'case-a', uuid.uuid4().hex)) and not fixture.output.exists())
    campaign_id, reviewed = fixture.prepare()
    campaign = reviewed['campaigns'][campaign_id]
    check('fresh_training_and_independent_review', campaign['state'] == 'completed'
        and campaign['assessment'] is not None and campaign['approval'] is not None
        and review.status(fixture.token('auditor'), 'case-a', campaign_id)['reviews_usable'])
    check('activation_requires_current_independent_review', fixture.activation_blocked_before_reviews)
    check('activation_requires_explicit_local_profile', denied(lambda: gateway.activate(
        fixture.token('releaser'), 'case-a', campaign_id, profile='agency_private_cloud')))
    activation_id, activation = fixture.activate()
    recipient = fixture.token('recipient')
    check('recipient_scope_is_exact', denied(lambda: gateway.grant(fixture.token('releaser'),
        'case-a', activation_id, fixture.token('auditor'), ttl_seconds=20)))
    candidate = (fixture.output / 'native/candidate.json').read_bytes()
    if hashlib.sha256(candidate).hexdigest() != activation['payload']['artifact_sha256']:
        raise RuntimeError('Activated candidate differs from actual fresh output')
    grant_id, grant = fixture.grant(activation_id, recipient)
    transfer_id = grant['payload']['transfer_id']
    receipts, collected = [], []
    def writer(raw):
        collected.append(raw)
        return len(raw)
    offset = 0
    while offset < len(candidate):
        length = min(128 if offset == 0 else MAX_CHUNK_BYTES, len(candidate) - offset)
        receipt = gateway.deliver_chunk(recipient, 'case-a', activation_id, grant_id,
            transfer_id, offset, length, writer=writer)
        receipts.append(receipt)
        offset += length
    request_ids = [receipt['admission']['request_id'] for receipt in receipts]
    check('exact_candidate_chunks_and_fresh_admissions', b''.join(collected) == candidate
        and len(receipts) >= 2 and len(set(request_ids)) == len(receipts)
        and all(receipt['bytes_written'] == receipt['admission']['length'] for receipt in receipts))

    partial_id, partial_grant = fixture.grant(activation_id, recipient)
    partial = gateway.deliver_chunk(recipient, 'case-a', activation_id, partial_id,
        partial_grant['payload']['transfer_id'], 0, 128, writer=lambda raw: 1)
    state = gateway.status(fixture.token('auditor'), 'case-a')
    check('interrupted_transfer_retains_admission', partial['status'] == 'interrupted'
        and partial['bytes_written'] == 1
        and partial['admission']['request_id'] in state['admissions']
        and state['grants'][partial_id]['attempted_bytes'] == 128)
    check('recipient_receipt_is_not_claimed', all(receipt['recipient_receipt_verified'] is False
        for receipt in [*receipts, partial]))

    live_id, live_grant = fixture.grant(activation_id, recipient)
    live_transfer = live_grant['payload']['transfer_id']
    gateway.deliver_chunk(recipient, 'case-a', activation_id, live_id, live_transfer, 0, 128, writer=lambda raw: len(raw))
    gateway.suspend(fixture.token('releaser'), 'case-a', activation_id)
    check('suspension_blocks_next_chunk', denied(lambda: gateway.deliver_chunk(recipient,
        'case-a', activation_id, live_id, live_transfer, 128, 128, writer=lambda raw: len(raw))))
    gateway.resume(fixture.token('releaser'), 'case-a', activation_id)
    resumed = gateway.deliver_chunk(recipient, 'case-a', activation_id, live_id,
        live_transfer, 128, 128, writer=lambda raw: len(raw))
    check('resume_requires_fresh_admission', resumed['bytes_written'] == 128
        and resumed['admission']['request_id'] not in request_ids)
    gateway.revoke_grant(fixture.token('releaser'), 'case-a', live_id)
    check('grant_revocation_blocks_next_chunk', denied(lambda: gateway.deliver_chunk(recipient,
        'case-a', activation_id, live_id, live_transfer, 256, 128, writer=lambda raw: len(raw))))

    from fastapi.testclient import TestClient
    from .api import create_fixture_app
    with TestClient(create_fixture_app(gateway, profile='local_public_fixture')) as client:
        direct = client.get('/v1/objects/' + activation['payload']['artifact_sha256'],
                            headers={'Authorization': 'Bearer ' + recipient})
    check('caller_artifact_and_direct_object_routes_are_refused', direct.status_code == 404
        and denied(lambda: gateway.activate(fixture.token('releaser'), 'case-a', campaign_id,
            profile='local_public_fixture', artifact_path=fixture.output / 'native/candidate.json'), type_error=True))

    current_activation, _ = fixture.activate()
    current_grant, current_record = fixture.grant(current_activation, recipient)
    current_transfer = current_record['payload']['transfer_id']

    # Restore only a generated copy. The live database and its final history are
    # retained; the independent newer checkpoint must reject the older copy.
    rollback = fixture.root / 'rollback-probe'
    rollback.mkdir()
    backup = (fixture.store.root / 'delivery.sqlite').read_bytes()
    (rollback / 'delivery.sqlite').write_bytes(backup)
    gateway.revoke(fixture.token('releaser'), 'case-a', activation_id)
    latest_pin = gateway.required_pin
    check('activation_revocation_is_permanent', denied(lambda: gateway.resume(
        fixture.token('releaser'), 'case-a', activation_id)))
    check('external_checkpoint_detects_restored_delivery_log', fixture.checkpoint_sink.read() == latest_pin
        and denied(lambda: DeliveryStore.open(rollback, expected_pin=latest_pin)))

    # This final mutation invalidates retained review contexts too. No authority
    # is reconstructed from durable metadata afterward.
    principals = dict(fixture.review_fixture.authority.principals)
    from dataclasses import replace
    principals[(ISSUER, 'recipient')] = replace(principals[(ISSUER, 'recipient')], enabled=False)
    fixture.review_fixture.update(principals=principals)
    check('current_authority_revocation_blocks_delivery', denied(lambda: gateway.deliver_chunk(
        recipient, 'case-a', current_activation, current_grant, current_transfer, 0, 128, writer=lambda raw: len(raw))))
    check('all_results_remain_production_blocked', all(receipt[key] is value
        for receipt in [*receipts, partial, resumed] for key, value in FLAGS.items()))
    return {'schema': 'mra-fixture-controlled-delivery-exercise/v1', 'status': 'passed',
        'checks': checks, 'summary': {'fresh_native_runs': 1, 'profile_id': 'sklearn-wine',
            'artifact_size': len(candidate), 'completed_transfer_chunks': len(receipts),
            'interrupted_attempted_bytes': 128, 'interrupted_bytes_written': 1,
            'recipient_receipt_verified': False, 'public_fixture_bytes_delivered': True},
        'evidence': {'campaign_id': campaign_id, 'policy_sha256': campaign['policy_sha256'],
            'binding_sha256': campaign['binding_sha256'], 'activation_id': activation_id,
            'authority_revocation_activation_id': current_activation,
            'artifact_sha256': activation['payload']['artifact_sha256'],
            'admissions': [receipt['admission'] for receipt in [*receipts, partial, resumed]],
            'required_pin': latest_pin}, **FLAGS}
