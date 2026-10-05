"""Atomic fixed engineering charges, schema migration and fenced metadata delivery."""
from contextlib import closing
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import sysconfig
import tempfile
import time
import unittest
from unittest import mock
import uuid

from model_release_assurance.production_registry import contracts as c, store as s
from test_production_registry_contracts import request_fixture, context_fixture

_CHILD = r"""import sys,json,time,os
from pathlib import Path
cfg=json.loads(sys.argv[1]);sys.path[:0]=cfg['paths']
from model_release_assurance.production_registry.store import RegistryStore,StoreConflict,StoreUnavailable
registry=RegistryStore.open(cfg['root'],cfg['store_id'],expected_schema_version=cfg['version'])
original=RegistryStore._write_record
def changed(self,connection,table,key,value):
    original(self,connection,table,key,value)
    if ((cfg['operation']=='crash_partial_commit' and table=='cases') or
        (cfg['operation']=='crash_migration' and table=='deliveries')): os._exit(23)
RegistryStore._write_record=changed
Path(cfg['ready']).write_text('ready',encoding='ascii')
end=time.monotonic()+15
while not Path(cfg['gate']).exists():
    if time.monotonic()>end:raise SystemExit(24)
    time.sleep(.01)
try:
    if cfg['operation'] in ('crash_migration','crash_after_migration'):
        RegistryStore.migrate(cfg['root'],cfg['store_id'],guard=lambda:1001)
        if cfg['operation']=='crash_after_migration':os._exit(23)
    else:
        result=registry.commit(cfg['request'],cfg['context'],broker=cfg['broker'],guard=lambda:1001)
        if cfg['operation']=='crash_after_commit':os._exit(23)
        print(json.dumps({'ok':True,'result':result}),flush=True)
except (ValueError,StoreUnavailable) as error:
    print(json.dumps({'ok':False,'error':type(error).__name__}),flush=True)
"""


class ProductionRegistryStoreTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory(prefix='registry-store-')
        self.addCleanup(temporary.cleanup)
        self.parent=Path(temporary.name)
        self.root=self.parent/'registry # percent%'
        self.now=1001
        self.accounts=[{'agency_id':'agency','project_id':'project'}, {'agency_id':'other','project_id':'project'}]
        self.store=s.RegistryStore.create(self.root,accounts=self.accounts)
        self.broker=self.store.activate_broker(uuid.uuid4().hex,expected_epoch=0,guard=self.guard)
        self.database=self.root/'registry.sqlite'
        self.owner='a'*64

    def guard(self):return self.now

    def account(self,agency='agency',project='project',store=None,broker=None):
        return (store or self.store).account(agency,project,broker=broker or self.broker,guard=self.guard)

    def case(self,case='case-a',agency='agency',project='project',store=None,broker=None):
        return (store or self.store).case(agency,project,case,broker=broker or self.broker,guard=self.guard)

    def request(self,case='case-a',agency='agency',project='project',store=None,broker=None,**changes):
        store=store or self.store
        account=self.account(agency,project,store,broker)
        current=self.case(case,agency,project,store,broker)
        values=dict(store_id=store.store_id,request_id=uuid.uuid4().hex,agency_id=agency,project_id=project,case_id=case,
                    account_sequence=account['sequence'],account_head=account['head_sha256'],
                    case_sequence=current['sequence'],case_head=current['head_sha256'])
        values.update(changes)
        return request_fixture(**values)

    def context(self,broker=None):
        broker=broker or self.broker
        return context_fixture(broker_id=broker['broker_id'],broker_epoch=broker['epoch'])

    def commit(self,request=None,store=None,broker=None,guard=None):
        store,broker=store or self.store,broker or self.broker
        return store.commit(request or self.request(store=store,broker=broker),self.context(broker),
                            broker=broker,guard=guard or self.guard)

    def claim(self,case='case-a',owner=None,broker=None,store=None,**kwargs):
        return (store or self.store).claim_outbox('agency','project',case,owner_sha256=owner or self.owner,
                    broker=broker or self.broker,guard=kwargs.pop('guard',self.guard),**kwargs)

    def ack(self,lease,owner=None,broker=None,store=None,guard=None):
        return (store or self.store).acknowledge(lease,owner_sha256=owner or self.owner,
                    broker=broker or self.broker,guard=guard or self.guard)

    def query(self,sql,args=(),database=None):
        with closing(sqlite3.connect(database or self.database)) as connection:
            return connection.execute(sql,args).fetchall()

    def change(self,sql,args=()):
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute(sql,args);connection.commit()

    def legacy(self):
        store=s.RegistryStore.create(self.parent/'legacy',accounts=self.accounts,schema_version=1)
        broker=store.activate_broker(uuid.uuid4().hex,expected_epoch=0,guard=self.guard)
        request=self.request(store=store,broker=broker)
        receipt=self.commit(request,store,broker)
        return store,broker,request,receipt

    def processes(self,operations,store=None,broker=None):
        store,broker=store or self.store,broker or self.broker
        gate=self.parent/('gate-'+uuid.uuid4().hex)
        paths=list(dict.fromkeys([str(Path(__file__).resolve().parents[1]/'src'),sysconfig.get_path('purelib'),sysconfig.get_path('platlib')]))
        children,ready_files=[],[]
        try:
            for operation,request in operations:
                ready=self.parent/('ready-'+uuid.uuid4().hex)
                cfg=dict(paths=paths,root=str(store.root),store_id=store.store_id,version=store.schema_version,
                         request=request,context=self.context(broker),broker=broker,operation=operation,ready=str(ready),gate=str(gate))
                child=subprocess.Popen([getattr(sys,'_base_executable',sys.executable),'-I','-S','-B','-c',_CHILD,json.dumps(cfg)],
                    stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',close_fds=True,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
                children.append(child);ready_files.append(ready)
            deadline=time.monotonic()+20
            while not all(path.exists() for path in ready_files):
                if any(child.poll() is not None for child in children) or time.monotonic()>=deadline:
                    self.fail('Fixed registry subprocess did not reach barrier')
                time.sleep(.01)
            gate.write_text('go',encoding='ascii')
            outcomes=[]
            for child,(operation,_) in zip(children,operations):
                output,error=child.communicate(timeout=20)
                if operation.startswith('crash_'):
                    self.assertEqual(child.returncode,23,error);outcomes.append({'crashed':True})
                else:
                    self.assertEqual(child.returncode,0,error);self.assertEqual(error,'');outcomes.append(json.loads(output))
            return outcomes
        finally:
            for child in children:
                if child.poll() is None:child.kill()
                child.communicate(timeout=5)

    def test_explicit_immutable_accounts_and_unknown_scopes(self):
        self.assertEqual(self.account()['capacity_units'],8)
        self.assertEqual(self.account()['remaining_units'],8)
        self.assertEqual(self.case()['sequence'],0)
        self.assertEqual(self.store.inspect(guard=self.guard)['case_count'],0)
        for operation in (lambda:self.account('unknown'),lambda:self.case(agency='unknown'),
            lambda:self.commit(request_fixture(store_id=self.store.store_id,agency_id='unknown'))):
            with self.assertRaises(s.StoreConflict):operation()
        for accounts in ([],self.accounts+[self.accounts[0]], [{'agency_id':'agency'}]):
            with self.assertRaises(ValueError):s.RegistryStore.create(self.parent/uuid.uuid4().hex,accounts=accounts)
        for field in ('root','store_id','schema_version'):
            with self.assertRaises(AttributeError):setattr(self.store,field,'changed')

    def test_head_charge_receipt_outbox_atomic_and_owned(self):
        request=self.request();receipt=self.commit(request)
        c.validate_receipt(receipt,request=request)
        self.assertEqual(self.account()['total_engineering_charge_units'],1)
        self.assertEqual(self.account()['head_sha256'],receipt['receipt_sha256'])
        self.assertEqual(self.case()['head_sha256'],receipt['receipt_sha256'])
        self.assertEqual(self.store.inspect(guard=self.guard)['outbox_pending'],1)
        for table in ('cases','receipts','outbox','deliveries'):
            self.assertEqual(self.query('SELECT count(*) FROM '+table),[(1,)])
        receipt['receipt']['charge_units']=0
        historical=self.store.get_receipt('agency','project',request['request_id'],broker=self.broker,guard=self.guard)
        self.assertEqual(historical['receipt']['charge_units'],1)
        self.assertFalse(historical['receipt']['privacy_accounting_supported'])

    def test_exact_idempotency_survives_credential_and_broker_change(self):
        request=self.request();original=self.commit(request)
        before=self.store.inspect(guard=self.guard)
        self.assertEqual(self.commit(request),original)
        self.assertEqual(self.store.inspect(guard=self.guard)['event_sequence'],before['event_sequence'])
        reopened=s.RegistryStore.open(self.root,self.store.store_id)
        newer=reopened.activate_broker(uuid.uuid4().hex,expected_epoch=self.broker['epoch'],guard=self.guard)
        context={**self.context(newer),'actor_credential_sha256':'e'*64,'authority_revision':2,'trust_revision':3}
        self.assertEqual(reopened.commit(request,context,broker=newer,guard=self.guard),original)
        self.assertEqual(self.account(store=reopened,broker=newer)['total_engineering_charge_units'],1)
        with self.assertRaises(s.StoreConflict):self.commit(request)

    def test_request_ids_permanent_changed_intent_and_stale_heads_fail(self):
        request=self.request();stale=self.request(case='case-b');self.commit(request)
        with self.assertRaises(s.StoreConflict):self.commit(stale)
        changed=self.request(request_id=request['request_id'])
        with self.assertRaises(s.StoreConflict):self.commit(changed)
        self.assertEqual(self.account()['sequence'],1)
        self.assertEqual(self.case('case-b')['sequence'],0)

    def test_one_shared_capacity_across_case_names_and_no_refund(self):
        receipts=[];requests=[]
        for i in range(8):
            request=self.request(case='case-'+str(i));requests.append(request);receipts.append(self.commit(request))
        self.assertEqual(self.account()['remaining_units'],0)
        with self.assertRaises(s.StoreConflict):self.commit(self.request(case='renamed-case'))
        self.assertEqual(self.commit(requests[0]),receipts[0])
        self.assertEqual(self.account('other')['remaining_units'],8)
        for name in ('delete','refund','reset','set_capacity'):
            self.assertFalse(hasattr(self.store,name))

    def test_scoped_owner_leases_ack_idempotency_and_stable_event(self):
        receipt=self.commit();self.assertIsNone(self.claim(case='different-case'))
        claimed=self.claim();lease,event=claimed['lease'],claimed['event']
        self.assertEqual(event['event_id'],receipt['receipt']['event_id'])
        self.assertEqual(event['receipt_sha256'],receipt['receipt_sha256'])
        self.assertEqual(c.validate_outbox_event(event),event)
        self.assertIsNone(self.claim())
        with self.assertRaises(s.StoreConflict):self.ack(lease,owner='b'*64)
        ack=self.ack(lease);self.now=lease['expires_at']+1
        self.assertEqual(self.ack(lease),ack)
        self.assertIsNone(self.claim())
        self.assertEqual(self.store.inspect(guard=self.guard)['outbox_acknowledged'],1)
        self.assertEqual(self.account()['total_engineering_charge_units'],1)

    def test_expired_or_handed_over_lease_reclaimed_without_new_event_identity(self):
        self.commit();first=self.claim(lease_seconds=1);self.now+=1
        second=self.claim(owner='b'*64)
        self.assertEqual(first['event'],second['event'])
        self.assertEqual(second['lease']['generation'],2)
        with self.assertRaises(s.StoreConflict):self.ack(first['lease'])
        newer=self.store.activate_broker(uuid.uuid4().hex,expected_epoch=1,guard=self.guard)
        third=self.claim(owner='c'*64,broker=newer)
        self.assertEqual(third['lease']['generation'],3)
        self.assertEqual(third['event'],first['event'])
        with self.assertRaises(s.StoreConflict):self.ack(second['lease'],owner='b'*64,broker=newer)
        self.ack(third['lease'],owner='c'*64,broker=newer)

    def test_lease_fields_and_broker_tombstones_bound(self):
        self.commit();lease=self.claim()['lease']
        changes={'case_id':'other','account_id':'b'*64,'owner_sha256':'b'*64,'event_id':'b'*32,
                 'lease_id':'b'*32,'generation':2,'claimed_at':1000,'expires_at':lease['expires_at']+1}
        for key,value in changes.items():
            with self.subTest(key=key),self.assertRaises(ValueError):self.ack({**lease,key:value})
        with self.assertRaises(s.StoreConflict):
            self.store.activate_broker(self.broker['broker_id'],expected_epoch=1,guard=self.guard)
        with self.assertRaises(s.StoreConflict):
            self.store.activate_broker(uuid.uuid4().hex,expected_epoch=0,guard=self.guard)
        self.ack(lease)

    def test_v1_explicit_migration_preserves_core_and_fences_old_broker(self):
        old,broker,request,receipt=self.legacy()
        core_before={table:self.query('SELECT * FROM '+table,database=old.root/'registry.sqlite') for table in ('accounts','cases','receipts','outbox')}
        with self.assertRaises(s.StoreUnavailable):s.RegistryStore.open(old.root,old.store_id)
        with self.assertRaises(s.StoreConflict):self.claim(store=old,broker=broker)
        migrated=s.RegistryStore.migrate(old.root,old.store_id,guard=self.guard)
        self.assertEqual(migrated.schema_version,2)
        for table,before in core_before.items():
            self.assertEqual(self.query('SELECT * FROM '+table,database=old.root/'registry.sqlite'),before)
        status=migrated.inspect(guard=self.guard)
        self.assertIsNone(status['broker_id']);self.assertEqual(status['broker_epoch'],2)
        with self.assertRaises(s.StoreUnavailable):old.inspect(guard=self.guard)
        with self.assertRaises(s.StoreConflict):self.account(store=migrated,broker=broker)
        newer=migrated.activate_broker(uuid.uuid4().hex,expected_epoch=2,guard=self.guard)
        self.assertEqual(self.commit(request,migrated,newer),receipt)
        event=self.claim(store=migrated,broker=newer)
        self.assertEqual(event['event']['event_id'],receipt['receipt']['event_id'])
        self.ack(event['lease'],store=migrated,broker=newer)
        with self.assertRaises(s.StoreUnavailable):s.RegistryStore.migrate(old.root,old.store_id,guard=self.guard)

    def test_migration_final_guard_failure_rolls_back_schema_and_history(self):
        old,broker,_,_=self.legacy();before=old.inspect(guard=self.guard)
        calls=[]
        def guard():
            calls.append(1)
            if len(calls)==2:raise PermissionError('migration approval expired')
            return self.now
        with self.assertRaises(PermissionError):s.RegistryStore.migrate(old.root,old.store_id,guard=guard)
        self.assertEqual(old.inspect(guard=self.guard),before)
        database=old.root/'registry.sqlite'
        self.assertEqual(self.query('PRAGMA user_version',database=database),[(1,)])
        self.assertEqual(self.query("SELECT name FROM sqlite_schema WHERE name='deliveries'",database=database),[])
        self.assertEqual(self.account(store=old,broker=broker)['total_engineering_charge_units'],1)

    def test_final_guards_after_replay_and_retention_deadline_are_atomic(self):
        request=self.request();validate=self.store._validate;calls=[]
        def slow(connection,**kwargs):
            state=validate(connection,**kwargs);calls.append(1)
            if len(calls)==2:self.now=1002
            return state
        def guard():
            if self.now>=1002:raise PermissionError('authority expired after replay')
            return self.now
        with mock.patch.object(self.store,'_validate',side_effect=slow):
            with self.assertRaises(PermissionError):self.commit(request,guard=guard)
        self.assertEqual(self.account()['sequence'],0)
        self.now=1002
        with self.assertRaises(s.StoreConflict):self.commit(request,guard=iter([1002,1300]).__next__)
        self.assertEqual(self.account()['sequence'],0)
        self.assertEqual(self.store.inspect(guard=self.guard)['outbox_pending'],0)

    def test_claim_and_ack_final_deadline_fail_without_partial_state(self):
        self.commit()
        with self.assertRaises(s.StoreConflict):self.claim(lease_seconds=1,guard=iter([1001,1002]).__next__)
        claimed=self.claim(lease_seconds=1)
        self.assertEqual(claimed['lease']['generation'],1)
        with self.assertRaises(s.StoreConflict):self.ack(claimed['lease'],guard=iter([1001,1002]).__next__)
        self.assertEqual(self.store.inspect(guard=self.guard)['outbox_pending'],1)
        self.ack(claimed['lease'])

    def test_failed_write_rolls_back_head_charge_receipt_and_outbox(self):
        request=self.request();write=self.store._write_record
        def failure(connection,table,key,value):
            write(connection,table,key,value)
            if table=='cases':raise OSError('fixed test write interruption')
        with mock.patch.object(self.store,'_write_record',side_effect=failure):
            with self.assertRaises(OSError):self.commit(request)
        self.assertEqual(self.account()['total_engineering_charge_units'],0)
        for table in ('cases','receipts','outbox','deliveries'):
            self.assertEqual(self.query('SELECT count(*) FROM '+table),[(0,)])
        self.commit(request)

    def test_two_processes_same_request_have_one_charge_and_same_receipt(self):
        request=self.request();outcomes=self.processes([('commit',request),('commit',request)])
        self.assertTrue(all(row['ok'] for row in outcomes))
        self.assertEqual(outcomes[0]['result'],outcomes[1]['result'])
        self.assertEqual(self.account()['total_engineering_charge_units'],1)
        self.assertEqual(self.store.inspect(guard=self.guard)['outbox_pending'],1)

    def test_two_processes_different_cases_share_one_cas_head(self):
        outcomes=self.processes([('commit',self.request('case-a')),('commit',self.request('case-b'))])
        self.assertEqual(sum(row['ok'] for row in outcomes),1)
        self.assertEqual(self.account()['sequence'],1)
        self.assertEqual(self.store.inspect(guard=self.guard)['case_count'],1)

    def test_two_processes_same_id_changed_payload_have_one_permanent_winner(self):
        first=self.request('case-a')
        second=self.request('case-b',request_id=first['request_id'])
        outcomes=self.processes([('commit',first),('commit',second)])
        self.assertEqual(sum(row['ok'] for row in outcomes),1)
        winner=next(row['result'] for row in outcomes if row['ok'])
        self.assertIn(winner['receipt']['request_sha256'],(c.digest(first),c.digest(second)))
        self.assertEqual(self.account()['total_engineering_charge_units'],1)
        self.assertEqual(self.store.inspect(guard=self.guard)['case_count'],1)
        self.assertEqual(self.store.inspect(guard=self.guard)['outbox_pending'],1)

    def test_process_crash_mid_commit_has_no_partial_charge_or_outbox(self):
        request=self.request();self.processes([('crash_partial_commit',request)])
        reopened=s.RegistryStore.open(self.root,self.store.store_id)
        self.assertEqual(self.account(store=reopened)['total_engineering_charge_units'],0)
        self.assertEqual(reopened.inspect(guard=self.guard)['outbox_pending'],0)
        self.commit(request,store=reopened)

    def test_process_crash_after_commit_retry_never_charges_twice(self):
        request=self.request();self.processes([('crash_after_commit',request)])
        reopened=s.RegistryStore.open(self.root,self.store.store_id)
        before=reopened.get_receipt('agency','project',request['request_id'],broker=self.broker,guard=self.guard)
        self.assertEqual(self.commit(request,store=reopened),before)
        self.assertEqual(self.account(store=reopened)['total_engineering_charge_units'],1)

    def test_process_crash_mid_migration_keeps_complete_v1(self):
        old,broker,_,receipt=self.legacy();before=old.inspect(guard=self.guard)
        self.processes([('crash_migration',None)],store=old,broker=broker)
        reopened=s.RegistryStore.open(old.root,old.store_id,expected_schema_version=1)
        self.assertEqual(reopened.inspect(guard=self.guard),before)
        self.assertEqual(self.account(store=reopened,broker=broker)['head_sha256'],receipt['receipt_sha256'])
        self.assertEqual(self.query("SELECT name FROM sqlite_schema WHERE name='deliveries'",database=old.root/'registry.sqlite'),[])
        s.RegistryStore.migrate(old.root,old.store_id,guard=self.guard)

    def test_process_crash_after_migration_preserves_v2_without_reapplying(self):
        old,broker,request,receipt=self.legacy()
        self.processes([('crash_after_migration',None)],store=old,broker=broker)
        reopened=s.RegistryStore.open(old.root,old.store_id)
        status=reopened.inspect(guard=self.guard)
        self.assertEqual(status['schema_version'],2)
        self.assertEqual(status['broker_epoch'],2)
        self.assertIsNone(status['broker_id'])
        self.assertEqual(status['receipt_count'],1)
        self.assertEqual(status['outbox_pending'],1)
        with self.assertRaises(s.StoreConflict):self.account(store=reopened,broker=broker)
        with self.assertRaises(s.StoreUnavailable):s.RegistryStore.migrate(old.root,old.store_id,guard=self.guard)
        self.assertEqual(reopened.inspect(guard=self.guard),status)
        newer=reopened.activate_broker(uuid.uuid4().hex,expected_epoch=2,guard=self.guard)
        self.assertEqual(self.account(store=reopened,broker=newer)['total_engineering_charge_units'],1)
        self.assertEqual(self.commit(request,reopened,newer),receipt)
        claimed=self.claim(store=reopened,broker=newer)
        self.assertEqual(claimed['event']['event_id'],receipt['receipt']['event_id'])
        self.ack(claimed['lease'],store=reopened,broker=newer)

    def test_bounded_delivery_attempts_do_not_drop_pending_event(self):
        self.commit()
        for generation in range(1,9):
            claimed=self.claim(lease_seconds=1)
            self.assertEqual(claimed['lease']['generation'],generation);self.now+=1
        with self.assertRaises(s.StoreConflict):self.claim()
        self.assertEqual(self.store.inspect(guard=self.guard)['outbox_pending'],1)
        self.assertEqual(self.account()['total_engineering_charge_units'],1)

    def test_current_time_guard_typed_monotone_and_auth_errors_preserved(self):
        request=self.request()
        for value in (True,-1,1.,'1001',2**53):
            with self.subTest(value=value),self.assertRaises(ValueError):self.commit(request,guard=lambda:value)
        with self.assertRaises(s.StoreError):self.store.inspect(guard=None)
        with self.assertRaises(s.StoreUnavailable):self.commit(request,guard=lambda:1000)
        with self.assertRaises(s.StoreUnavailable):self.commit(request,guard=iter([1002,1001]).__next__)
        def denied():raise PermissionError('current authorization denied')
        with self.assertRaises(PermissionError):self.commit(request,guard=denied)
        self.assertEqual(self.account()['sequence'],0)

    def test_input_is_owned_before_guard_and_mismatched_context_fails(self):
        request=self.request();original=copy.deepcopy(request)
        def mutate():request['request_id']='f'*32;return self.now
        receipt=self.commit(request,guard=mutate)
        self.assertEqual(receipt['receipt']['request_sha256'],c.digest(original))
        changed={**self.context(),'actor_person_id':'other'}
        with self.assertRaises(s.StoreConflict):self.store.commit(original,changed,broker=self.broker,guard=self.guard)
        self.assertEqual(self.account()['sequence'],1)

    def test_schema_materialized_state_tail_and_receipt_id_corruption_fail_closed(self):
        self.commit()
        for table in ('accounts','cases','receipts','outbox','deliveries'):
            row=self.query('SELECT id,record_json FROM '+table+' LIMIT 1')[0]
            self.change('UPDATE '+table+' SET record_json=? WHERE id=?',('{}',row[0]))
            with self.subTest(table=table),self.assertRaises(s.StoreUnavailable):self.store.inspect(guard=self.guard)
            self.change('UPDATE '+table+' SET record_json=? WHERE id=?',(row[1],row[0]))
        self.change('CREATE TABLE unexpected (value TEXT)')
        with self.assertRaises(s.StoreUnavailable):self.store.inspect(guard=self.guard)
        self.change('DROP TABLE unexpected')
        self.change("UPDATE receipts SET receipt_id=?",('f'*32,))
        with self.assertRaises(s.StoreUnavailable):self.store.inspect(guard=self.guard)

    def test_deleted_tail_and_restamped_invalid_broker_event_fail(self):
        tail=self.query('SELECT sequence,event_sha256,event_json FROM events ORDER BY sequence DESC LIMIT 1')[0]
        self.change('DELETE FROM events WHERE sequence=?',(tail[0],))
        with self.assertRaises(s.StoreUnavailable):self.store.inspect(guard=self.guard)
        self.change('INSERT INTO events VALUES(?,?,?)',tail)
        body=json.loads(tail[2]);body['payload']['expected_epoch']=5
        raw=c.canonical_bytes(body).decode();sha=c.digest(body)
        self.change('UPDATE events SET event_sha256=?,event_json=? WHERE sequence=?',(sha,raw,tail[0]))
        self.change("UPDATE meta SET value=? WHERE key='head_sha256'",(sha,))
        with self.assertRaises(s.StoreUnavailable):s.RegistryStore.open(self.root,self.store.store_id)

    def test_open_never_creates_resets_or_automatically_upgrades(self):
        with self.assertRaises(s.StoreUnavailable):s.RegistryStore.create(self.root,accounts=self.accounts)
        with self.assertRaises(s.StoreUnavailable):s.RegistryStore.open(self.root,'f'*32)
        absent=self.parent/'absent'
        with self.assertRaises(s.StoreUnavailable):s.RegistryStore.open(absent,self.store.store_id)
        self.assertFalse(absent.exists())
        with self.assertRaises(s.StoreError):s.RegistryStore.migrate(self.root,self.store.store_id,from_version=2,to_version=1,guard=self.guard)
        self.database.unlink()
        with self.assertRaises(s.StoreUnavailable):self.store.inspect(guard=self.guard)
        self.assertFalse(self.database.exists())

    def test_replacement_hardlink_traversal_and_reparse_rejected(self):
        copy_path=self.parent/'copy.sqlite';shutil.copyfile(self.database,copy_path)
        self.database.unlink();copy_path.rename(self.database)
        with self.assertRaises(s.StoreUnavailable):self.store.inspect(guard=self.guard)
        # Expected ID is not an independent whole-file rollback witness.
        reopened=s.RegistryStore.open(self.root,self.store.store_id)
        alias=self.parent/'hardlink.sqlite';os.link(self.database,alias)
        try:
            with self.assertRaises(s.StoreUnavailable):reopened.inspect(guard=self.guard)
        finally:alias.unlink()
        for path in (self.root/'..'/'child',Path(r'\\server\share\registry')):
            with self.assertRaises(s.StoreUnavailable):s.RegistryStore.create(path,accounts=self.accounts)
        with mock.patch.object(s,'_unsafe',return_value=True):
            with self.assertRaises(s.StoreUnavailable):reopened.inspect(guard=self.guard)

    def test_wrong_sqlite_version_metadata_clock_journal_and_size_rejected(self):
        self.change('PRAGMA user_version=1')
        with self.assertRaises(s.StoreUnavailable):self.store.inspect(guard=self.guard)
        self.change('PRAGMA user_version=2')
        self.change("UPDATE meta SET value='1000' WHERE key='last_clock'")
        with self.assertRaises(s.StoreUnavailable):self.store.inspect(guard=self.guard)
        self.change("UPDATE meta SET value='1001' WHERE key='last_clock'")
        wal=self.root/'registry.sqlite-wal';wal.write_bytes(b'forbidden')
        with self.assertRaises(s.StoreUnavailable):self.store.inspect(guard=self.guard)
        wal.unlink()
        with self.database.open('ab') as stream:stream.truncate(s.MAX_DATABASE_BYTES+1)
        with self.assertRaises(s.StoreUnavailable):self.store.inspect(guard=self.guard)


if __name__=='__main__':unittest.main()
