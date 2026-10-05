"""Complete public local assessment and honest failed-stage behavior."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from model_release_assurance.production_assessment import contracts as c, rehearsal


class RehearsalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.result = rehearsal.exercise(cls.root / "success", profile="local_public_fixture")

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_complete_real_local_assessment(self):
        self.assertEqual(self.result["status"], "passed", self.result.get("errors"))
        self.assertEqual({row["name"] for row in self.result["checks"]}, rehearsal.REQUIRED_CHECKS)
        self.assertTrue(all(row["passed"] for row in self.result["checks"]))

    def test_permanent_production_findings(self):
        review = self.result["summary"]["review"]
        self.assertEqual(review["production_blocker_count"], 11)
        self.assertIs(review["production_blockers_open"], True)
        self.assertIs(review["agency_assessor_appointed"], False)

    def test_expired_serialized_review_unusable(self):
        review = self.result["summary"]["review"]
        self.assertIs(review["expired_review_unusable"], True)
        self.assertIs(review["serialized_review_restored"], False)

    def test_packet_verifier_does_not_claim_reconstructed_execution(self):
        self.assertEqual(self.result["packet"]["status"], "historical_packet_verified")
        self.assertIs(self.result["packet"]["probe_execution_reconstructed"], False)
        self.assertIs(self.result["packet"]["agency_signer_authenticated"], False)

    def test_all_results_non_authorizing(self):
        for name, flag in c.FLAGS.items():
            self.assertIs(self.result[name], flag)

    def test_production_refuses_before_output(self):
        target = self.root / "production-denied"
        with self.assertRaises(c.AssessmentError):
            rehearsal.exercise(target)
        self.assertFalse(target.exists())

    def test_probe_failure_preserved_without_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "failed"
            def probes(output, *, profile="agency_private_cloud"):
                if profile != "local_public_fixture":
                    c.require_local(profile)
                raise c.AssessmentError("PRIVATE-JWT-CANARY")
            with patch.object(rehearsal, "run_probes", side_effect=probes):
                result = rehearsal.exercise(target, profile="local_public_fixture")
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["errors"], [{"stage": "adversarial_probes", "code": "LocalAssessmentStageFailed"}])
            self.assertNotIn("CANARY", str(result))
            self.assertTrue((target / "exercise-result.json").exists())

    def test_packet_failure_keeps_known_probe_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "failed"
            # Reuse genuine observations from the successful run while avoiding
            # another fit; packet stage is the only injected fault.
            import json, shutil
            fixture = self.root / "success/packet/fixture"
            observed = json.loads((self.root / "success/packet/assessment-observations.json").read_bytes())
            def probes(output, *, profile="agency_private_cloud"):
                c.require_local(profile)
                shutil.copytree(fixture, output)
                return observed
            with patch.object(rehearsal, "run_probes", side_effect=probes), patch.object(
                    rehearsal.packet, "seal_packet", side_effect=c.AssessmentError("Unavailable")):
                result = rehearsal.exercise(target, profile="local_public_fixture")
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["summary"]["probes"], observed["summary"])
            self.assertEqual(result["errors"][0]["stage"], "packet_integrity")


if __name__ == "__main__":
    unittest.main()
