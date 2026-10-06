"""Worker binding, fixed transport and pre-import D cache routing boundaries."""
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
from model_release_assurance.production_pyrit import protocol as p, worker as w, upstream as u
from model_release_assurance.production_pyrit.runtime import LOCKED_VERSIONS, expected_binding, PyritRuntimeUnavailable
from test_production_pyrit_protocol import fixture_plan, fixture_campaign, fixture_cache_binding, fixture_response
SOURCE={"fixture.py": "0"*64}


def request(mode="prepare", plan=None):
    return {"schema": "mra-pyrit-worker-request/v1", "mode": mode, "versions": dict(LOCKED_VERSIONS),
        "source_sha256": p.sha(SOURCE), "lock_sha256": "b"*64, "model": dict(p.MODEL), "plan": plan}


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.plan=fixture_plan(source_sha256=p.sha(SOURCE)); self.binding=expected_binding()
        for name, target, value in (("source", "source_snapshot", copy.deepcopy(SOURCE)), ("runtime", "probe_runtime", copy.deepcopy(self.binding))):
            obj=patch.object(w,target,return_value=value); setattr(self,name,obj.start()); self.addCleanup(obj.stop)
        obj=patch.object(u,"build_identifiers",return_value=copy.deepcopy(self.plan["identifiers"]))
        self.identifiers=obj.start();self.addCleanup(obj.stop)
        obj=patch.object(u,"check_paths",return_value=fixture_cache_binding()); obj.start();self.addCleanup(obj.stop)

    def test_prepare_has_no_target_or_attacker_execution(self):
        with patch.object(u,"LoopbackClient") as client, patch.object(u,"run_campaign") as attack:
            output=w.prepare_request(request())
        client.assert_not_called();attack.assert_not_called()
        self.assertEqual(output["target_calls"],0);self.assertEqual(output["status"],"prepared")
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


class LoopbackTests(unittest.TestCase):
    def test_fixed_paths_and_no_redirect(self):
        client=u.LoopbackClient()
        with patch.object(client.opener,"open") as call,self.assertRaises(ValueError):client._request("https://example.invalid")
        call.assert_not_called()
        with self.assertRaises(ValueError):u.NoRedirect().redirect_request(None,None,None,None,None,None)

    def test_fixed_model_options_and_call_budget(self):
        client=u.LoopbackClient()
        with patch.object(client,"_request",return_value=fixture_response()) as call:
            for _ in range(6): client.chat([{"role":"user","content":"Fixed public text"}])
            with self.assertRaises(ValueError):client.chat([{"role":"user","content":"Fixed public text"}])
        self.assertEqual(call.call_count,6);self.assertEqual(call.call_args.args[1]["options"],p.OPTIONS)
        self.assertEqual(call.call_args.args[1]["model"],p.MODEL_NAME)

    def test_transport_strict_json_and_byte_bounds(self):
        for raw in (b'{"a":1,"a":2}',b'x'*(p.MAX_PROVIDER_BYTES+1)):
            response=io.BytesIO(raw);response.headers={"Content-Type":"application/json"};client=u.LoopbackClient()
            with patch.object(client.opener,"open",return_value=response),self.assertRaises(ValueError):client._request("/api/tags")

    def test_inventory_must_bind_one_exact_digest(self):
        for data in ({"models":[]},{"models":[{"name":p.MODEL_NAME,"digest":"c"*64}]},
                {"models":[{"name":p.MODEL_NAME,"digest":p.MODEL_DIGEST}]*2}):
            client=u.LoopbackClient()
            with patch.object(client,"_request",return_value=data),self.assertRaises(ValueError):client.inventory()

    def test_deadline_and_history_bounds(self):
        client=u.LoopbackClient();client.deadline=0
        with patch.object(client.opener,"open") as call,self.assertRaises(TimeoutError):client._request("/api/tags")
        call.assert_not_called()
        for messages in ([{"role":"user","content":"x"}]*8,[{"role":"user","content":"x"*65537}]):
            client=u.LoopbackClient()
            with patch.object(client,"_request") as call,self.assertRaises(ValueError):client.chat(messages)
            call.assert_not_called()


class StorageHookTests(unittest.TestCase):
    def setUp(self):
        obj=patch.object(u,"_PATH_BINDING",None);obj.start();self.addCleanup(obj.stop)
        obj=patch.object(u,"_COMPONENTS",None);obj.start();self.addCleanup(obj.stop)

    def test_preloaded_pyrit_path_is_refused_before_any_import(self):
        with patch.dict(sys.modules,{"pyrit.common.path":SimpleNamespace()}),patch.object(u.importlib.util,"find_spec") as find:
            with self.assertRaises(ValueError):u._install_storage_hook()
        find.assert_not_called()

    def test_only_declared_appdirs_calls_and_owned_empty_log(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).absolute();fake=SimpleNamespace(user_data_dir=Mock())
            env={name:str(root) for name in ("HOME","USERPROFILE","APPDATA","LOCALAPPDATA","XDG_CONFIG_HOME","XDG_DATA_HOME","XDG_CACHE_HOME")}
            env.update(RETRY_MAX_NUM_ATTEMPTS="1",CUSTOM_RESULT_RETRY_MAX_NUM_ATTEMPTS="1")
            spec=SimpleNamespace(origin=str(root/"site/pyrit/__init__.py"))
            with patch.dict(os.environ,env),patch.dict(sys.modules,{"appdirs":fake}),patch.object(u.importlib.util,"find_spec",return_value=spec),patch.object(Path,"home",return_value=root):
                binding=u._install_storage_hook()
                self.assertEqual(fake.user_data_dir("dbdata","pyrit"),str(root/"pyrit/dbdata"))
                self.assertEqual(fake.user_data_dir(".pyrit_cache","pyrit"),str(root/"pyrit/.pyrit_cache"))
                for args in (("other","pyrit"),("dbdata","other"),("dbdata","pyrit","v1"),("dbdata","pyrit",None,True)):
                    with self.subTest(args=args),self.assertRaises(ValueError):fake.user_data_dir(*args)
                (root/"pyrit/dbdata").mkdir(parents=True);(root/"pyrit/.pyrit_cache").mkdir();(root/"pyrit/dbdata/logs.txt").touch()
                module=SimpleNamespace(DB_DATA_PATH=root/"pyrit/dbdata",PYRIT_CACHE_PATH=root/"pyrit/.pyrit_cache",LOG_PATH=root/"pyrit/dbdata/logs.txt")
                with patch.dict(sys.modules,{"pyrit.common.path":module}):self.assertEqual(u.check_paths(),binding)
                module.LOG_PATH=root/"wrong.txt"
                with patch.dict(sys.modules,{"pyrit.common.path":module}),self.assertRaises(ValueError):u.check_paths()

    def test_runtime_repository_marker_rejected_before_pyrit_import(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).absolute();(root/"site").mkdir();(root/"site/.git").touch()
            env={name:str(root) for name in ("HOME","USERPROFILE","APPDATA","LOCALAPPDATA","XDG_CONFIG_HOME","XDG_DATA_HOME","XDG_CACHE_HOME")}
            env.update(RETRY_MAX_NUM_ATTEMPTS="1",CUSTOM_RESULT_RETRY_MAX_NUM_ATTEMPTS="1")
            with patch.dict(os.environ,env),patch.object(u.importlib.util,"find_spec",return_value=SimpleNamespace(origin=str(root/"site/pyrit/__init__.py"))),patch.object(Path,"home",return_value=root),self.assertRaises(ValueError):u._install_storage_hook()


if __name__=="__main__":unittest.main()
