"""Historical handoff integrity misuse tests over one fresh real native fixture."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from model_release_assurance.production_assessment import contracts as c, packet
from model_release_assurance.production_assessment.probes import run_probes, probe_plan


class PacketTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workspace = tempfile.TemporaryDirectory()
        cls.template = Path(cls.workspace.name) / "template"
        cls.template.mkdir()
        observed = run_probes(cls.template / "fixture", profile="local_public_fixture")
        if observed["status"] != "passed":
            raise AssertionError("Real public fixture probes failed")
        for name, value in (("assessment-plan.json", probe_plan()),
                            ("assessment-observations.json", observed),
                            ("assessment-findings.json", c.finding_catalog())):
            (cls.template / name).write_bytes(c.canonical_bytes(value))

    @classmethod
    def tearDownClass(cls):
        cls.workspace.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "packet"
        shutil.copytree(self.template, self.root)

    def seal(self):
        return packet.seal_packet(self.root, profile="local_public_fixture")

    def verify(self, pins):
        return packet.verify_packet(self.root, expected_manifest_sha256=pins["manifest_sha256"],
                                    expected_key_sha256=pins["key_sha256"])

    def test_real_fixture_exact_historical_packet(self):
        pins = self.seal()
        result = self.verify(pins)
        self.assertEqual(result["status"], "historical_packet_verified")
        self.assertGreater(result["file_count"], 10)
        for name, flag in c.FLAGS.items():
            self.assertIs(result[name], flag)
        self.assertIs(result["current_authorization_checked"], False)
        self.assertIs(result["probe_execution_reconstructed"], False)

    def test_production_refused_before_key_or_manifest(self):
        with self.assertRaises(c.AssessmentError):
            packet.seal_packet(self.root)
        self.assertFalse((self.root / "manifest.json").exists())
        self.assertFalse((self.root / "public-key.json").exists())

    def test_existing_packet_never_overwritten(self):
        pins = self.seal()
        old = (self.root / "manifest.json").read_bytes()
        with self.assertRaises(c.AssessmentError):
            self.seal()
        self.assertEqual((self.root / "manifest.json").read_bytes(), old)
        self.verify(pins)

    def test_external_pins_required(self):
        self.seal()
        with self.assertRaises(TypeError):
            packet.verify_packet(self.root)

    def test_wrong_manifest_pin(self):
        pins = self.seal(); pins["manifest_sha256"] = "0"*64
        with self.assertRaises(c.AssessmentError):
            self.verify(pins)

    def test_wrong_key_pin(self):
        pins = self.seal(); pins["key_sha256"] = "0"*64
        with self.assertRaises(c.AssessmentError):
            self.verify(pins)

    def test_embedded_key_does_not_bootstrap_trust(self):
        pins = self.seal()
        key = (self.root / "public-key.json").read_bytes()
        (self.root / "public-key.json").write_bytes(key + b" ")
        with self.assertRaises(c.AssessmentError):
            self.verify(pins)

    def test_signature_change_with_restamped_manifest_pin(self):
        pins = self.seal()
        value = json.loads((self.root / "manifest.json").read_bytes())
        value["signature_hex"] = "00"*64
        raw = packet._canonical(value)
        (self.root / "manifest.json").write_bytes(raw)
        pins["manifest_sha256"] = hashlib.sha256(raw).hexdigest()
        with self.assertRaises(c.AssessmentError):
            self.verify(pins)

    def test_duplicate_manifest_keys_rejected(self):
        pins = self.seal()
        raw = b'{"payload":{},"payload":{},"signature_hex":"' + b"0"*128 + b'"}'
        (self.root / "manifest.json").write_bytes(raw)
        pins["manifest_sha256"] = hashlib.sha256(raw).hexdigest()
        with self.assertRaises(c.AssessmentError):
            self.verify(pins)

    def test_fixed_catalog_boolean_alias_rejected_at_seal(self):
        value = c.finding_catalog(); value["can_clear"] = 0
        (self.root / "assessment-findings.json").write_bytes(packet._canonical(value))
        with self.assertRaises(c.AssessmentError):
            self.seal()

    def test_fixed_plan_boolean_alias_rejected_at_seal(self):
        value = probe_plan()
        def change(item):
            if type(item) is dict:
                for key, child in item.items():
                    if type(child) is int and child in (0, 1):
                        item[key] = bool(child); return True
                    if change(child): return True
            elif type(item) is list:
                for child in item:
                    if change(child): return True
            return False
        self.assertTrue(change(value), "Frozen plan should specify integer clock advance/count")
        (self.root / "assessment-plan.json").write_bytes(packet._canonical(value))
        with self.assertRaises(c.AssessmentError):
            self.seal()

    def test_raw_fixture_bytes_are_bound(self):
        pins = self.seal()
        p = self.root / "fixture/plan.json"
        p.write_bytes(p.read_bytes() + b" ")
        with self.assertRaises(c.AssessmentError):
            self.verify(pins)

    def test_extra_file_refused(self):
        pins = self.seal()
        (self.root / "unexpected.json").write_bytes(b"{}")
        with self.assertRaises(c.AssessmentError):
            self.verify(pins)

    def test_extra_nested_file_refused(self):
        pins = self.seal()
        (self.root / "fixture/extra.json").write_bytes(b"{}")
        with self.assertRaises(c.AssessmentError):
            self.verify(pins)

    def test_missing_bound_file_refused(self):
        pins = self.seal()
        (self.root / "fixture/plan.json").unlink()
        with self.assertRaises(c.AssessmentError):
            self.verify(pins)

    def test_hard_link_refused(self):
        pins = self.seal()
        original = self.root / "fixture/plan.json"
        os.link(original, Path(self.tmp.name) / "linked.json")
        with self.assertRaises(c.AssessmentError):
            self.verify(pins)

    def test_file_replacement_during_replay_even_with_same_bytes(self):
        pins = self.seal()
        original_capture = packet._capture
        target = self.root / "fixture/plan.json"
        calls = 0
        def capture(*args, **kwargs):
            nonlocal calls
            value = original_capture(*args, **kwargs)
            calls += 1
            if calls == 1:
                new = Path(self.tmp.name) / "replacement.json"
                new.write_bytes(target.read_bytes())
                os.replace(new, target)
            return value
        with patch.object(packet, "_capture", side_effect=capture), self.assertRaises(c.AssessmentError):
            self.verify(pins)

    def test_changed_validator_source_binding_refused(self):
        pins = self.seal()
        with patch.object(packet, "implementation_sha256", return_value="0"*64), self.assertRaises(c.AssessmentError):
            self.verify(pins)

    def test_different_runtime_refused(self):
        pins = self.seal()
        with patch.object(packet, "runtime_observation", return_value={"python": "different"}), self.assertRaises(c.AssessmentError):
            self.verify(pins)

    def test_total_evidence_bytes_bounded(self):
        with patch.object(packet, "MAX_TOTAL_BYTES", 1), self.assertRaises(c.AssessmentError):
            self.seal()

    def test_errors_do_not_expose_paths_or_payloads(self):
        pins = self.seal()
        (self.root / "fixture/private-token-canary").write_bytes(b"JWT-PHI-CANARY")
        with self.assertRaises(c.AssessmentError) as caught:
            self.verify(pins)
        self.assertNotIn("CANARY", str(caught.exception))
        self.assertNotIn(str(self.root), str(caught.exception))


if __name__ == "__main__":
    unittest.main()
