"""End-to-end pilot-plan lifecycle with a fresh matching historical assessment."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from model_release_assurance.production_pilot import contracts as c,rehearsal


class RehearsalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.root=Path(cls.temp.name)
        cls.result=rehearsal.exercise(cls.root/"actual",profile="local_public_fixture")
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def test_complete_real_fresh_assessment_and_seven_signed_people(self):
        self.assertEqual(self.result["status"],"passed",self.result.get("errors"))
        self.assertEqual({r["name"] for r in self.result["checks"]},rehearsal.REQUIRED_CHECKS)
        self.assertTrue(all(r["passed"] is True for r in self.result["checks"]))
        self.assertEqual(self.result["summary"],rehearsal.EXPECTED_SUMMARY)
    def test_no_agency_pilot_or_queries_or_delivery(self):
        for key in ("model_queries","pilot_delivered_bytes"):self.assertEqual(self.result["summary"][key],0)
        self.assertIs(self.result["summary"]["agency_pilot_started"],False)
        self.assertIs(self.result["pilot_admission"],False)
    def test_historical_records_never_restore_permissions(self):
        self.assertIs(self.result["serialized_plan_restored"],False)
        self.assertIs(self.result["summary"]["expired_roster_unusable"],True)
        self.assertIs(self.result["summary"]["withdrawal_terminal"],True)
    def test_all_production_findings_remain_open(self):
        self.assertEqual(len(self.result["evidence"]["production_blockers"]),11)
        self.assertEqual(self.result["summary"]["production_blockers_open"],11)
        for key,value in c.FLAGS.items():self.assertIs(self.result[key],value)
    def test_packet_pins_exact(self):
        self.assertEqual(self.result["pins"]["manifest_sha256"],self.result["evidence"]["assessment_manifest_sha256"])
        self.assertEqual(self.result["pins"]["key_sha256"],self.result["evidence"]["assessment_key_sha256"])
    def test_default_production_refusal_before_output(self):
        target=self.root/"denied"
        with self.assertRaises(c.PilotError):rehearsal.exercise(target)
        self.assertFalse(target.exists())
    def test_failed_assessment_keeps_intent_and_generic_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/"failed"
            with patch.object(rehearsal,"assess",side_effect=RuntimeError("PRIVATE-JWT-CANARY")):
                result=rehearsal.exercise(target,profile="local_public_fixture")
            self.assertEqual(result["status"],"failed")
            self.assertEqual(result["errors"],[{"stage":"fresh_assessment","code":"LocalPilotStageFailed"}])
            self.assertNotIn("CANARY",str(result))
            self.assertTrue((target/"pilot-intent.json").exists())
            self.assertTrue((target/"exercise-result.json").exists())


if __name__=="__main__":unittest.main()
