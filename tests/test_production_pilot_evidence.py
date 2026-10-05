"""Exact manifest-owned buffer and historical-capability misuse checks."""
import copy
import hashlib
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
from model_release_assurance.production_assessment import rehearsal as assessment
from model_release_assurance.production_assessment import packet
from model_release_assurance.production_pilot import contracts as c, evidence


class EvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        result = assessment.exercise(cls.root / "assessment", profile="local_public_fixture")
        if result["status"] != "passed":
            raise AssertionError(result["errors"])
        cls.template = cls.root / "assessment/packet"
        cls.pins = result["pins"]

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "packet"
        shutil.copytree(self.template, self.path)

    def capability(self):
        return evidence.VerifiedAssessment(self.path,
            expected_manifest_sha256=self.pins["manifest_sha256"],
            expected_key_sha256=self.pins["key_sha256"], profile="local_public_fixture")

    def test_actual_fresh_candidate_and_scope_bound(self):
        cap = self.capability()
        snapshot = cap.recheck()
        raw = (self.path / "fixture/fixture/training/native/candidate.json").read_bytes()
        self.assertEqual(snapshot["candidate_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(snapshot["case_id"], "case-a")
        self.assertEqual(snapshot["profile_id"], "sklearn-wine")
        self.assertIs(snapshot["current_authorization_checked"], False)
        self.assertIs(snapshot["pilot_admission"], False)

    def test_production_refused_before_inspecting_path(self):
        with self.assertRaises(c.PilotError):
            evidence.VerifiedAssessment(object(), expected_manifest_sha256=object(), expected_key_sha256=object())

    def test_wrong_external_pins_refused(self):
        with self.assertRaises(c.PilotError):
            evidence.VerifiedAssessment(self.path, expected_manifest_sha256="0"*64,
                expected_key_sha256=self.pins["key_sha256"], profile="local_public_fixture")

    def test_dictionary_or_duck_type_cannot_be_capability(self):
        for value in ({}, object()):
            with self.assertRaises(c.PilotError): evidence.check_capability(value)

    def test_constructor_bypass_cannot_be_capability(self):
        with self.assertRaises(c.PilotError):
            evidence.check_capability(object.__new__(evidence.VerifiedAssessment))

    def test_snapshot_is_owned(self):
        cap = self.capability()
        snap = cap.snapshot(); snap["candidate_sha256"] = "0"*64; snap["production_blockers"].clear()
        self.assertNotEqual(cap.recheck()["candidate_sha256"], "0"*64)
        self.assertEqual(len(cap.snapshot()["production_blockers"]), 11)

    def test_bound_packet_tamper_invalidates_retained_capability(self):
        cap = self.capability()
        target = self.path / "fixture/plan.json"; target.write_bytes(target.read_bytes()+b" ")
        with self.assertRaises(c.PilotError): cap.recheck()

    def test_same_byte_manifest_replacement_cannot_rebind_capability(self):
        cap = self.capability()
        target = self.path / "manifest.json"
        replacement = Path(self.tmp.name) / "replacement.json"
        replacement.write_bytes(target.read_bytes())
        import os
        os.replace(replacement, target)
        with self.assertRaises(c.PilotError): cap.recheck()

    def test_changed_current_implementation_cannot_restamp_old_packet(self):
        with patch.object(packet, "implementation_sha256", return_value="0"*64), self.assertRaises(c.PilotError):
            self.capability()

    def substituted_read(self, filename, replacement):
        original = evidence.io.read_file
        verified = packet.verify_packet(self.path, expected_manifest_sha256=self.pins["manifest_sha256"],
                                        expected_key_sha256=self.pins["key_sha256"])
        def read(path, *args, **kwargs):
            if Path(path).as_posix().endswith(filename):
                return replacement
            return original(path, *args, **kwargs)
        with patch.object(packet, "verify_packet", return_value=verified), patch.object(
                evidence.io, "read_file", side_effect=read), self.assertRaises(c.PilotError):
            self.capability()

    def test_transient_observation_buffer_substitution_refused(self):
        raw = (self.path / "assessment-observations.json").read_bytes()
        value = packet._json(raw)
        value["evidence_hashes"]["candidate_sha256"] = "0"*64
        self.substituted_read("/assessment-observations.json", c.canonical_bytes(value))

    def test_transient_candidate_buffer_substitution_refused(self):
        name = "/fixture/fixture/training/native/candidate.json"
        self.substituted_read(name, (self.path / name.lstrip("/")).read_bytes()+b" ")

    def test_transient_registration_buffer_substitution_refused(self):
        name = "/fixture/fixture/training/registration.json"
        from model_release_assurance.production_registration.contracts import native_json, native_bytes
        value = native_json((self.path / name.lstrip("/")).read_bytes())
        value["case_id"] = "case-b"
        self.substituted_read(name, native_bytes(value))

    def test_errors_do_not_expose_paths(self):
        (self.path / "public-key.json").write_bytes(b"JWT-PHI-CANARY")
        with self.assertRaises(c.PilotError) as caught: self.capability()
        self.assertNotIn("CANARY", str(caught.exception))
        self.assertNotIn(str(self.path), str(caught.exception))


if __name__ == "__main__":
    unittest.main()
