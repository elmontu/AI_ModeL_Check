"""Bounded real SQLite monitoring transactions, recovery and redaction checks."""
from contextlib import closing
import copy
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from model_release_assurance.production_monitoring import contracts as c
from model_release_assurance.production_monitoring import store as m

_ROOT = Path(__file__).resolve().parents[1]
ACTOR = {"kind": "human", "authority_revision": 1}


def event(identifier=1, condition="fault", code="worker_unavailable", resource=100, at=100):
    return {"schema": "mra-fixture-monitor-event/v1", "event_id": format(identifier,"032x"),
        "resource_id": format(resource,"032x"), "observed_at": at, "code": code, "condition": condition, **c.FLAGS}


def receiver_pin():
    return {"schema": "mra-fixture-monitor-pin/v1", "store_id": "a"*32, "sequence": 1, "head_sha256": "b"*64}


_CHILD = r"""
import json,os,sys,time
from pathlib import Path
from contextlib import contextmanager
sys.path[:0]=[str(Path.cwd()/'src'),str(Path.cwd()/'tests')]
from model_release_assurance.production_monitoring.store import MonitorStore,MonitorConflict
from test_production_monitoring_store import event
root,pin,mode,gate,identifier=sys.argv[1:]
pin=json.loads(pin)
store=MonitorStore.open(root,expected_pin=pin)
if gate:
    deadline=time.monotonic()+10
    while not Path(gate).exists():
        if time.monotonic()>deadline: raise RuntimeError('fixture gate timeout')
        time.sleep(.01)
if mode=='after':
    original=MonitorStore._transaction
    @contextmanager
    def crash_after(self,*args,**kwargs):
        with original(self,*args,**kwargs) as value: yield value
        os._exit(74)
    MonitorStore._transaction=crash_after
calls=0
def guard():
    global calls
    calls+=1
    if mode=='before' and calls==2: os._exit(73)
    return 100
try:
    result=store.record(event(int(identifier)),expected_pin=pin,guard=guard)
    print(json.dumps({'outcome':'committed','pin':result['pin']}),flush=True)
except MonitorConflict:
    print(json.dumps({'outcome':'conflict'}),flush=True)
"""


class MonitoringStoreTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory(prefix="mra-monitor-store-")
        self.addCleanup(temporary.cleanup)
        self.base=Path(temporary.name)
        self.store=m.MonitorStore.create(self.base/"store",profile="local_public_fixture")
        self.pin=self.store.initial_pin
        self.now=100

    def guard(self):
        return self.now

    def read(self, *, store=None, pin=None):
        return (store or self.store).read(expected_pin=pin or self.pin,guard=self.guard)

    def record(self, value=None):
        result=self.store.record(event() if value is None else value,expected_pin=self.pin,guard=self.guard)
        self.pin=result['pin']
        return result

    def action(self, action, op=900, incident=1):
        result=self.store.action(format(op,"032x"),format(incident,"032x"),action,ACTOR,
            at=self.now,expected_pin=self.pin,guard=self.guard)
        self.pin=result['pin']
        return result

    def test_production_default_refused_before_output_and_no_overwrite(self):
        output=self.base/'production'
        with self.assertRaises(m.MonitorError): m.MonitorStore.create(output)
        self.assertFalse(output.exists())
        raw=(self.store.root/'monitor.sqlite').read_bytes()
        with self.assertRaises(m.MonitorUnavailable): m.MonitorStore.create(self.store.root,profile='local_public_fixture')
        self.assertEqual((self.store.root/'monitor.sqlite').read_bytes(),raw)
        missing=self.base/'missing'
        with self.assertRaises(m.MonitorUnavailable): m.MonitorStore.open(missing,expected_pin=self.pin)
        self.assertFalse(missing.exists())
        with self.assertRaises(TypeError): m.MonitorStore.open(self.store.root)

    def test_empty_genesis_and_owned_snapshots_reopen(self):
        self.assertEqual(self.pin['sequence'],0)
        self.assertEqual(self.pin['head_sha256'],'0'*64)
        self.assertEqual(self.read()['events'],[])
        initial=self.pin.copy()
        state=self.record()
        state['events'][0]['code']='tampered'
        self.assertEqual(self.read()['events'][0]['code'],'worker_unavailable')
        other=m.MonitorStore.open(self.store.root,expected_pin=initial)
        self.assertEqual(self.read(store=other,pin=initial)['pin'],self.pin)
        with self.assertRaises(m.MonitorError): _=other.initial_pin
        for name,value in c.FLAGS.items(): self.assertIs(self.read()[name],value)

    def test_fault_incident_outbox_atomic_rules_and_all_codes(self):
        for index,code in enumerate(c.RULES,1):
            result=self.record(event(index,code=code,resource=index))
            alert=result['alerts'][-1]
            c.validate_alert(alert)
            self.assertEqual(alert['alert_id'],format(index,'032x'))
            self.assertEqual(alert['incident_id'],alert['alert_id'])
            self.assertFalse(alert['acknowledged'])
            self.assertIsNone(alert['receiver_pin'])
            for field,value in c.RULES[code].items(): self.assertEqual(alert[field],value)
        self.assertEqual(tuple(len(result[key]) for key in ('events','incidents','alerts')),(4,4,4))

    def test_unique_faults_share_active_incident_and_healthy_does_not_resolve(self):
        self.record()
        result=self.record(event(2))
        self.assertEqual(len(result['incidents']),1)
        self.assertEqual(len(result['alerts']),2)
        self.assertEqual(result['alerts'][1]['incident_id'],format(1,'032x'))
        result=self.record(event(3,'healthy'))
        self.assertEqual(result['incidents'][0]['status'],'open')
        self.assertEqual(result['incidents'][0]['latest_event_id'],format(3,'032x'))
        self.assertEqual(len(result['alerts']),2)

    def test_acknowledge_then_current_healthy_allows_resolve_and_new_fault_new_incident(self):
        self.record()
        with self.assertRaises(m.MonitorConflict): self.action('resolve')
        self.action('acknowledge')
        with self.assertRaises(m.MonitorConflict): self.action('resolve',op=901)
        self.record(event(2,'healthy'))
        state=self.action('resolve',op=901)
        self.assertEqual(state['incidents'][0]['status'],'resolved')
        with self.assertRaises(m.MonitorConflict): self.action('acknowledge',op=902)
        state=self.record(event(3))
        self.assertEqual([row['status'] for row in state['incidents']],['resolved','open'])
        self.assertEqual(state['incidents'][1]['id'],format(3,'032x'))

    def test_healthy_for_other_resource_or_superseded_by_fault_cannot_resolve(self):
        self.record(); self.action('acknowledge')
        self.record(event(2,'healthy',resource=101))
        with self.assertRaises(m.MonitorConflict): self.action('resolve',op=901)
        self.record(event(3,'healthy')); self.record(event(4))
        with self.assertRaises(m.MonitorConflict): self.action('resolve',op=901)

    def test_healthy_only_does_not_create_incident_or_alert(self):
        state=self.record(event(1,'healthy'))
        self.assertEqual(state['incidents'],[]); self.assertEqual(state['alerts'],[])
        with self.assertRaises(m.MonitorConflict): self.action('acknowledge')

    def test_event_exact_retry_current_cas_collision_and_stale_write(self):
        first=self.pin.copy(); result=self.record()
        self.assertEqual(self.record()['pin'],result['pin'])
        for value in (event(1,'healthy'),event(1,resource=101)):
            with self.assertRaises(m.MonitorConflict): self.record(value)
        for value in (event(),event(2)):
            with self.assertRaises(m.MonitorConflict):
                self.store.record(value,expected_pin=first,guard=self.guard)
        self.assertEqual(len(self.read()['events']),1)

    def test_operation_idempotency_bound_kind_actor_and_at(self):
        self.record(); result=self.action('acknowledge')
        self.assertEqual(self.action('acknowledge')['pin'],result['pin'])
        for action,actor,at in (('resolve',ACTOR,100),('acknowledge',{**ACTOR,'authority_revision':2},100),('acknowledge',ACTOR,101)):
            with self.assertRaises(m.MonitorConflict):
                self.store.action(format(900,'032x'),format(1,'032x'),action,actor,at=at,expected_pin=self.pin,guard=self.guard)
        with self.assertRaises(m.MonitorConflict):
            self.store.acknowledge_alert(format(900,'032x'),format(1,'032x'),receiver_pin(),at=100,expected_pin=self.pin,guard=self.guard)

    def test_receiver_ack_exact_pin_idempotency_and_no_incident_resolution(self):
        self.record()
        args=(format(800,'032x'),format(1,'032x'),receiver_pin())
        state=self.store.acknowledge_alert(*args,at=100,expected_pin=self.pin,guard=self.guard)
        self.pin=state['pin']
        self.assertTrue(state['alerts'][0]['acknowledged'])
        self.assertEqual(state['incidents'][0]['status'],'open')
        self.assertFalse(state['external_notifications_sent'])
        self.assertEqual(self.store.acknowledge_alert(*args,at=100,expected_pin=self.pin,guard=self.guard)['pin'],self.pin)
        for args2 in ((format(801,'032x'),*args[1:]),(args[0],args[1],{**args[2],'head_sha256':'c'*64})):
            with self.assertRaises(m.MonitorConflict):
                self.store.acknowledge_alert(*args2,at=100,expected_pin=self.pin,guard=self.guard)

    def test_receiver_genesis_and_unknown_alert_refused(self):
        self.record()
        for identifier,pin in ((1,{**receiver_pin(),'sequence':0,'head_sha256':'0'*64}),(2,receiver_pin())):
            with self.assertRaises(m.MonitorConflict):
                self.store.acknowledge_alert(format(800,'032x'),format(identifier,'032x'),pin,at=100,expected_pin=self.pin,guard=self.guard)
        self.assertFalse(self.read()['alerts'][0]['acknowledged'])

    def test_future_observation_reordered_resource_clock_and_action_time_refused(self):
        self.record()
        for value in (event(2,at=101),event(2,'healthy',at=99)):
            with self.assertRaises(m.MonitorConflict): self.record(value)
        for at in (99,101):
            with self.assertRaises(m.MonitorConflict):
                self.store.action(format(900,'032x'),format(1,'032x'),'acknowledge',ACTOR,at=at,expected_pin=self.pin,guard=self.guard)
        self.now=99
        with self.assertRaises(m.MonitorUnavailable): self.read()

    def test_final_guard_failure_rolls_back_event_incident_alert_and_operation(self):
        for operation in ('record','action','ackalert'):
            if operation!='record' and not self.read()['events']: self.record()
            before=self.read()
            calls=0
            def expired():
                nonlocal calls
                calls+=1
                if calls==2: raise PermissionError('test final expiry')
                return self.now
            with self.subTest(operation=operation),self.assertRaises(PermissionError):
                if operation=='record': self.store.record(event(),expected_pin=self.pin,guard=expired)
                elif operation=='action': self.store.action(format(900,'032x'),format(1,'032x'),'acknowledge',ACTOR,at=100,expected_pin=self.pin,guard=expired)
                else: self.store.acknowledge_alert(format(800,'032x'),format(1,'032x'),receiver_pin(),at=100,expected_pin=self.pin,guard=expired)
            self.assertEqual(self.read(),before)

    def test_expensive_replay_precedes_final_current_guard(self):
        original=self.store._validate; calls=0
        def validate(db):
            nonlocal calls
            result=original(db); calls+=1
            if calls==2: self.now=101
            return result
        def guard():
            if self.now>=101: raise PermissionError('expired during replay')
            return self.now
        with patch.object(self.store,'_validate',side_effect=validate):
            with self.assertRaises(PermissionError): self.store.record(event(),expected_pin=self.pin,guard=guard)
        self.assertEqual(self.read()['events'],[])

    def test_owned_inputs_cannot_be_changed_by_guard(self):
        value=event(); pin=self.pin.copy()
        def mutate():
            value['code']='key_unavailable'; pin['head_sha256']='e'*64
            return self.now
        result=self.store.record(value,expected_pin=pin,guard=mutate)
        self.pin=result['pin']
        self.assertEqual(self.read()['events'][0]['code'],'worker_unavailable')

    def test_actual_database_wait_rechecks_guard_after_lock(self):
        errors=[]; entered=threading.Event()
        with closing(sqlite3.connect(self.store.root/'monitor.sqlite',isolation_level=None)) as blocker:
            blocker.execute('BEGIN IMMEDIATE')
            def operation():
                entered.set()
                def current():
                    if self.now>=101: raise PermissionError('expired while waiting')
                    return self.now
                try: self.store.record(event(),expected_pin=self.pin,guard=current)
                except Exception as error: errors.append(error)
            child=threading.Thread(target=operation)
            child.start(); self.assertTrue(entered.wait(2)); self.now=101; blocker.commit()
            child.join(10)
        self.assertFalse(child.is_alive()); self.assertEqual(len(errors),1)
        self.assertIsInstance(errors[0],PermissionError)
        self.assertEqual(self.read()['events'],[])

    def test_rollback_and_same_revision_fork_rejected_by_external_pin(self):
        initial=self.pin.copy(); backup=(self.store.root/'monitor.sqlite').read_bytes()
        other_root=self.base/'fork'; shutil.copytree(self.store.root,other_root)
        other=m.MonitorStore.open(other_root,expected_pin=initial)
        self.record()
        alternate=other.record(event(2),expected_pin=initial,guard=self.guard)
        self.assertNotEqual(alternate['pin']['head_sha256'],self.pin['head_sha256'])
        with self.assertRaises(m.MonitorConflict): m.MonitorStore.open(other_root,expected_pin=self.pin)
        (self.store.root/'monitor.sqlite').write_bytes(backup)
        with self.assertRaises(m.MonitorConflict): m.MonitorStore.open(self.store.root,expected_pin=self.pin)
        with self.assertRaises(m.MonitorConflict): self.read()

    def test_database_and_directory_replacement_hardlink_and_oversize_refused(self):
        path=self.store.root/'monitor.sqlite'
        linked=self.base/'alias'; os.link(path,linked)
        with self.assertRaises(m.MonitorUnavailable): self.read()
        linked.unlink()
        alternative=self.base/'replacement'; alternative.write_bytes(path.read_bytes()); os.replace(alternative,path)
        with self.assertRaises(m.MonitorUnavailable): self.read()
        reopened=m.MonitorStore.open(self.store.root,expected_pin=self.pin)
        oldroot=self.base/'old'; self.store.root.rename(oldroot); shutil.copytree(oldroot,self.store.root)
        with self.assertRaises(m.MonitorUnavailable): self.read(store=reopened)
        opened=m.MonitorStore.open(self.store.root,expected_pin=self.pin)
        with path.open('ab') as stream: stream.truncate(m.MAX_DATABASE_BYTES+1)
        with self.assertRaises(m.MonitorUnavailable): self.read(store=opened)

    def test_paths_hash_percent_and_traversal(self):
        special=m.MonitorStore.create(self.base/'special#%name',profile='local_public_fixture')
        self.assertEqual(special.read(expected_pin=special.initial_pin,guard=self.guard)['events'],[])
        with self.assertRaises(m.MonitorUnavailable):
            m.MonitorStore.create(self.store.root/'..'/'escape',profile='local_public_fixture')
        self.assertFalse((self.base/'escape').exists())

    def test_schema_deletion_hash_and_semantically_invalid_rehashed_history_rejected(self):
        self.record(); path=self.store.root/'monitor.sqlite'; original=path.read_bytes()
        for sql in ('CREATE TABLE extra(value TEXT)','PRAGMA user_version=2','DELETE FROM records',"UPDATE records SET record_json='{}'"):
            path.write_bytes(original)
            with closing(sqlite3.connect(path)) as db, db: db.execute(sql)
            with self.subTest(sql=sql),self.assertRaises(m.MonitorUnavailable): self.read()
        path.write_bytes(original)
        with closing(sqlite3.connect(path)) as db,db:
            record=json.loads(db.execute('SELECT record_json FROM records').fetchone()[0])
            record['payload']['observed_at']=record['at']+1
            sha=c.digest(record)
            db.execute('UPDATE records SET record_json=?,record_sha256=?',(c.canonical_bytes(record).decode(),sha))
            db.execute("UPDATE meta SET value=? WHERE key='head_sha256'",(c.canonical_bytes(sha).decode(),))
        with self.assertRaises(m.MonitorUnavailable): self.read(pin=self.store.initial_pin)

    def test_capacity_permanent_and_invalid_guards(self):
        with patch.object(m,'MAX_RECORDS',1):
            self.record()
            self.assertEqual(self.record()['pin'],self.pin)
            with self.assertRaises(m.MonitorConflict): self.record(event(2))
        for guard in (lambda:True,lambda:-1,lambda:2**53):
            with self.assertRaises(m.MonitorUnavailable): self.store.read(expected_pin=self.pin,guard=guard)
        with self.assertRaises(m.MonitorError): self.store.read(expected_pin=self.pin,guard=None)

    def test_redaction_invalid_payloads_never_persist_or_echo_canaries(self):
        secret='SECRET-token-private-path-123'
        for value in ({**event(),'exception':secret},{**event(),'resource_id':secret},{**event(),'code':secret}):
            try: self.record(value)
            except (ValueError,TypeError) as error: self.assertNotIn(secret,str(error))
            else: self.fail('sensitive field was accepted')
        self.assertNotIn(secret.encode(),(self.store.root/'monitor.sqlite').read_bytes())
        self.assertEqual(self.read()['events'],[])

    def test_pure_captured_replay_has_no_path_clock_or_mutation(self):
        self.record(); raw=(self.store.root/'monitor.sqlite').read_bytes()
        with closing(sqlite3.connect(':memory:')) as db:
            db.deserialize(raw); db.execute('PRAGMA query_only=ON')
            reader=object.__new__(m.MonitorStore); reader._store_id=self.store.store_id
            state=reader._validate(db); reader._floor(state,self.pin)
            self.assertEqual(reader._snapshot(state)['events'],[event()])
        self.assertEqual((self.store.root/'monitor.sqlite').read_bytes(),raw)

    def child(self,mode,gate='',identifier=1):
        process=subprocess.Popen([sys.executable,'-B','-c',_CHILD,str(self.store.root),json.dumps(self.pin),mode,str(gate),str(identifier)],
            cwd=_ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        def stop():
            if process.poll() is None:
                process.kill(); process.wait(timeout=10)
        self.addCleanup(stop)
        return process

    def test_independent_process_write_race_has_one_atomic_outcome(self):
        gate=self.base/'gate'; children=[self.child('race',gate,i) for i in (1,2)]
        gate.write_text('ready')
        outcomes=[]
        for child in children:
            out,err=child.communicate(timeout=25)
            self.assertEqual(child.returncode,0,err); outcomes.append(json.loads(out)['outcome'])
        self.assertCountEqual(outcomes,['committed','conflict'])
        state=self.read()
        self.assertEqual([len(state[key]) for key in ('events','incidents','alerts')],[1,1,1])

    def test_abrupt_crash_before_commit_retains_no_partial_incident_or_outbox(self):
        child=self.child('before'); _,err=child.communicate(timeout=25)
        self.assertEqual(child.returncode,73,err)
        opened=m.MonitorStore.open(self.store.root,expected_pin=self.pin)
        state=self.read(store=opened)
        self.assertEqual([state[key] for key in ('events','incidents','alerts','operations')],[[],[],[],[]])
        opened.record(event(),expected_pin=self.pin,guard=self.guard)

    def test_abrupt_crash_after_commit_reopens_and_exact_retry_does_not_duplicate(self):
        child=self.child('after'); _,err=child.communicate(timeout=25)
        self.assertEqual(child.returncode,74,err)
        opened=m.MonitorStore.open(self.store.root,expected_pin=self.pin)
        state=self.read(store=opened)
        repeated=opened.record(event(),expected_pin=state['pin'],guard=self.guard)
        self.assertEqual(repeated,state)
        self.assertEqual([len(state[key]) for key in ('events','incidents','alerts')],[1,1,1])


if __name__=='__main__': unittest.main()
