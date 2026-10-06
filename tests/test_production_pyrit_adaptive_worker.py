"""Adaptive worker preparation, source/runtime ownership and terminal evidence boundaries."""
from __future__ import annotations
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from model_release_assurance.production_adapters.contracts import canonical_bytes
from model_release_assurance.production_pyrit_adaptive import protocol as p, worker as w, upstream as u
from model_release_assurance.production_pyrit_adaptive.runtime import LOCKED_VERSIONS, expected_binding, PyritRuntimeUnavailable
from test_production_pyrit_adaptive_protocol import fixture_plan, fixture_campaign, fixture_cache_binding, fixture_response, fixture_attacker_failure
SOURCE={"fixture.py": "0"*64}


def request(mode="prepare", plan=None):
    return {"schema": "mra-pyrit-adaptive-worker-request/v1", "mode": mode, "versions": dict(LOCKED_VERSIONS),
        "source_sha256": p.sha(SOURCE), "lock_sha256": "b"*64, "model": dict(p.MODEL), "plan": plan}


class AdaptiveWorkerTests(unittest.TestCase):
    def setUp(self):
        self.plan=fixture_plan(source_sha256=p.sha(SOURCE)); self.binding=expected_binding()
        for name, target, value in (("source", "source_snapshot", copy.deepcopy(SOURCE)), ("runtime", "probe_runtime", copy.deepcopy(self.binding))):
            obj=patch.object(w,target,return_value=value); setattr(self,name,obj.start()); self.addCleanup(obj.stop)
        obj=patch.object(u,"build_identifiers",return_value=copy.deepcopy(self.plan["identifiers"]))
        self.identifiers=obj.start();self.addCleanup(obj.stop)
        obj=patch.object(u,"response_schema",return_value=copy.deepcopy(p.RESPONSE_SCHEMA));obj.start();self.addCleanup(obj.stop)
        obj=patch.object(u,"check_paths",return_value=fixture_cache_binding()); obj.start();self.addCleanup(obj.stop)

    def test_prepare_has_no_target_or_attacker_execution(self):
        with patch.object(u,"AdaptiveLoopbackClient") as client, patch.object(u,"run_campaign") as attack:
            output=w.prepare_request(request())
        client.assert_not_called();attack.assert_not_called()
        for key,value in p.ROLE_FLAGS.items():self.assertIs(output[key],value)
        self.assertEqual(output["attacker_calls"],0);self.assertEqual(output["target_calls"],0);self.assertEqual(output["status"],"prepared")
        self.assertEqual(output["plan"],self.plan);self.assertEqual(self.runtime.call_count,2);self.assertEqual(self.source.call_count,2)

    def test_actual_identity_change_prevents_execution(self):
        self.identifiers.return_value[0]["objective_target"]["hash"]="f"*64
        with patch.object(u,"run_campaign") as attack, self.assertRaises(ValueError): w.run_request(request("run",self.plan))
        attack.assert_not_called()

    def test_run_keeps_history_and_unscoreable_evidence(self):
        campaign=fixture_campaign(self.plan,response=fixture_response(p.MARKER,done=False))
        with patch.object(u,"run_campaign",return_value=campaign): result=w.run_request(request("run",self.plan))
        self.assertEqual(result["status"],"incomplete");self.assertEqual(result["replay"]["unscoreable"],6)
        self.assertEqual(p.replay(self.plan,result)["observed_literal_hits"],6)
        self.assertFalse(result["can_clear"])

    def test_source_mismatch_prevents_optional_import(self):
        self.source.return_value={"changed.py":"0"*64}
        with self.assertRaises(ValueError): w.prepare_request(request())
        self.identifiers.assert_not_called()

    def test_post_phase_source_or_runtime_drift_rejected(self):
        for boundary in ("source", "runtime"):
            with self.subTest(boundary=boundary):
                self.source.side_effect=[SOURCE,{"changed":True}] if boundary=="source" else None
                self.runtime.side_effect=[self.binding,{"changed":True}] if boundary=="runtime" else None
                with self.assertRaises(ValueError): w.prepare_request(request())
                self.source.side_effect=None;self.runtime.side_effect=None

    def test_missing_runtime_is_explicit(self):
        self.runtime.side_effect=PyritRuntimeUnavailable("Missing component")
        with self.assertRaises(PyritRuntimeUnavailable): w.prepare_request(request())
        self.identifiers.assert_not_called()

    def test_fixed_request_and_plan_binding(self):
        for field in ("model", "versions", "extra", "mode", "prepare_plan"):
            value=request()
            if field=="model":value["model"]["digest"]="c"*64
            elif field=="versions":value["versions"]["pyrit"]="0.0.0"
            elif field=="extra":value["endpoint"]="https://example.invalid"
            elif field=="mode":value["mode"]="full_cli"
            else:value["plan"]=self.plan
            with self.subTest(field=field),self.assertRaises(ValueError):w.validate_request(value)
        for field in ("source_sha256", "lock_sha256"):
            value=request("run",self.plan);value[field]="c"*64
            with self.subTest(field=field),self.assertRaises(ValueError):w.validate_request(value)
        with self.assertRaises(ValueError):w.run_request(request())
        with self.assertRaises(ValueError):w.prepare_request(request("run",self.plan))

    def test_main_retains_incomplete_and_refuses_overwrite(self):
        campaign=fixture_campaign(self.plan,response=fixture_response(p.MARKER,done=False))
        with patch.object(u,"run_campaign",return_value=campaign),tempfile.TemporaryDirectory() as folder:
            root=Path(folder);raw=canonical_bytes(request("run",self.plan));file=root/"input.json";file.write_bytes(raw);output=root/"output";output.mkdir()
            args=[str(file),hashlib.sha256(raw).hexdigest(),str(output)]
            self.assertEqual(w.main(args),0);saved=json.loads((output/"worker.json").read_text())
            self.assertEqual(saved["status"],"incomplete");self.assertEqual(len(saved["campaign"]["runs"]),6)
            self.assertEqual(w.main(args),2)

    def test_main_missing_runtime_exit_three(self):
        self.runtime.side_effect=PyritRuntimeUnavailable("Missing component")
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);raw=canonical_bytes(request());file=root/"input.json";file.write_bytes(raw);output=root/"output";output.mkdir()
            self.assertEqual(w.main([str(file),hashlib.sha256(raw).hexdigest(),str(output)]),3)
            self.assertEqual(json.loads((output/"error.json").read_text())["status"],"unavailable")
            self.assertFalse((output/"worker.json").exists())

    def test_main_hash_and_duplicate_fields_rejected(self):
        for data, digest in [(canonical_bytes(request()),"0"*64),(b'{"mode":"prepare","mode":"run"}',None)]:
            with tempfile.TemporaryDirectory() as folder:
                root=Path(folder);file=root/"input.json";file.write_bytes(data);output=root/"output";output.mkdir()
                self.assertEqual(w.main([str(file),digest or hashlib.sha256(data).hexdigest(),str(output)]),2)
                self.assertFalse((output/"worker.json").exists())
        self.assertEqual(w.main([]),2)


    def test_terminal_attacker_evidence_persists_without_target_substitution(self):
        campaign=fixture_campaign(self.plan,attacker_response=fixture_attacker_failure())
        with patch.object(u,"run_campaign",return_value=campaign) as attack:
            result=w.run_request(request("run",self.plan))
        attack.assert_called_once_with(self.plan,client=None)
        self.assertEqual(result["status"],"incomplete")
        self.assertEqual(result["replay"]["target_turns"],0)
        self.assertEqual(result["replay"]["attacker_calls"],2)
        self.assertEqual(result["campaign"]["runs"][2]["result"]["upstream_result"]["executed_turns"],0)
        self.assertIs(result["independent_attacker_model"],False)

    def test_schema_drift_prevents_inference(self):
        with patch.object(u,"response_schema",return_value={"type":"string"}),patch.object(u,"run_campaign") as attack:
            with self.assertRaises(ValueError):w.run_request(request("run",self.plan))
        attack.assert_not_called()

    def test_post_run_drift_cannot_return_logical_completion(self):
        campaign=fixture_campaign(self.plan)
        self.source.side_effect=[SOURCE,{"changed.py":"0"*64}]
        with patch.object(u,"run_campaign",return_value=campaign),self.assertRaises(ValueError):w.run_request(request("run",self.plan))

    def test_main_terminal_incomplete_zero_target_receipt_is_retained(self):
        campaign=fixture_campaign(self.plan,attacker_response=fixture_attacker_failure())
        with patch.object(u,"run_campaign",return_value=campaign),tempfile.TemporaryDirectory() as folder:
            root=Path(folder);raw=canonical_bytes(request("run",self.plan));file=root/"input.json";file.write_bytes(raw);output=root/"output";output.mkdir()
            self.assertEqual(w.main([str(file),hashlib.sha256(raw).hexdigest(),str(output)]),0)
            saved=json.loads((output/"worker.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["replay"]["attacker_failures"],2);self.assertEqual(saved["replay"]["target_turns"],0)
            self.assertFalse((output/"error.json").exists())


if __name__=="__main__":unittest.main()
