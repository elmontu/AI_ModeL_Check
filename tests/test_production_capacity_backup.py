"""Historical two-store image conservation, independent pins and capture races."""
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
import tempfile
import time
import unittest
from unittest.mock import patch

from model_release_assurance.production_capacity import backup as b, contracts as c
from model_release_assurance.production_registry.store import RegistryStore
from model_release_assurance.production_witness.store import WitnessStore
from model_release_assurance.production_witness.rehearsal import WitnessFixture
from model_release_assurance.production_witness.contracts import create_intent

_ROOT = Path(__file__).resolve().parents[1]
_LOCAL = 'local_public_fixture'
_CHILD = r"""
import json,sys,time
from pathlib import Path
sys.path[:0]=[str(Path.cwd()/'src')]
from model_release_assurance.production_registry.store import RegistryStore
root,identifier,ready=sys.argv[1:]
store=RegistryStore.open(root,identifier)
Path(ready).write_text('ready')
result=store.activate_broker('e'*32,expected_epoch=1,guard=lambda:1000)
print(json.dumps(result),flush=True)
"""


class CapacityBackupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary=tempfile.TemporaryDirectory(prefix='mra-backup-base-')
        cls.base=Path(cls.temporary.name)
        cls.fixture=WitnessFixture(cls.base/'fixture')
        cls.requests=[cls.fixture.request()]
        cls.fixture.commit(cls.requests[0])
        cls.requests.append(cls.fixture.request('case-b'))
        cls.fixture.commit(cls.requests[1])
        rf=cls.fixture.registry
        worker=rf.token('worker')
        claim=rf.service.claim_outbox(worker,'case-a',10)
        rf.service.acknowledge(worker,'case-a',claim['lease'])
        cls.fixture.recover(cls.requests[0])
        cls.anchor=b.registry_anchor(rf.store,guard=rf.clock)
        cls.pin=cls.fixture.sink.floor

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def setUp(self):
        temporary=tempfile.TemporaryDirectory(prefix='mra-backup-case-')
        self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name)
        shutil.copytree(self.fixture.registry.store.root,self.root/'registry')
        shutil.copytree(self.fixture.witness.root,self.root/'witness')
        self.registry=RegistryStore.open(self.root/'registry',self.anchor['store_id'])
        self.witness=WitnessStore.open(self.root/'witness',expected_pin=self.pin)
        self.now=1000

    def guard(self): return self.now

    def capture(self, output=None, **kwargs):
        return b.capture_quiesced(self.registry,self.witness,output or self.root/'backup',
            expected_registry_anchor=kwargs.pop('expected_registry_anchor',self.anchor),
            expected_witness_pin=kwargs.pop('expected_witness_pin',self.pin),
            guard=kwargs.pop('guard',self.guard),profile=kwargs.pop('profile',_LOCAL),**kwargs)

    def pins(self,report):
        return {'expected_manifest_sha256':report['manifest_sha256'],
            'expected_registry_anchor':self.anchor,'expected_witness_pin':self.pin}

    def rewrite_manifest(self,root):
        raw=json.loads((root/'manifest.json').read_bytes())
        for name in ('registry.sqlite','witness.sqlite'):
            data=(root/name).read_bytes()
            raw['files'][name]={'sha256':hashlib.sha256(data).hexdigest(),'size_bytes':len(data)}
        result=c.canonical_bytes(raw);(root/'manifest.json').write_bytes(result)
        return hashlib.sha256(result).hexdigest()

    def test_capture_verify_restore_conserves_full_receipts_charges_and_outbox(self):
        original={name:(self.root/name/(name+'.sqlite')).read_bytes() for name in ('registry','witness')}
        report=self.capture()
        self.assertEqual(report['status'],'historical_backup_verified')
        evidence=report['evidence']
        self.assertEqual((evidence['engineering_charge_units'],evidence['receipt_count'],evidence['committed_intents']),(2,2,2))
        self.assertEqual((evidence['outbox_count'],evidence['outbox_acknowledged'],evidence['outbox_pending']),(2,1,1))
        self.assertEqual(evidence['pending_intents'],0)
        verified=b.verify_backup(self.root/'backup',**self.pins(report))
        restored=b.restore_backup(self.root/'backup',self.root/'restored',profile=_LOCAL,**self.pins(report))
        self.assertEqual(restored['evidence'],evidence)
        self.assertEqual(restored['status'],'historical_restore_verified')
        self.assertGreater(restored['restore_elapsed_ns'],0)
        self.assertEqual(set(p.name for p in (self.root/'restored').iterdir()),{'registry.sqlite','witness.sqlite','manifest.json'})
        for name,raw in original.items(): self.assertEqual((self.root/name/(name+'.sqlite')).read_bytes(),raw)
        for name in ('registry.sqlite','witness.sqlite','manifest.json'):
            self.assertEqual((self.root/'restored'/name).read_bytes(),(self.root/'backup'/name).read_bytes())
        for key,value in c.FLAGS.items(): self.assertIs(verified[key],value)
        self.assertFalse(verified['current_authorization_checked']);self.assertFalse(verified['release_resumed'])

    def test_restoration_never_constructs_live_service_or_activates_broker(self):
        report=self.capture()
        with patch('model_release_assurance.production_registry.service.FixtureRegistryService.__init__',side_effect=AssertionError('live constructor')), \
             patch.object(RegistryStore,'activate_broker',side_effect=AssertionError('activation')):
            restored=b.restore_backup(self.root/'backup',self.root/'restored',profile=_LOCAL,**self.pins(report))
        self.assertEqual(restored['registry_anchor']['broker_epoch'],self.anchor['broker_epoch'])

    def test_profiles_refuse_before_any_output_or_source_access(self):
        with self.assertRaises(c.CapacityError):
            b.capture_quiesced(None,None,self.root/'capture-denied',expected_registry_anchor={},expected_witness_pin={},guard=None)
        with self.assertRaises(c.CapacityError):
            b.restore_backup(self.root/'missing',self.root/'restore-denied',expected_manifest_sha256='',expected_registry_anchor={},expected_witness_pin={})
        self.assertFalse((self.root/'capture-denied').exists());self.assertFalse((self.root/'restore-denied').exists())

    def test_exact_external_pins_required_wrong_or_ancestor_pins_cannot_weaken_cut(self):
        report=self.capture(); kwargs=self.pins(report)
        with self.assertRaises(c.CapacityError): b.verify_backup(self.root/'backup',**{**kwargs,'expected_manifest_sha256':'0'*64})
        with self.assertRaises(c.CapacityError):
            b.verify_backup(self.root/'backup',**{**kwargs,'expected_registry_anchor':{**self.anchor,'store_id':'e'*32}})
        with self.assertRaises(c.CapacityError):
            b.verify_backup(self.root/'backup',**{**kwargs,'expected_witness_pin':self.fixture.witness.initial_pin})
        with self.assertRaises(c.CapacityError):
            b.verify_backup(self.root/'backup',**{**kwargs,'expected_witness_pin':{**self.pin,'head_sha256':'f'*64}})
        with self.assertRaises(c.CapacityError): b.verify_backup(self.root/'backup')

    def test_source_registry_ahead_of_witness_refused_without_output(self):
        self.registry.activate_broker('e'*32,expected_epoch=self.anchor['broker_epoch'],guard=self.guard)
        ahead=b.registry_anchor(self.registry,guard=self.guard)
        with self.assertRaises(c.CapacityError): self.capture(expected_registry_anchor=ahead)
        self.assertFalse((self.root/'backup').exists())

    def test_stale_source_anchor_refused_without_output(self):
        self.registry.activate_broker('e'*32,expected_epoch=self.anchor['broker_epoch'],guard=self.guard)
        with self.assertRaises(c.CapacityError): self.capture()
        self.assertFalse((self.root/'backup').exists())

    def test_pending_intent_even_at_equal_cut_cannot_claim_reconciled_backup(self):
        fixture=WitnessFixture(self.root/'pending')
        request=fixture.request()
        history=fixture.reader.snapshot(guard=fixture.registry.clock)
        diagnosis=fixture.witness.prepare(create_intent(history,request),history,
            expected_pin=fixture.service.required_pin,guard=fixture.registry.clock)
        anchor=b.registry_anchor(fixture.registry.store,guard=fixture.registry.clock)
        with self.assertRaises(c.CapacityError):
            b.capture_quiesced(fixture.registry.store,fixture.witness,self.root/'denied',
                expected_registry_anchor=anchor,expected_witness_pin=diagnosis['pin'],guard=fixture.registry.clock,profile=_LOCAL)
        self.assertEqual(fixture.witness.status(expected_pin=diagnosis['pin'],guard=fixture.registry.clock)['pending_intents'],1)
        self.assertFalse((self.root/'denied').exists())

    def test_individually_valid_mixed_cut_and_different_namespace_pair_rejected(self):
        report=self.capture()
        other=WitnessFixture(self.root/'other')
        (self.root/'backup'/'witness.sqlite').write_bytes((other.witness.root/'witness.sqlite').read_bytes())
        sha=self.rewrite_manifest(self.root/'backup')
        with self.assertRaises(c.CapacityError):
            b.verify_backup(self.root/'backup',**{**self.pins(report),'expected_manifest_sha256':sha,'expected_witness_pin':other.sink.floor})

    def advanced_cut(self, registry, witness, broker, pin):
        registry.activate_broker(broker,expected_epoch=self.anchor['broker_epoch'],guard=self.guard)
        anchor=b.registry_anchor(registry,guard=self.guard)
        with registry._connect() as db:
            rows=b._events(db)
        from model_release_assurance.production_witness.contracts import FLAGS
        history={'schema':'mra-fixture-registry-history-snapshot/v1','store_id':registry.store_id,
            'schema_version':2,'broker_epoch':anchor['broker_epoch'],'broker_id':anchor['broker_id'],
            'event_sequence':anchor['event_sequence'],'event_head_sha256':anchor['event_head_sha256'],
            'observed_at':self.now,'events':rows,**FLAGS}
        observed=witness.observe(history,expected_pin=pin,guard=self.guard)
        return anchor,observed['pin']

    def test_coherently_older_valid_pair_cannot_restore_against_newer_external_cut(self):
        old=self.capture()
        anchor,pin=self.advanced_cut(self.registry,self.witness,'d'*32,self.pin)
        new=b.capture_quiesced(self.registry,self.witness,self.root/'new',expected_registry_anchor=anchor,
            expected_witness_pin=pin,guard=self.guard,profile=_LOCAL)
        b.verify_backup(self.root/'new',expected_manifest_sha256=new['manifest_sha256'],
            expected_registry_anchor=anchor,expected_witness_pin=pin)
        with self.assertRaises(c.CapacityError):
            b.restore_backup(self.root/'backup',self.root/'denied',profile=_LOCAL,
                expected_manifest_sha256=old['manifest_sha256'],expected_registry_anchor=anchor,expected_witness_pin=pin)
        self.assertFalse((self.root/'denied').exists())

    def test_same_identity_same_sequence_fork_rejected_by_other_branch_external_pins(self):
        shutil.copytree(self.registry.root,self.root/'fork-registry')
        shutil.copytree(self.witness.root,self.root/'fork-witness')
        registry=RegistryStore.open(self.root/'fork-registry',self.registry.store_id)
        witness=WitnessStore.open(self.root/'fork-witness',expected_pin=self.pin)
        anchor_a,pin_a=self.advanced_cut(self.registry,self.witness,'d'*32,self.pin)
        anchor_b,pin_b=self.advanced_cut(registry,witness,'e'*32,self.pin)
        self.assertEqual(anchor_a['event_sequence'],anchor_b['event_sequence'])
        self.assertEqual(pin_a['revision'],pin_b['revision'])
        self.assertNotEqual(anchor_a['event_head_sha256'],anchor_b['event_head_sha256'])
        report=b.capture_quiesced(registry,witness,self.root/'fork-backup',expected_registry_anchor=anchor_b,
            expected_witness_pin=pin_b,guard=self.guard,profile=_LOCAL)
        with self.assertRaises(c.CapacityError):
            b.verify_backup(self.root/'fork-backup',expected_manifest_sha256=report['manifest_sha256'],
                expected_registry_anchor=anchor_a,expected_witness_pin=pin_a)

    def test_missing_extra_nested_hardlinked_and_truncated_inventory_refused(self):
        report=self.capture(); root=self.root/'backup'; pins=self.pins(report)
        original=(root/'witness.sqlite').read_bytes()
        (root/'witness.sqlite').unlink()
        with self.assertRaises(c.CapacityError): b.verify_backup(root,**pins)
        (root/'witness.sqlite').write_bytes(original)
        for name in ('unapproved','registry.sqlite-wal'):
            path=root/name
            if name=='unapproved': path.mkdir()
            else: path.write_bytes(b'rogue')
            with self.assertRaises(c.CapacityError): b.verify_backup(root,**pins)
            path.rmdir() if path.is_dir() else path.unlink()
        link=self.root/'link';os.link(root/'witness.sqlite',link)
        with self.assertRaises(c.CapacityError): b.verify_backup(root,**pins)
        link.unlink();(root/'witness.sqlite').write_bytes(original[:4096])
        sha=self.rewrite_manifest(root)
        with self.assertRaises(c.CapacityError): b.verify_backup(root,**{**pins,'expected_manifest_sha256':sha})

    def test_tampered_projection_and_rehashed_manifest_cannot_bypass_replay(self):
        report=self.capture(); root=self.root/'backup';path=root/'registry.sqlite'
        with closing(sqlite3.connect(path)) as db,db:
            row=db.execute('SELECT id,record_json FROM accounts').fetchone()
            value=json.loads(row[1]);value['total_engineering_charge_units']=0
            db.execute('UPDATE accounts SET record_json=? WHERE id=?',(c.canonical_bytes(value).decode(),row[0]))
        sha=self.rewrite_manifest(root)
        with self.assertRaises(c.CapacityError): b.verify_backup(root,**{**self.pins(report),'expected_manifest_sha256':sha})

    def test_deleted_acknowledgment_and_extra_sql_schema_rejected(self):
        report=self.capture(); root=self.root/'backup';path=root/'registry.sqlite'; original=path.read_bytes()
        for sql in ('DELETE FROM deliveries','CREATE VIEW unsafe AS SELECT load_extension("secret")'):
            path.write_bytes(original)
            with closing(sqlite3.connect(path)) as db,db: db.execute(sql)
            sha=self.rewrite_manifest(root)
            with self.assertRaises(c.CapacityError): b.verify_backup(root,**{**self.pins(report),'expected_manifest_sha256':sha})

    def test_manifest_ambiguity_unknown_fields_nonfinite_and_bool_alias_refused(self):
        report=self.capture();root=self.root/'backup'; original=(root/'manifest.json').read_bytes()
        values=[original[:-1]+b',"schema":"mra-fixture-recovery-bundle/v1"}',b'{"overflow":1e999}']
        for transform in (lambda d:d.update(unreviewed=True),lambda d:d.update(current_authorization_checked=0),
                          lambda d:d['files']['registry.sqlite'].update(size_bytes=True)):
            doc=json.loads(original);transform(doc);values.append(c.canonical_bytes(doc))
        for raw in values:
            (root/'manifest.json').write_bytes(raw)
            with self.assertRaises(c.CapacityError):
                b.verify_backup(root,**{**self.pins(report),'expected_manifest_sha256':hashlib.sha256(raw).hexdigest()})

    def test_inventory_enumerates_at_most_four_names_before_rejecting(self):
        report=self.capture();root=self.root/'backup';seen=[]
        def unlimited(path):
            for number in range(10000):
                seen.append(number)
                if number == 4: self.fail('Unbounded inventory enumeration')
                yield path/str(number)
        with patch.object(Path,'iterdir',unlimited):
            with self.assertRaises(c.CapacityError): b.verify_backup(root,**self.pins(report))
        self.assertEqual(seen,[0,1,2,3])

    def test_same_byte_file_replacement_during_replay_refused(self):
        report=self.capture();root=self.root/'backup';original=b._check_manifest
        before=(root/'registry.sqlite').stat().st_ino
        def replace(*args,**kwargs):
            result=original(*args,**kwargs)
            replacement=self.root/'replacement.sqlite'
            replacement.write_bytes((root/'registry.sqlite').read_bytes())
            replacement.replace(root/'registry.sqlite')
            self.assertNotEqual(before,(root/'registry.sqlite').stat().st_ino)
            return result
        with patch.object(b,'_check_manifest',side_effect=replace):
            with self.assertRaises(c.CapacityError): b.verify_backup(root,**self.pins(report))

    def test_implementation_binds_all_four_frozen_validator_sources(self):
        report=self.capture();original=b.io.read_file
        expected={('production_registry','store.py'),('production_registry','contracts.py'),
                  ('production_witness','store.py'),('production_witness','contracts.py')}
        seen=set()
        def observe(path,*args,**kwargs):
            key=(Path(path).parent.name,Path(path).name)
            if key in expected: seen.add(key)
            return original(path,*args,**kwargs)
        with patch.object(b.io,'read_file',side_effect=observe): b._implementation_sha256()
        self.assertEqual(seen,expected)
        for module in (b.registry_module,b.registry_contracts,b.witness_module,b.witness_contracts):
            selected=Path(module.__file__).absolute()
            def changed(path,*args,**kwargs):
                raw=original(path,*args,**kwargs)
                return raw+b'\n# simulated dependency change\n' if Path(path)==selected else raw
            with self.subTest(module=module.__name__),patch.object(b.io,'read_file',side_effect=changed):
                with self.assertRaises(c.CapacityError): b.verify_backup(self.root/'backup',**self.pins(report))

    def test_source_implementation_change_refuses_verify_and_restore_without_output(self):
        report=self.capture()
        with patch.object(b,'_implementation_sha256',return_value='0'*64):
            with self.assertRaises(c.CapacityError): b.verify_backup(self.root/'backup',**self.pins(report))
            with self.assertRaises(c.CapacityError):
                b.restore_backup(self.root/'backup',self.root/'denied',profile=_LOCAL,**self.pins(report))
        self.assertFalse((self.root/'denied').exists())

    def test_no_overwrite_and_traversal_for_capture_and_restore(self):
        report=self.capture(); raw=(self.root/'backup'/'manifest.json').read_bytes()
        with self.assertRaises(c.CapacityError): self.capture()
        with self.assertRaises(c.CapacityError):
            b.restore_backup(self.root/'backup',self.root/'backup',profile=_LOCAL,**self.pins(report))
        with self.assertRaises(c.CapacityError):
            b.restore_backup(self.root/'backup',self.root/'backup'/'..'/'escape',profile=_LOCAL,**self.pins(report))
        self.assertEqual((self.root/'backup'/'manifest.json').read_bytes(),raw)
        self.assertFalse((self.root/'escape').exists())

    def test_final_guard_failure_before_output_and_after_copy_never_returns_success(self):
        calls=0
        def expires():
            nonlocal calls
            calls+=1
            if calls==2: raise PermissionError('private secret expiry')
            return 1000
        with self.assertRaises(c.CapacityError) as caught: self.capture(guard=expires)
        self.assertNotIn('private secret',str(caught.exception));self.assertFalse((self.root/'backup').exists())
        calls=0
        def late():
            nonlocal calls
            calls+=1
            if calls==3: raise PermissionError('expiry after copy')
            return 1000
        with self.assertRaises(c.CapacityError): self.capture(guard=late)
        self.assertTrue((self.root/'backup'/'manifest.json').exists())
        self.assertEqual(b.registry_anchor(self.registry,guard=self.guard),self.anchor)

    def test_owned_external_pin_inputs_before_guard(self):
        anchor,pin=copy.deepcopy(self.anchor),copy.deepcopy(self.pin)
        def mutate():
            anchor['event_head_sha256']='e'*64;pin['head_sha256']='e'*64
            return self.now
        report=self.capture(expected_registry_anchor=anchor,expected_witness_pin=pin,guard=mutate)
        self.assertEqual(report['registry_anchor'],self.anchor);self.assertEqual(report['witness_pin'],self.pin)

    def test_input_change_during_restore_rejected_and_partial_new_files_preserved(self):
        report=self.capture();root=self.root/'backup'; original=b.io.exclusive_write
        def alter(path,raw):
            result=original(path,raw)
            if Path(path).name=='manifest.json':
                (root/'manifest.json').write_bytes((root/'manifest.json').read_bytes()+b' ')
            return result
        with patch.object(b.io,'exclusive_write',side_effect=alter):
            with self.assertRaises(c.CapacityError):
                b.restore_backup(root,self.root/'restored',profile=_LOCAL,**self.pins(report))
        self.assertTrue((self.root/'restored'/'registry.sqlite').exists())

    def test_destination_failure_does_not_repair_or_mutate_source(self):
        original=(self.registry.root/'registry.sqlite').read_bytes()
        writer=b.io.exclusive_write
        def fails(path,raw):
            if Path(path).name=='witness.sqlite': raise OSError('private path failure')
            return writer(path,raw)
        with patch.object(b.io,'exclusive_write',side_effect=fails):
            with self.assertRaises(c.CapacityError): self.capture()
        self.assertTrue((self.root/'backup'/'registry.sqlite').exists())
        self.assertFalse((self.root/'backup'/'manifest.json').exists())
        self.assertEqual((self.registry.root/'registry.sqlite').read_bytes(),original)
        with self.assertRaises(c.CapacityError): self.capture()

    def test_clock_rollback_bool_and_wrong_types_fail_before_capture_output(self):
        for guard in (lambda:999,lambda:True,lambda:-1):
            with self.assertRaises(c.CapacityError): self.capture(guard=guard)
        with self.assertRaises(c.CapacityError): b.registry_anchor(object(),guard=self.guard)
        self.assertFalse((self.root/'backup').exists())

    def test_independent_process_writer_waits_until_both_images_are_captured(self):
        original=b.io.exclusive_write; children=[]; marker=self.root/'ready'
        def launch(path,raw):
            if not children:
                child=subprocess.Popen([sys.executable,'-B','-c',_CHILD,str(self.registry.root),self.registry.store_id,str(marker)],
                    cwd=_ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
                children.append(child)
                deadline=time.monotonic()+10
                while not marker.exists():
                    if time.monotonic()>=deadline: self.fail('child did not enter')
                    time.sleep(.01)
                self.assertIsNone(child.poll())
            return original(path,raw)
        try:
            with patch.object(b.io,'exclusive_write',side_effect=launch): report=self.capture()
            out,err=children[0].communicate(timeout=15)
            self.assertEqual(children[0].returncode,0,err)
            self.assertEqual(json.loads(out)['epoch'],self.anchor['broker_epoch']+1)
            verified=b.verify_backup(self.root/'backup',**self.pins(report))
            self.assertEqual(verified['registry_anchor'],self.anchor)
            self.assertGreater(b.registry_anchor(self.registry,guard=self.guard)['event_sequence'],self.anchor['event_sequence'])
        finally:
            for child in children:
                if child.poll() is None: child.kill();child.wait(timeout=10)


if __name__=='__main__': unittest.main()
