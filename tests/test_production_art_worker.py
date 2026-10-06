"""Worker trust-boundary tests; the sklearn reference never claims ART execution."""
from __future__ import annotations
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import warnings
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.exceptions import ConvergenceWarning
from model_release_assurance.production_adapters import native
from model_release_assurance.production_adapters.contracts import canonical_bytes
from model_release_assurance.production_art import protocol, worker, runtime
from model_release_assurance.production_evidence import replay
from model_release_assurance.production_registration.profiles import load_profile
from test_production_art_protocol import sklearn_repetitions

SOURCE = {"trusted_fixture.py": "a"*64}
SOURCE_SHA = hashlib.sha256(canonical_bytes(SOURCE)).hexdigest()


class ReferenceAttack:
    """Minimal independent learner reference used only for control-path tests."""
    def __init__(self):
        self.attack_model = LogisticRegression(C=1, solver="lbfgs", max_iter=500, random_state=20261006)
        self.scaler = StandardScaler()
        self.calls = []

    def fit(self, *, pred, y, test_pred, test_y):
        if np.any(y != 0) or np.any(test_y != 0):
            raise AssertionError("Extra target label signal")
        self.calls.append(("fit", len(pred), len(test_pred)))
        features = np.column_stack([np.concatenate([pred, test_pred]).astype(np.float32)[:,0],
                                    np.zeros(len(pred)+len(test_pred),dtype=np.float32)])
        labels = np.concatenate([np.ones(len(pred)), np.zeros(len(test_pred))])
        self.attack_model.fit(self.scaler.fit_transform(features), labels)

    def infer(self, x, *, pred, y, probabilities):
        if x is not None or np.any(y != 0) or probabilities is not True:
            raise AssertionError("Prediction endpoint or extra label signal")
        self.calls.append(("infer", len(pred)))
        features = np.column_stack([pred.astype(np.float32)[:,0], np.zeros(len(pred),dtype=np.float32)])
        return self.attack_model.predict_proba(self.scaler.transform(features))[:,[1]]


class ArtWorkerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workspace = tempfile.TemporaryDirectory(prefix="art-worker-fixture-")
        data = load_profile("sklearn-wine", max_rows=128)
        output = Path(cls.workspace.name) / "native"
        native.run_native(data["x"], data["y"], dataset_id=data["dataset_id"],source_sha256=data["source_sha256"],
            feature_names=data["feature_names"], task=data["task"], output=output)
        cls.prepared = protocol.prepare_input(replay.snapshot_native_bundle(output))
        cls.cases = {name: sklearn_repetitions(cls.prepared, name) for name in protocol.CASES}

    @classmethod
    def tearDownClass(cls):
        cls.workspace.cleanup()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="art-worker-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def request(self):
        return {"schema": "mra-art-worker-request/v1", "prepared": copy.deepcopy(self.prepared),
            "versions": dict(runtime.LOCKED_VERSIONS), "source_sha256": SOURCE_SHA,"lock_sha256": "b"*64}

    def dispatch(self, request=None):
        with mock.patch.object(worker, "source_snapshot", return_value=SOURCE), \
             mock.patch.object(worker, "probe_runtime", return_value=runtime.expected_binding()), \
             mock.patch.object(worker, "_run_case", side_effect=lambda prepared,name:copy.deepcopy(self.cases[name])):
            return worker.run_request(self.request() if request is None else request)

    def input_file(self, request=None):
        path = self.root / "request.json"
        raw = canonical_bytes(self.request() if request is None else request) + b"\n"
        path.write_bytes(raw)
        return path, hashlib.sha256(raw).hexdigest()

    def test_request_is_strict_and_prepared_is_owned(self):
        request = self.request()
        prepared = worker.validate_request(request)
        prepared["cases"]["target"]["loss_values"][0] = 99.
        self.assertNotEqual(prepared, request["prepared"])
        for change in ({"extra": 0}, {"schema": "other"}, {"source_sha256": "x"*64}, {"lock_sha256": "abc"}):
            altered = self.request(); altered.update(change)
            with self.assertRaises(ValueError):
                worker.validate_request(altered)

    def test_missing_or_changed_locked_roster_rejected(self):
        for versions in ({}, {**runtime.LOCKED_VERSIONS,"numpy":"other"}, {**runtime.LOCKED_VERSIONS,"extra":"1"}):
            request=self.request(); request["versions"]=versions
            with self.assertRaises(ValueError):
                worker.validate_request(request)

    def test_eligibility_flip_rejected_before_external_execution(self):
        request=self.request(); request["prepared"]["assessment_eligible"]=True
        with mock.patch.object(worker,"probe_runtime") as probe:
            with self.assertRaises(ValueError):worker.run_request(request)
            probe.assert_not_called()

    def test_source_binding_rejected_before_runtime_or_attack(self):
        request=self.request(); request["source_sha256"]="0"*64
        with mock.patch.object(worker,"source_snapshot",return_value=SOURCE),mock.patch.object(worker,"probe_runtime") as probe:
            with self.assertRaises(ValueError):worker.run_request(request)
            probe.assert_not_called()

    def test_explicit_missing_dependency_never_substitutes_a_native_attack(self):
        with mock.patch.object(worker,"source_snapshot",return_value=SOURCE), \
             mock.patch.object(worker,"probe_runtime",side_effect=runtime.ArtRuntimeUnavailable("missing")), \
             mock.patch.object(worker,"_run_case") as run:
            with self.assertRaises(runtime.ArtRuntimeUnavailable):worker.run_request(self.request())
            run.assert_not_called()

    def test_optional_art_is_not_imported_at_module_load(self):
        import builtins
        import importlib
        original=builtins.__import__
        def no_art(name,*args,**kwargs):
            if name=="art" or name.startswith("art."):
                raise AssertionError("Optional ART imported at worker module load")
            return original(name,*args,**kwargs)
        with mock.patch("builtins.__import__",side_effect=no_art):
            importlib.reload(worker)
        # Explicitly controlled missing roster, independent of incidental local
        # editable app metadata, demonstrates the unavailable path.
        with mock.patch.object(runtime.importlib.metadata,"distributions",return_value=[]):
            with self.assertRaises(runtime.ArtRuntimeUnavailable):
                runtime.probe_runtime(runtime.LOCKED_VERSIONS)

    def test_completed_worker_has_exact_non_authorizing_output(self):
        result=self.dispatch()
        self.assertEqual(set(result),{"schema","status","prepared_sha256","runtime","versions","source_sha256","lock_sha256","cases",*worker.WORKER_FLAGS})
        self.assertEqual(result["prepared_sha256"],hashlib.sha256(canonical_bytes(self.prepared)).hexdigest())
        self.assertEqual(set(result["cases"]),set(protocol.CASES))
        for name,expected in worker.WORKER_FLAGS.items():self.assertIs(result[name],expected)

    def test_both_source_and_runtime_rechecked_after_attack(self):
        for which in ("source","runtime"):
            with mock.patch.object(worker,"source_snapshot",side_effect=[SOURCE,{"changed":"c"*64}] if which=="source" else [SOURCE,SOURCE]), \
                 mock.patch.object(worker,"probe_runtime",side_effect=[runtime.expected_binding(),{}] if which=="runtime" else [runtime.expected_binding(),runtime.expected_binding()]), \
                 mock.patch.object(worker,"_run_case",side_effect=lambda prepared,name:copy.deepcopy(self.cases[name])):
                with self.assertRaises(ValueError):worker.run_request(self.request())

    def test_caller_mutation_cannot_restamp_worker_bindings(self):
        request=self.request()
        def mutate(prepared,name):
            request["lock_sha256"]="f"*64; request["source_sha256"]="f"*64; request["versions"]["numpy"]="other"
            request["prepared"]["cases"]["target"]["loss_values"][0]=999.
            return copy.deepcopy(self.cases[name])
        with mock.patch.object(worker,"source_snapshot",return_value=SOURCE), \
             mock.patch.object(worker,"probe_runtime",return_value=runtime.expected_binding()), \
             mock.patch.object(worker,"_run_case",side_effect=mutate):
            result=worker.run_request(request)
        self.assertEqual(result["lock_sha256"],"b"*64)
        self.assertEqual(result["source_sha256"],SOURCE_SHA)
        self.assertEqual(result["versions"],runtime.LOCKED_VERSIONS)
        self.assertEqual(result["prepared_sha256"],hashlib.sha256(canonical_bytes(self.prepared)).hexdigest())

    def test_reference_learner_uses_fixed_splits_and_zero_label_channel(self):
        attacks=[]
        def create():
            attack=ReferenceAttack();attacks.append(attack);return attack
        with mock.patch.object(worker,"_create_attack",side_effect=create):
            repetitions=worker._run_case(self.prepared,"target")
        self.assertEqual(len(attacks),3)
        self.assertEqual([row["seed"] for row in repetitions],list(protocol.SEEDS))
        for attack,split in zip(attacks,protocol.frozen_splits(self.prepared)):
            self.assertEqual(sum(attack.calls[0][1:]),len(split["train_indices"]))
            self.assertEqual(attack.calls[1],("infer",len(split["test_indices"])))
        protocol.compare_repetitions(self.prepared,"target",repetitions)

    def test_reference_balanced_null_zero_iterations_is_accepted(self):
        with mock.patch.object(worker,"_create_attack",side_effect=ReferenceAttack):
            repetitions=worker._run_case(self.prepared,"null")
        self.assertTrue(any(row["learned"]["n_iter"]==0 for row in repetitions))
        self.assertTrue(protocol.compare_repetitions(self.prepared,"null",repetitions)["controls_satisfied"])

    def test_convergence_warning_fails_closed(self):
        attack=ReferenceAttack()
        attack.fit=lambda **kwargs:warnings.warn("not converged",ConvergenceWarning)
        with mock.patch.object(worker,"_create_attack",return_value=attack):
            with self.assertRaises(ConvergenceWarning):worker._run_case(self.prepared,"target")

    def test_invalid_member_probability_output_is_rejected(self):
        for value in (float("nan"),2.):
            attack=ReferenceAttack()
            attack.infer=lambda x,**kwargs:np.full((len(kwargs["y"]),1),value)
            with mock.patch.object(worker,"_create_attack",return_value=attack):
                with self.assertRaises(ValueError):worker._run_case(self.prepared,"target")

    def test_main_requires_exact_arguments(self):
        self.assertEqual(worker.main([]),2)
        self.assertEqual(worker.main(["one","two"]),2)

    def test_main_binds_input_bytes_before_execution(self):
        path,digest=self.input_file()
        output=self.root/"out";output.mkdir()
        with mock.patch.object(worker,"run_request") as dispatch:
            self.assertEqual(worker.main([str(path),"f"*64,str(output)]),1)
            dispatch.assert_not_called()
        failure=json.loads((output/"failure.json").read_bytes())
        self.assertEqual(failure["status"],"failed")
        self.assertNotIn("error_message",failure)

    def test_main_rejects_duplicate_json_keys(self):
        path=self.root/"request.json";raw=b'{"schema":"a","schema":"b"}'
        path.write_bytes(raw);output=self.root/"out";output.mkdir()
        with mock.patch.object(worker,"run_request") as dispatch:
            self.assertEqual(worker.main([str(path),hashlib.sha256(raw).hexdigest(),str(output)]),1)
            dispatch.assert_not_called()

    def test_main_missing_dependency_is_explicit_exit_three(self):
        path,digest=self.input_file();output=self.root/"out";output.mkdir()
        with mock.patch.object(worker,"run_request",side_effect=runtime.ArtRuntimeUnavailable("missing")):
            self.assertEqual(worker.main([str(path),digest,str(output)]),3)
        result=json.loads((output/"failure.json").read_bytes())
        self.assertEqual(result["status"],"unavailable")
        self.assertFalse(result["assessment_eligible"])
        self.assertFalse((output/"worker.json").exists())

    def test_main_changed_runtime_is_failure_not_unavailable(self):
        path,digest=self.input_file();output=self.root/"out";output.mkdir()
        with mock.patch.object(worker,"run_request",side_effect=runtime.ArtRuntimeError("changed")):
            self.assertEqual(worker.main([str(path),digest,str(output)]),1)
        self.assertEqual(json.loads((output/"failure.json").read_bytes())["status"],"failed")

    def test_main_writes_bounded_canonical_owned_output(self):
        path,digest=self.input_file();output=self.root/"out";output.mkdir();result=self.dispatch()
        with mock.patch.object(worker,"run_request",return_value=result):
            self.assertEqual(worker.main([str(path),digest,str(output)]),0)
        self.assertEqual((output/"worker.json").read_bytes(),canonical_bytes(result)+b"\n")

    def test_main_cannot_overwrite_existing_worker_receipt(self):
        path,digest=self.input_file();output=self.root/"out";output.mkdir()
        prior=output/"worker.json";prior.write_bytes(b"preserved")
        with mock.patch.object(worker,"run_request",return_value=self.dispatch()):
            self.assertEqual(worker.main([str(path),digest,str(output)]),1)
        self.assertEqual(prior.read_bytes(),b"preserved")

    def test_main_rejects_oversized_output(self):
        path,digest=self.input_file();output=self.root/"out";output.mkdir()
        with mock.patch.object(worker,"run_request",return_value=self.dispatch()),mock.patch.object(worker,"MAX_OUTPUT",32):
            self.assertEqual(worker.main([str(path),digest,str(output)]),1)
        self.assertFalse((output/"worker.json").exists())

    def oracle(self):
        # Stub only the optional ART classes so the concrete oracle and fixed
        # constructor policy can be tested in the preserved no-ART runtime.
        import types
        class Base:
            def __init__(self,**kwargs):self.args=kwargs
        class Mixin:pass
        class Attack:
            def __init__(self,estimator,**kwargs):
                self.estimator=estimator;self.options=kwargs;self.default_model=True
                self.attack_model=LogisticRegression()
        modules={}
        for name in ("art","art.attacks","art.attacks.inference","art.attacks.inference.membership_inference",
                     "art.estimators","art.estimators.estimator","art.estimators.regression"):
            modules[name]=types.ModuleType(name)
        modules["art.attacks.inference.membership_inference"].MembershipInferenceBlackBox=Attack
        modules["art.estimators.estimator"].BaseEstimator=Base
        modules["art.estimators.regression"].RegressorMixin=Mixin
        with mock.patch.dict("sys.modules",modules):
            return worker._create_attack()

    def test_oracle_constructor_preserves_fixed_default_lr(self):
        attack=self.oracle()
        self.assertEqual(attack.options,{"input_type":"loss","attack_model_type":"lr","scaler_type":"standard"})
        for key in ("C","solver","max_iter","random_state"):
            self.assertEqual(attack.attack_model.get_params()[key],runtime.ATTACK_PARAMETERS[key])
        self.assertEqual(attack.estimator.__class__.__name__,"RetainedGroupLossRegressor")
        self.assertEqual(attack.estimator.input_shape,(1,))
        self.assertIsNone(attack.estimator.args["model"])

    def test_oracle_rejects_target_fit_prediction_and_feature_queries(self):
        oracle=self.oracle().estimator
        for method in (lambda:oracle.fit(np.zeros((2,1)),np.zeros(2)),
                       lambda:oracle.predict(np.zeros((2,1))),
                       lambda:oracle.compute_loss(np.zeros((2,1)),np.zeros(2))):
            with self.assertRaises(NotImplementedError):method()

    def test_oracle_returns_owned_loss_without_true_target_label_signal(self):
        oracle=self.oracle().estimator
        values=np.asarray([[.125],[3.]],dtype=np.float64)
        result=oracle.compute_loss_from_predictions(values,np.zeros(2,dtype=np.float32))
        self.assertTrue(np.array_equal(result,values[:,0]))
        result[0]=99.
        self.assertEqual(values[0,0],.125)
        with self.assertRaises(ValueError):oracle.compute_loss_from_predictions(values,np.asarray([0.,1.]))

    def test_oracle_rejects_invalid_shapes_dtypes_and_float_bounds(self):
        oracle=self.oracle().estimator
        for values,labels in ((np.zeros((2,2)),np.zeros(2)), (np.zeros(2),np.zeros(2)),
                              (np.asarray([[True],[False]]),np.zeros(2)),
                              (np.asarray([[1.],[2.]]),np.zeros((2,1))),
                              (np.asarray([[1.],[2.]]),np.asarray([False,False])),
                              (np.asarray([[1e40],[1.]]),np.zeros(2)),
                              (np.asarray([[float("nan")],[1.]]),np.zeros(2)),
                              (np.asarray([[-1.],[1.]]),np.zeros(2))):
            with self.assertRaises(ValueError):oracle.compute_loss_from_predictions(values,labels)

if __name__ == "__main__":
    unittest.main()
