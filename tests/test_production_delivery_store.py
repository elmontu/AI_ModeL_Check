"""Adversarial metadata-only store and sealed public-fixture chunk admissions."""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from model_release_assurance.production_delivery.contracts import DeliveryError, canonical_bytes
from model_release_assurance.production_delivery.store import DeliveryStore, StoreError, StoreConflict, StoreUnavailable
from test_production_delivery_contracts import candidate_fixture, activation_fixture, grant_fixture, chunk_fixture, actor_fixture


class DeliveryStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.now=1000
        self.cases=[{"agency_id":"agency","project_id":"project","case_id":name,"submitter_person_id":"owner"}
                    for name in ("case-a","case-b")]
        self.store=DeliveryStore.create(self.root/'delivery',cases=self.cases,guard=self.guard)
        self.pin=self.store.initial_pin
        self.owner=object()
        self.capability=self.store._bind_gateway(self.owner)
        self.raw=candidate_fixture()
        self.activation=activation_fixture(self.raw)
        self.recipient=actor_fixture()
        self.manager=actor_fixture('releaser','f')

    def guard(self):
        return self.now

    def get(self,case='case-a'):
        return self.store.get(case,expected_pin=self.pin,guard=self.guard)

    def apply(self,operation,payload,*,actor=None,case='case-a'):
        current=self.get(case)
        result=self.store.apply(case,operation,payload,actor or self.manager,expected_pin=self.pin,
                               expected_head_sha256=current['head_sha256'],guard=self.guard)
        self.pin=result['pin']
        return result

    def activate(self,activation=None,raw=None):
        activation=activation or self.activation
        current=self.get(activation['case_id'])
        result=self.store._activate(activation['case_id'],activation,self.manager,artifact_bytes=self.raw if raw is None else raw,
            capability=self.capability,expected_pin=self.pin,expected_head_sha256=current['head_sha256'],guard=self.guard)
        self.pin=result['pin']
        return result

    def ready(self,grant=None):
        self.activate()
        return self.apply('grant',grant or grant_fixture(self.activation))

    def take(self,payload=None,*,actor=None,case='case-a',capability=None):
        current=self.get(case)
        result=self.store._take_chunk(case,payload or chunk_fixture(),actor or self.recipient,
            capability=self.capability if capability is None else capability,expected_pin=self.pin,
            expected_head_sha256=current['head_sha256'],guard=self.guard)
        self.pin=result['pin']
        return result

    def manage(self,operation):
        return self.apply(operation,{'activation_id':self.activation['activation_id'],'reason':'operator_request'})

    def observation(self,**changes):
        value={'request_id':'6'*32,'bytes_written':32,'status':'returned','write_extent_known':True,'recipient_receipt_verified':False}
        value.update(changes)
        return value

    def test_metadata_only_reads_and_exact_sealed_bytes(self):
        self.ready()
        result=self.take()
        self.assertEqual(result['bytes'],self.raw[:32])
        self.assertEqual(result['admission']['chunk_sha256'],hashlib.sha256(self.raw[:32]).hexdigest())
        metadata=self.get()
        self.assertNotIn('bytes',metadata)
        self.assertNotIn(self.raw, [value for value in metadata.values() if isinstance(value,bytes)])
        self.assertNotIn('public_fixture_bytes_delivered',metadata)
        self.assertFalse(metadata['recipient_receipt_verified'])
        self.assertFalse(metadata['model_delivery'])
        self.assertEqual(metadata['grants']['4'*32]['attempted_bytes'],32)
        self.assertEqual(metadata['observations'],{})
        self.assertEqual(canonical_bytes(metadata),canonical_bytes(self.store.get('case-a',expected_pin=self.pin,guard=self.guard)))

    def test_public_api_and_wrong_capability_cannot_activate_or_take_bytes(self):
        before=self.get()
        for operation,payload in (('activate',self.activation),('admit',chunk_fixture()),('read',{})):
            with self.assertRaises(StoreError):
                self.store.apply('case-a',operation,payload,self.manager,expected_pin=self.pin,
                                 expected_head_sha256=before['head_sha256'],guard=self.guard)
        with self.assertRaises(StoreConflict):
            self.store._activate('case-a',self.activation,self.manager,artifact_bytes=self.raw,capability=object(),
                expected_pin=self.pin,expected_head_sha256=before['head_sha256'],guard=self.guard)
        self.ready()
        with self.assertRaises(StoreConflict):
            self.take(capability=object())
        self.assertEqual(self.get()['admissions'],{})

    def test_replaced_gateway_seal_fails_again_at_final_guard(self):
        self.ready()
        before=self.get()
        calls=[0]
        def guard():
            calls[0]+=1
            if calls[0]==2:
                self.store._bind_gateway(object())
            return self.now
        with self.assertRaises(StoreConflict):
            self.store._take_chunk('case-a',chunk_fixture(),self.recipient,capability=self.capability,
                expected_pin=self.pin,expected_head_sha256=before['head_sha256'],guard=guard)
        self.assertEqual(self.get()['admissions'],{})

    def test_activation_scope_hash_size_and_format_are_bound(self):
        for activation,raw in ((activation_fixture(case_id='case-b'),self.raw),
            (self.activation,self.raw+b' '),(activation_fixture(artifact_size=len(self.raw)-1),self.raw)):
            with self.subTest(activation=activation['case_id']):
                if activation['case_id']=='case-b':
                    current=self.get()
                    with self.assertRaises(StoreConflict):
                        self.store._activate('case-a',activation,self.manager,artifact_bytes=raw,capability=self.capability,
                            expected_pin=self.pin,expected_head_sha256=current['head_sha256'],guard=self.guard)
                else:
                    with self.assertRaises(DeliveryError):
                        self.activate(activation,raw)
        self.assertEqual(self.get()['activations'],{})

    def test_exact_recipient_person_credential_case_and_transfer_required(self):
        self.ready()
        for actor in (actor_fixture('someone'),actor_fixture(credential='a')):
            with self.assertRaises(StoreConflict):
                self.take(actor=actor)
        for payload in (chunk_fixture(transfer_id='9'*32),chunk_fixture(activation_id='9'*32)):
            with self.assertRaises(StoreConflict):
                self.take(payload)
        with self.assertRaises(StoreConflict):
            self.take(case='case-b')
        self.assertEqual(self.get()['admissions'],{})

    def test_grant_limits_expiry_and_exact_recipient_scope(self):
        self.activate()
        for changes in ({'expires_at':1061},{'expires_at':1000},{'recipient_id':'other'},
                        {'max_attempted_bytes':3*len(self.raw)+1}):
            with self.subTest(changes=changes),self.assertRaises(StoreConflict):
                self.apply('grant',grant_fixture(self.activation,**changes))
        self.apply('grant',grant_fixture(self.activation))
        with self.assertRaises(StoreConflict):
            self.apply('grant',grant_fixture(self.activation,grant_id='9'*32))

    def test_only_next_offset_or_exact_prior_chunk_retry_is_allowed(self):
        self.ready()
        for payload in (chunk_fixture(offset=1),chunk_fixture(offset=len(self.raw)-1,length=32)):
            with self.assertRaises(StoreConflict):
                self.take(payload)
        first=self.take()
        retry=self.take(chunk_fixture(request_id='8'*32,chunk_id='9'*32))
        self.assertEqual(first['bytes'],retry['bytes'])
        with self.assertRaises(StoreConflict):
            self.take(chunk_fixture(request_id='a'*32,chunk_id='b'*32,offset=0,length=16))
        self.take(chunk_fixture(request_id='a'*32,chunk_id='b'*32,offset=32,length=16))
        grant=self.get()['grants']['4'*32]
        self.assertEqual((grant['next_offset'],grant['attempted_bytes'],grant['admission_count']),(48,80,3))

    def test_request_and_chunk_identifiers_are_permanently_one_use(self):
        self.ready()
        self.take()
        for payload in (chunk_fixture(),chunk_fixture(chunk_id='8'*32),chunk_fixture(request_id='8'*32)):
            with self.assertRaises(StoreConflict):
                self.take(payload)
        self.assertEqual(self.get()['grants']['4'*32]['attempted_bytes'],32)

    def test_interruption_and_unknown_write_do_not_refund_or_claim_receipt(self):
        self.ready(grant_fixture(self.activation,max_attempted_bytes=32))
        self.take()
        result=self.apply('observe',self.observation(bytes_written=None,status='failed',write_extent_known=False),actor=self.recipient)
        self.assertIsNone(result['observations']['6'*32]['payload']['bytes_written'])
        self.assertFalse(result['recipient_receipt_verified'])
        self.assertEqual(result['grants']['4'*32]['attempted_bytes'],32)
        with self.assertRaises(StoreConflict):
            self.take(chunk_fixture(request_id='8'*32,chunk_id='9'*32))

    def test_observation_exact_recipient_and_single_immutable_fact(self):
        self.ready()
        self.take()
        with self.assertRaises(StoreConflict):
            self.apply('observe',self.observation(),actor=actor_fixture('other'))
        for changes in ({'bytes_written':33},{'bytes_written':1}):
            with self.assertRaises(StoreConflict):
                self.apply('observe',self.observation(**changes),actor=self.recipient)
        self.apply('observe',self.observation(bytes_written=4,status='interrupted'),actor=self.recipient)
        with self.assertRaises(StoreConflict):
            self.apply('observe',self.observation(),actor=self.recipient)

    def test_observation_after_expiry_and_revocation_is_audit_only(self):
        self.ready()
        self.take()
        self.manage('revoke')
        self.now=1200
        result=self.apply('observe',self.observation(bytes_written=None,status='failed',write_extent_known=False),actor=self.recipient)
        self.assertEqual(result['activations']['1'*32]['state'],'revoked')
        self.assertEqual(result['grants']['4'*32]['attempted_bytes'],32)
        with self.assertRaises(StoreConflict):
            self.take(chunk_fixture(request_id='8'*32,chunk_id='9'*32))

    def test_suspend_resume_and_permanent_revoke_order_admissions(self):
        self.ready()
        self.manage('suspend')
        with self.assertRaises(StoreConflict):
            self.take()
        self.manage('resume')
        self.take()
        self.manage('revoke')
        with self.assertRaises(StoreConflict):
            self.take(chunk_fixture(request_id='8'*32,chunk_id='9'*32))
        for operation in ('resume','revoke','suspend'):
            with self.assertRaises(StoreConflict):
                self.manage(operation)
        with self.assertRaises(StoreConflict):
            self.activate()

    def test_revoked_grant_is_terminal_even_after_activation_resume(self):
        self.ready()
        self.apply('revoke_grant',{'grant_id':'4'*32})
        self.manage('suspend'); self.manage('resume')
        with self.assertRaises(StoreConflict):
            self.take()
        with self.assertRaises(StoreConflict):
            self.apply('grant',grant_fixture(self.activation,transfer_id='8'*32))

    def test_expiry_is_exclusive_and_rechecked_after_full_replay(self):
        self.ready(grant_fixture(self.activation,expires_at=1001))
        before=self.get()
        original=self.store._validate
        calls=[0]
        def validate(connection):
            result=original(connection)
            calls[0]+=1
            if calls[0]==2:
                self.now=1001
            return result
        with patch.object(self.store,'_validate',side_effect=validate):
            with self.assertRaises(StoreConflict):
                self.store._take_chunk('case-a',chunk_fixture(),self.recipient,capability=self.capability,
                    expected_pin=self.pin,expected_head_sha256=before['head_sha256'],guard=self.guard)
        self.assertEqual(self.get()['admissions'],{})
        self.assertEqual(self.get()['grants']['4'*32]['attempted_bytes'],0)

    def test_final_authority_guard_failure_does_not_return_or_commit_buffer(self):
        self.ready()
        before=self.get()
        calls=[0]
        def guard():
            calls[0]+=1
            if calls[0]==2:
                raise PermissionError('revoked')
            return self.now
        with self.assertRaises(PermissionError):
            self.store._take_chunk('case-a',chunk_fixture(),self.recipient,capability=self.capability,
                expected_pin=self.pin,expected_head_sha256=before['head_sha256'],guard=guard)
        self.assertEqual(self.get()['admissions'],{})

    def test_stale_head_before_revocation_cannot_admit_after_revocation(self):
        self.ready()
        before=self.get()
        self.manage('revoke')
        with self.assertRaises(StoreConflict):
            self.store._take_chunk('case-a',chunk_fixture(),self.recipient,capability=self.capability,
                expected_pin=before['pin'],expected_head_sha256=before['head_sha256'],guard=self.guard)
        self.assertEqual(self.get()['admissions'],{})

    def test_external_floor_detects_backup_restore_fork_and_wrong_store(self):
        self.ready()
        backup=self.root/'backup'
        shutil.copytree(self.store.root,backup)
        oldpin=self.pin
        self.manage('revoke')
        with self.assertRaises(StoreConflict):
            DeliveryStore.open(backup,expected_pin=self.pin)
        fork=DeliveryStore.open(backup,expected_pin=oldpin)
        current=fork.get('case-a',expected_pin=oldpin,guard=self.guard)
        branch=fork.apply('case-a','suspend',{'activation_id':'1'*32,'reason':'operator_request'},self.manager,
                         expected_pin=oldpin,expected_head_sha256=current['head_sha256'],guard=self.guard)
        with self.assertRaises(StoreConflict):
            self.store.get('case-a',expected_pin=branch['pin'],guard=self.guard)
        with self.assertRaises(StoreUnavailable):
            DeliveryStore.open(self.store.root,expected_pin={**self.pin,'store_id':'f'*32})
        self.assertEqual(self.store.get('case-a',expected_pin=oldpin,guard=self.guard)['pin'],self.pin)

    def test_reopen_requires_external_pin_and_never_bootstraps_new_floor(self):
        self.ready(); self.take()
        reopened=DeliveryStore.open(self.store.root,expected_pin=self.pin)
        with self.assertRaises(StoreError):
            _=reopened.initial_pin
        self.assertEqual(reopened.get('case-a',expected_pin=self.pin,guard=self.guard)['admissions'],self.get()['admissions'])
        cap=reopened._bind_gateway(object())
        before=reopened.get('case-a',expected_pin=self.pin,guard=self.guard)
        with self.assertRaises(StoreConflict):
            reopened._take_chunk('case-a',chunk_fixture(),self.recipient,capability=cap,
                expected_pin=self.pin,expected_head_sha256=before['head_sha256'],guard=self.guard)

    def test_corrupt_blob_missing_event_or_schema_fails_closed(self):
        self.ready()
        for name,sql,values in (
            ('blob','UPDATE artifacts SET content=?',(self.raw[:-1]+b'x',)),
            ('missing','DELETE FROM events WHERE sequence=2',()),
            ('schema','PRAGMA user_version=99',()),
            ('extra','CREATE TABLE unexpected (x INTEGER)',())):
            path=self.root/name
            shutil.copytree(self.store.root,path)
            with closing(sqlite3.connect(path/'delivery.sqlite')) as connection:
                connection.execute(sql,values); connection.commit()
            with self.subTest(name=name),self.assertRaises(StoreUnavailable):
                DeliveryStore.open(path,expected_pin=self.pin)

    def test_unknown_unbound_artifact_is_not_accepted(self):
        with closing(sqlite3.connect(self.store.root/'delivery.sqlite')) as connection:
            connection.execute('INSERT INTO artifacts VALUES (?,?)',('f'*32,self.raw)); connection.commit()
        with self.assertRaises(StoreUnavailable):
            self.get()

    def test_clock_bool_rollback_and_invalid_guard_fail(self):
        for now in (999,True,1000.0):
            with self.assertRaises(StoreUnavailable):
                self.store.get('case-a',expected_pin=self.pin,guard=lambda:now)

    def test_existing_root_missing_open_hardlink_and_traversal(self):
        with self.assertRaises(StoreUnavailable):
            DeliveryStore.create(self.store.root,cases=self.cases,guard=self.guard)
        with self.assertRaises(StoreUnavailable):
            DeliveryStore.open(self.root/'missing',expected_pin=self.pin)
        self.assertFalse((self.root/'missing').exists())
        alias=self.root/'alias'
        os.link(self.store.root/'delivery.sqlite',alias)
        with self.assertRaises(StoreUnavailable):
            self.get()
        alias.unlink()
        with self.assertRaises(StoreUnavailable):
            DeliveryStore.open(self.store.root/'..'/'delivery',expected_pin=self.pin)

    def _child(self,operation,payload,actor,*,head,mode='normal'):
        parameters=json.dumps({'root':str(self.store.root),'pin':self.pin,'head':head,'operation':operation,
                               'payload':payload,'actor':actor,'mode':mode})
        script="""
import json,os,sys
from model_release_assurance.production_delivery.store import DeliveryStore,StoreConflict
p=json.loads(sys.argv[1]); store=DeliveryStore.open(p['root'],expected_pin=p['pin'])
cap=store._bind_gateway(object())
if p['mode']=='before_commit':
    original=store._append
    def crash(*args,**kwargs):
        original(*args,**kwargs)
        os._exit(73)
    store._append=crash
try:
    common=dict(expected_pin=p['pin'],expected_head_sha256=p['head'],guard=lambda:1000)
    if p['operation']=='admit':
        result=store._take_chunk('case-a',p['payload'],p['actor'],capability=cap,**common)
    else:
        result=store.apply('case-a',p['operation'],p['payload'],p['actor'],**common)
except StoreConflict:
    print('conflict',flush=True)
else:
    if p['mode']=='after_commit':
        os._exit(74)
    print(json.dumps({'pin':result['pin'],'admitted':p['operation']=='admit'}),flush=True)
"""
        return subprocess.Popen([sys.executable,'-B','-c',script,parameters],cwd=Path(__file__).resolve().parents[1],
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)

    def test_process_crash_before_admission_rolls_back_after_commit_retains_attempt(self):
        self.ready()
        head=self.get()['head_sha256']
        for mode,code,attempted in (('before_commit',73,0),('after_commit',74,32)):
            child=self._child('admit',chunk_fixture(),self.recipient,head=head,mode=mode)
            stdout,stderr=child.communicate(timeout=20)
            self.assertEqual(child.returncode,code,stdout+stderr)
            reopened=DeliveryStore.open(self.store.root,expected_pin=self.pin)
            current=reopened.get('case-a',expected_pin=self.pin,guard=self.guard)
            self.assertEqual(current['grants']['4'*32]['attempted_bytes'],attempted)
            self.assertEqual(len(current['admissions']),int(attempted>0))
            self.assertEqual(current['observations'],{})
            self.assertFalse(current['recipient_receipt_verified'])
        with self.assertRaises(StoreConflict):
            self.take()
        self.assertEqual(self.take(chunk_fixture(request_id='8'*32,chunk_id='9'*32))['bytes'],self.raw[:32])

    def test_independent_process_admit_vs_revoke_has_one_linearized_winner(self):
        self.ready()
        head=self.get()['head_sha256']
        children=[self._child('admit',chunk_fixture(),self.recipient,head=head),
                  self._child('revoke',{'activation_id':'1'*32,'reason':'operator_request'},self.manager,head=head)]
        outputs=[]
        for child in children:
            stdout,stderr=child.communicate(timeout=20)
            self.assertEqual(child.returncode,0,stderr)
            outputs.append(stdout.strip())
        self.assertEqual(outputs.count('conflict'),1)
        current=self.get()
        if current['activations']['1'*32]['state']=='active':
            self.assertEqual(len(current['admissions']),1)
            self.manage('revoke')
        else:
            self.assertEqual(current['admissions'],{})
        with self.assertRaises(StoreConflict):
            self.take(chunk_fixture(request_id='8'*32,chunk_id='9'*32))

    def test_independent_process_same_admission_id_race_consumes_once(self):
        self.ready()
        head=self.get()['head_sha256']
        children=[self._child('admit',chunk_fixture(),self.recipient,head=head) for _ in range(2)]
        outputs=[]
        for child in children:
            stdout,stderr=child.communicate(timeout=20)
            self.assertEqual(child.returncode,0,stderr)
            outputs.append(stdout.strip())
        self.assertEqual(outputs.count('conflict'),1)
        current=self.get()
        self.assertEqual(len(current['admissions']),1)
        self.assertEqual(current['grants']['4'*32]['attempted_bytes'],32)

    def test_process_revoke_committed_before_response_is_not_lost(self):
        self.ready()
        head=self.get()['head_sha256']
        child=self._child('revoke',{'activation_id':'1'*32,'reason':'operator_request'},self.manager,
                          head=head,mode='after_commit')
        stdout,stderr=child.communicate(timeout=20)
        self.assertEqual(child.returncode,74,stdout+stderr)
        current=self.get()
        self.assertEqual(current['activations']['1'*32]['state'],'revoked')
        with self.assertRaises(StoreConflict):
            self.take()

    def test_transfer_admission_capacity_fails_without_reset_or_refund(self):
        self.ready(grant_fixture(self.activation,max_attempted_bytes=3*len(self.raw)))
        with patch('model_release_assurance.production_delivery.store.MAX_TRANSFER_ADMISSIONS',2):
            self.take()
            self.take(chunk_fixture(request_id='8'*32,chunk_id='9'*32))
            with self.assertRaises(StoreConflict):
                self.take(chunk_fixture(request_id='a'*32,chunk_id='b'*32))
            self.assertEqual(self.get()['grants']['4'*32]['attempted_bytes'],64)

    def test_same_bytes_database_replacement_denied_by_existing_handle(self):
        replacement=self.root/'replacement.sqlite'
        shutil.copyfile(self.store.root/'delivery.sqlite',replacement)
        os.replace(replacement,self.store.root/'delivery.sqlite')
        with self.assertRaises(StoreUnavailable):
            self.get()
        # An explicit reopen still needs the independently retained floor.
        reopened=DeliveryStore.open(self.store.root,expected_pin=self.pin)
        self.assertEqual(reopened.get('case-a',expected_pin=self.pin,guard=self.guard)['pin'],self.pin)


if __name__=='__main__':
    unittest.main()
