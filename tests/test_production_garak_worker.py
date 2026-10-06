"""Owned-request, dependency drift and bounded loopback transport checks."""
import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from model_release_assurance.production_adapters.contracts import canonical_bytes
from model_release_assurance.production_garak import protocol as p, worker as w, upstream as u
from model_release_assurance.production_garak.runtime import LOCKED_VERSIONS, expected_binding, GarakRuntimeUnavailable
from test_production_garak_protocol import SOURCE, fixture_corpus, fixture_plan, fixture_campaign, response


def request(mode="prepare", plan=None):
    return {"schema": "mra-garak-worker-request/v1", "mode": mode, "versions": dict(LOCKED_VERSIONS),
            "source_sha256": p.sha(SOURCE), "lock_sha256": "b" * 64, "model": dict(p.MODEL), "plan": plan}


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.binding = expected_binding()
        self.source_patch = patch.object(w, "source_snapshot", return_value=copy.deepcopy(SOURCE))
        self.runtime_patch = patch.object(w, "probe_runtime", return_value=copy.deepcopy(self.binding))
        self.corpus_patch = patch.object(w.upstream, "build_corpus", return_value=fixture_corpus())
        self.source = self.source_patch.start(); self.runtime = self.runtime_patch.start(); self.corpus = self.corpus_patch.start()
        self.addCleanup(self.source_patch.stop); self.addCleanup(self.runtime_patch.stop); self.addCleanup(self.corpus_patch.stop)

    def test_prepare_freezes_real_corpus_without_target_calls(self):
        with patch.object(u, "LoopbackClient") as client:
            result = w.prepare_request(request())
        client.assert_not_called()
        self.assertEqual(result["target_calls"], 0)
        self.assertEqual(result["status"], "prepared")
        self.assertEqual(result["plan"]["corpus_sha256"], p.CORPUS_SHA256)
        self.assertEqual(self.runtime.call_count, 2)
        self.assertEqual(self.source.call_count, 2)

    def test_run_retains_and_replays_fixed_campaign(self):
        plan = fixture_plan(); campaign = fixture_campaign(plan)
        with patch.object(u, "run_campaign", return_value=campaign) as execute:
            output = w.run_request(request("run", plan))
        execute.assert_called_once()
        self.assertEqual(output["status"], "completed")
        self.assertEqual(p.replay(plan, output)["scored"], 12)
        self.assertFalse(output["authorization_eligible"])

    def test_run_logically_incomplete_keeps_result(self):
        plan = fixture_plan(); campaign = fixture_campaign(plan)
        campaign["inventory"]["after"] = {"error": "ValueError"}
        with patch.object(u, "run_campaign", return_value=campaign):
            result = w.run_request(request("run", plan))
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(len(result["campaign"]["attacks"]), 12)

    def test_source_mismatch_prevents_optional_execution(self):
        self.source.return_value = {"changed.py": "0" * 64}
        with self.assertRaises(ValueError): w.prepare_request(request())
        self.corpus.assert_not_called()

    def test_source_drift_during_prepare_rejected(self):
        self.source.side_effect = [SOURCE, {"changed.py": "0" * 64}]
        with self.assertRaises(ValueError): w.prepare_request(request())

    def test_runtime_drift_during_prepare_rejected(self):
        self.runtime.side_effect = [self.binding, {"changed": True}]
        with self.assertRaises(ValueError): w.prepare_request(request())

    def test_initial_runtime_binding_mismatch_rejected(self):
        self.runtime.return_value = {"changed": True}
        with self.assertRaises(ValueError): w.prepare_request(request())
        self.corpus.assert_not_called()

    def test_missing_runtime_remains_explicit(self):
        self.runtime.side_effect = GarakRuntimeUnavailable("Missing component dependency")
        with self.assertRaises(GarakRuntimeUnavailable): w.prepare_request(request())
        self.corpus.assert_not_called()

    def test_actual_corpus_change_invalidates_frozen_plan(self):
        self.corpus.return_value[0]["prompt"] += "changed"
        with patch.object(u, "run_campaign") as execute, self.assertRaises(ValueError):
            w.run_request(request("run", fixture_plan()))
        execute.assert_not_called()

    def test_request_has_exact_model_and_versions(self):
        for change in ("model", "versions", "extra", "mode", "prepare_plan"):
            value = request()
            if change == "model": value["model"]["digest"] = "c" * 64
            elif change == "versions": value["versions"]["garak"] = "0.16.0"
            elif change == "extra": value["endpoint"] = "https://example.invalid"
            elif change == "mode": value["mode"] = "full_cli"
            else: value["plan"] = fixture_plan()
            with self.subTest(change=change), self.assertRaises(ValueError): w.validate_request(value)

    def test_run_plan_binding_mismatch_rejected(self):
        for field in ("source_sha256", "lock_sha256"):
            value = request("run", fixture_plan()); value[field] = "c" * 64
            with self.subTest(field=field), self.assertRaises(ValueError): w.validate_request(value)

    def test_mode_specific_entrypoints_reject_other_mode(self):
        with self.assertRaises(ValueError): w.run_request(request())
        with self.assertRaises(ValueError): w.prepare_request(request("run", fixture_plan()))

    def test_main_valid_prepare_exclusive_worker_file(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); data = canonical_bytes(request()); path = root / "input.json"; path.write_bytes(data)
            output = root / "output"; output.mkdir()
            self.assertEqual(w.main([str(path), hashlib.sha256(data).hexdigest(), str(output)]), 0)
            saved = json.loads((output / "worker.json").read_text())
            self.assertEqual(saved["target_calls"], 0)
            self.assertEqual(w.main([str(path), hashlib.sha256(data).hexdigest(), str(output)]), 2)

    def test_main_missing_runtime_exit_three_and_error(self):
        self.runtime.side_effect = GarakRuntimeUnavailable("Missing component dependency")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); data = canonical_bytes(request()); path = root / "input.json"; path.write_bytes(data)
            output = root / "output"; output.mkdir()
            self.assertEqual(w.main([str(path), hashlib.sha256(data).hexdigest(), str(output)]), 3)
            error = json.loads((output / "error.json").read_text())
            self.assertEqual(error["status"], "unavailable")
            self.assertFalse(error["authorization_eligible"])
            self.assertFalse((output / "worker.json").exists())

    def test_main_hash_and_duplicate_json_rejected(self):
        for data, digest in [(canonical_bytes(request()), "0" * 64), (b'{"mode":"prepare","mode":"run"}', None)]:
            with tempfile.TemporaryDirectory() as folder:
                root = Path(folder); path = root / "input.json"; path.write_bytes(data); output = root / "output"; output.mkdir()
                self.assertEqual(w.main([str(path), digest or hashlib.sha256(data).hexdigest(), str(output)]), 2)
                self.assertFalse((output / "worker.json").exists())

    def test_main_valid_incomplete_returns_zero_with_retained_evidence(self):
        plan = fixture_plan(); campaign = fixture_campaign(plan); campaign["inventory"]["after"] = {"error": "ValueError"}
        with patch.object(u, "run_campaign", return_value=campaign), tempfile.TemporaryDirectory() as folder:
            root = Path(folder); data = canonical_bytes(request("run", plan)); path = root / "input.json"; path.write_bytes(data)
            output = root / "output"; output.mkdir()
            self.assertEqual(w.main([str(path), hashlib.sha256(data).hexdigest(), str(output)]), 0)
            self.assertEqual(json.loads((output / "worker.json").read_text())["status"], "incomplete")

    def test_bad_cli_arity(self):
        self.assertEqual(w.main([]), 2)


class LoopbackTests(unittest.TestCase):
    def test_redirect_rejected(self):
        with self.assertRaises(ValueError): u.NoRedirect().redirect_request(None, None, None, None, None, None)

    def test_only_two_paths(self):
        client = u.LoopbackClient()
        with patch.object(client.opener, "open") as call, self.assertRaises(ValueError): client._request("https://example.invalid")
        call.assert_not_called()

    def test_query_limit_and_fixed_model_options(self):
        client = u.LoopbackClient()
        with patch.object(client, "_request", return_value=response("ok")) as call:
            for _ in range(18): client.chat([{"role": "user", "content": "Fixed text"}])
            with self.assertRaises(ValueError): client.chat([{"role": "user", "content": "Fixed text"}])
        self.assertEqual(call.call_count, 18)
        payload = call.call_args.args[1]
        self.assertEqual(payload["model"], p.MODEL_NAME)
        self.assertEqual(payload["options"], p.OPTIONS)
        self.assertNotIn("tools", payload)

    def test_elapsed_campaign_prevents_request(self):
        client = u.LoopbackClient(); client.deadline = 0
        with patch.object(client.opener, "open") as call, self.assertRaises(TimeoutError): client._request("/api/tags")
        call.assert_not_called()

    def test_duplicate_or_changed_inventory_rejected(self):
        for models in ([dict(p.MODEL), dict(p.MODEL)], [{"name": p.MODEL_NAME, "digest": "c" * 64}], []):
            client = u.LoopbackClient()
            with patch.object(client, "_request", return_value={"models": models}), self.assertRaises(ValueError): client.inventory()

    def test_matching_inventory_no_inference(self):
        client = u.LoopbackClient()
        with patch.object(client, "_request", return_value={"models": [dict(p.MODEL)]}) as call:
            self.assertEqual(client.inventory(), p.MODEL)
        self.assertEqual(call.call_args.args, ("/api/tags",))
        self.assertEqual(client.target_calls, 0)

    def test_invalid_content_type_response_bound_and_duplicate_json(self):
        for kind in ("type", "size", "duplicate"):
            client = u.LoopbackClient()
            raw = b'{}' if kind == "type" else b'x' * (p.MAX_PROVIDER_BYTES + 1) if kind == "size" else b'{"x":1,"x":2}'
            opened = Mock(); opened.__enter__ = Mock(return_value=opened); opened.__exit__ = Mock(return_value=False)
            opened.read.return_value = raw
            opened.headers = {"Content-Type": "text/html" if kind == "type" else "application/json"}
            with patch.object(client.opener, "open", return_value=opened), self.subTest(kind=kind), self.assertRaises(ValueError):
                client._request("/api/tags")
            opened.read.assert_called_once_with(p.MAX_PROVIDER_BYTES + 1)


if __name__ == "__main__":
    unittest.main()
