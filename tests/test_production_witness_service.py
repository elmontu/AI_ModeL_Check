"""Signed case authority, external floors and uncertain witness recovery."""
from contextlib import contextmanager
import copy
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

from model_release_assurance.production_identity.policy import PermissionDenied
from model_release_assurance.production_registry.contracts import account_id
from model_release_assurance.production_registry.store import RegistryStore, StoreConflict
from model_release_assurance.production_registry.service import FixtureRegistryService
from model_release_assurance.production_witness.contracts import create_intent
from model_release_assurance.production_witness.reader import RegistryHistoryReader
from model_release_assurance.production_witness.rehearsal import WitnessFixture, FileCheckpointSink
from model_release_assurance.production_witness.service import FixtureWitnessService, WitnessQuarantined
from model_release_assurance.production_witness.store import WitnessStore, WitnessConflict, WitnessUnavailable


class WitnessServiceTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory(prefix="mra-witness-service-")
        self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name)
        self.f=WitnessFixture(self.root)
        self.r=self.f.registry

    def status(self):
        return self.f.witness.status(expected_pin=self.f.service.required_pin,guard=self.r.clock)

    def pending(self,request):
        history=self.f.reader.snapshot(guard=self.r.clock)
        result=self.f.witness.prepare(create_intent(history,request),history,
            expected_pin=self.f.service.required_pin,guard=self.r.clock)
        self.f.service._accept(result,self.r.clock)
        return result

    def test_signed_witnessed_commit_binds_original_receipt_and_has_one_charge(self):
        request=self.f.request();first=self.f.commit(request);second=self.f.commit(request)
        self.assertEqual(first['receipt'],second['receipt'])
        self.assertEqual(first['status'],'witnessed_metadata')
        self.assertEqual(self.status()['committed_intents'],1)
        self.assertFalse(first['production_authorized']);self.assertFalse(first['independent_custody_verified'])
        self.assertEqual(self.r.service.state(self.r.token('auditor'),'case-a')['account']['total_engineering_charge_units'],1)

    def test_sink_failure_before_registry_commit_keeps_pending_intent_without_charge(self):
        request=self.f.request()
        with mock.patch.object(self.f.service,'_sink',side_effect=OSError('fixture outage')):
            with self.assertRaises(OSError):self.f.commit(request)
        self.assertEqual(self.r.store.inspect(guard=self.r.clock)['receipt_count'],0)
        # Failure at the initial observation may precede prepare. In both
        # cases no charge or unwitnessed success may be produced.
        self.assertGreaterEqual(self.f.service.required_pin['revision'],self.f.sink.floor['revision'])

    def test_intent_sink_failure_is_retained_and_exact_retry_is_safe(self):
        request=self.f.request();real=self.f.service._sink;calls=[0]
        def sink(pin):
            calls[0]+=1
            if calls[0]==2:raise OSError('intent checkpoint unavailable')
            return real(pin)
        with mock.patch.object(self.f.service,'_sink',side_effect=sink):
            with self.assertRaises(OSError):self.f.commit(request)
        self.assertEqual(self.status()['pending_intents'],1)
        self.assertEqual(self.r.store.inspect(guard=self.r.clock)['receipt_count'],0)
        result=self.f.commit(request)
        self.assertEqual(result['status'],'witnessed_metadata')
        self.assertEqual(self.r.store.inspect(guard=self.r.clock)['receipt_count'],1)

    def test_slow_checkpoint_sink_cannot_commit_after_token_deadline(self):
        request=self.f.request();token=self.r.token('operator');real=self.f.service._sink;calls=[0]
        def sink(pin):
            result=real(pin);calls[0]+=1
            if calls[0]==2:self.r.now=1240
            return result
        with mock.patch.object(self.f.service,'_sink',side_effect=sink):
            with self.assertRaises(PermissionDenied):self.f.service.commit(token,'case-a',request)
        self.assertEqual(self.r.store.inspect(guard=self.r.clock)['receipt_count'],0)
        self.assertEqual(self.status()['pending_intents'],1)

    def test_checkpoint_callback_mutation_cannot_downgrade_required_floor(self):
        request=self.f.request();real=self.f.service._sink
        def mutate(pin):
            real(pin);pin['revision']=1;pin['head_sha256']='0'*64
        with mock.patch.object(self.f.service,'_sink',side_effect=mutate):result=self.f.commit(request)
        self.assertEqual(self.f.service.required_pin,result['witness_pin'])
        self.assertEqual(self.f.service.required_pin,self.f.sink.floor)

    def test_constructor_promotes_newest_observed_pin_before_startup(self):
        old=self.f.sink.floor;request=self.f.request();self.f.commit(request)
        seen=[]
        service=FixtureWitnessService(self.r.service,self.f.witness,expected_pin=old,
                                     checkpoint_sink=lambda pin:seen.append(pin))
        self.assertEqual(service.required_pin,self.f.service.required_pin)
        self.assertEqual(seen[-1],self.f.service.required_pin)
        self.assertGreater(service.required_pin['revision'],old['revision'])

    def test_witness_outage_after_registry_commit_recovers_same_receipt(self):
        request=self.f.request();original=self.f.witness.observe;calls=[0]
        def outage(*args,**kwargs):
            calls[0]+=1
            if calls[0]==2:raise WitnessUnavailable('fixture outage')
            return original(*args,**kwargs)
        with mock.patch.object(self.f.witness,'observe',side_effect=outage):
            with self.assertRaises(WitnessUnavailable):self.f.commit(request)
        prior=self.r.service.read(self.r.token('auditor'),'case-a',request['request_id'])
        self.assertEqual(self.status()['pending_intents'],1)
        recovered=self.f.recover(request)
        self.assertEqual(recovered['receipt'],prior)
        self.assertEqual(self.r.store.inspect(guard=self.r.clock)['receipt_count'],1)

    def test_recovery_of_committed_metadata_after_object_retention_expiry(self):
        request=self.f.request();self.pending(request);prior=self.r.commit(request)
        self.r.now=1240
        token=self.r.token('auditor',expires_at=1249)
        result=self.f.service.recover(token,'case-a',request['request_id'])
        self.assertEqual(result['receipt'],prior)
        self.assertEqual(result['status'],'witnessed_metadata')

    def test_uncertain_missing_commit_stays_quarantined(self):
        request=self.f.request();self.pending(request)
        result=self.f.recover(request)
        self.assertEqual(result['status'],'quarantined')
        self.assertEqual(result['intent_state'],'pending')
        self.assertEqual(self.status()['pending_intents'],1)

    def test_broker_handover_alone_does_not_abort_or_retry_pending_intent(self):
        request=self.f.request();self.pending(request)
        fresh=FixtureRegistryService(self.r.identity,self.r.storage,
                                    RegistryStore.open(self.r.store.root,self.r.store.store_id))
        service=FixtureWitnessService(fresh,self.f.witness,expected_pin=self.f.sink.floor,checkpoint_sink=self.f.sink)
        result=service.recover(self.r.token('auditor'),'case-a',request['request_id'])
        self.assertEqual(result['intent_state'],'pending')
        with self.assertRaises(WitnessQuarantined):service.commit(self.r.token('operator'),'case-a',request)
        self.assertEqual(self.r.store.inspect(guard=self.r.clock)['receipt_count'],0)

    def test_racing_predecessor_intents_resolve_winner_and_abort_stale_loser(self):
        first=self.f.request();second=self.f.request('case-b')
        self.pending(first);self.pending(second)
        self.r.commit(first)
        result=self.f.recover(first)
        self.assertEqual(result['status'],'witnessed_metadata')
        self.assertEqual(self.status()['committed_intents'],1)
        self.assertEqual(self.status()['aborted_intents'],1)
        with self.assertRaises(WitnessQuarantined):self.f.commit(second)
        self.assertEqual(self.r.store.inspect(guard=self.r.clock)['receipt_count'],1)

    def test_bypassed_commit_without_prior_intent_is_quarantined(self):
        request=self.f.request();self.r.commit(request)
        before=self.f.service.required_pin
        with self.assertRaises(WitnessConflict):self.f.recover(request)
        self.assertEqual(self.f.service.required_pin,before)

    def test_changed_request_id_payload_is_permanently_rejected(self):
        request=self.f.request();self.f.commit(request)
        changed=self.r.request(request_id=request['request_id'])
        with self.assertRaises(WitnessQuarantined):self.f.commit(changed)
        self.assertEqual(self.r.store.inspect(guard=self.r.clock)['receipt_count'],1)

    def test_wrong_actor_and_case_and_revoked_current_grant_are_denied(self):
        request=self.f.request()
        with self.assertRaises(PermissionDenied):self.f.service.commit(self.r.token('other'),'case-a',request)
        with self.assertRaises(PermissionDenied):self.f.service.commit(self.r.token('operator'),'case-b',request)
        self.f.commit(request)
        with self.assertRaises(PermissionDenied):self.f.service.recover(self.r.token('auditor'),'case-b',request['request_id'])
        self.r.update(grants=tuple(g for g in self.r.authority.grants if g.person_id!='person-auditor'))
        with self.assertRaises(PermissionDenied):self.f.recover(request)

    def test_unknown_namespace_cannot_be_enrolled_via_case_access(self):
        with self.assertRaises(PermissionDenied):self.f.service.recover(self.r.token('auditor'),'case-c','a'*32)

    def test_new_ledger_identity_cannot_substitute_for_the_pinned_registry(self):
        store=RegistryStore.create(self.root/'different',accounts=[{'agency_id':'agency','project_id':'project'}])
        service=FixtureRegistryService(self.r.identity,self.r.storage,store)
        with self.assertRaises(WitnessQuarantined):FixtureWitnessService(service,self.f.witness,
            expected_pin=self.f.sink.floor,checkpoint_sink=self.f.sink)

    def test_actual_old_registry_copy_is_rejected_with_retained_witness(self):
        backup=self.root/'before.sqlite';shutil.copyfile(self.r.store.root/'registry.sqlite',backup)
        request=self.f.request();self.f.commit(request)
        restored=self.root/'restored';restored.mkdir();shutil.copyfile(backup,restored/'registry.sqlite')
        registry=FixtureRegistryService(self.r.identity,self.r.storage,RegistryStore.open(restored,self.r.store.store_id))
        service=FixtureWitnessService(registry,self.f.witness,expected_pin=self.f.sink.floor,checkpoint_sink=self.f.sink)
        with self.assertRaises(WitnessConflict):service.recover(self.r.token('auditor'),'case-a',request['request_id'])

    def test_missing_external_floor_or_sink_never_defaults_to_genesis(self):
        with self.assertRaises((ValueError,TypeError)):FixtureWitnessService(self.r.service,self.f.witness,expected_pin=None,checkpoint_sink=self.f.sink)
        with self.assertRaises(ValueError):FixtureWitnessService(self.r.service,self.f.witness,expected_pin=self.f.sink.floor,checkpoint_sink=None)

    def test_reader_holds_registry_lock_during_witness_and_sink(self):
        original=self.f.service._reader.with_snapshot
        active=[False];seen=[]
        def wrapped(*,guard,callback):
            def locked(history):
                active[0]=True
                try:return callback(history)
                finally:active[0]=False
            return original(guard=guard,callback=locked)
        sink=self.f.service._sink
        def observed(pin):seen.append(active[0]);return sink(pin)
        with mock.patch.object(self.f.service._reader,'with_snapshot',side_effect=wrapped),mock.patch.object(self.f.service,'_sink',side_effect=observed):self.f.commit(self.f.request())
        self.assertTrue(seen);self.assertTrue(all(seen))

    def test_reader_final_guard_rejects_expiry_after_callback(self):
        token=self.r.token('operator')
        def operation(context):
            guard=self.r.service._guard(context,self.r.trust.revision)
            def callback(history):self.r.now=1240;return history
            return self.f.reader.with_snapshot(guard=guard,callback=callback)
        with self.assertRaises(PermissionDenied):self.r.identity._with_fixture_job_authorization(token,'case-a','job:run',operation)

    def test_checkpoint_files_are_immutable_and_preserve_expected_floor(self):
        before=self.f.sink.floor;self.f.commit(self.f.request())
        self.assertEqual((self.f.sink.root/(str(before['revision'])+'.json')).read_bytes(),
                         __import__('model_release_assurance.production_witness.contracts',fromlist=['canonical_bytes']).canonical_bytes(before))
        with self.assertRaises(ValueError):self.f.sink(before)
        latest=self.f.sink.floor;target=self.f.sink.root/(str(latest['revision'])+'.json');target.write_bytes(b'changed')
        with self.assertRaises(ValueError):self.f.sink(latest)

    def test_checkpoint_directory_replacement_is_rejected(self):
        sink=self.f.sink;floor=sink.floor
        moved=self.root/'old-checkpoints';sink.root.rename(moved);sink.root.mkdir()
        with self.assertRaises(ValueError):sink(floor)
        self.assertEqual(list(sink.root.iterdir()),[])

    def test_checkpoint_file_substitution_during_open_is_rejected(self):
        import os
        sink=self.f.sink;floor=sink.floor;target=sink.root/(str(floor['revision'])+'.json')
        replacement=self.root/'replacement.json';replacement.write_bytes(target.read_bytes())
        original=os.open
        def replace_file(path,*args,**kwargs):
            if Path(path)==target:os.replace(replacement,target)
            return original(path,*args,**kwargs)
        with mock.patch('model_release_assurance.production_witness.rehearsal.os.open',side_effect=replace_file):
            with self.assertRaises(ValueError):sink(floor)

if __name__=='__main__':unittest.main()
