from __future__ import annotations

import json
from pathlib import Path
import re
import unittest
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
REVIEW = ROOT / "docs" / "game-theory-literature-review.md"
LEDGER = ROOT / "formal" / "game-theory-claim-ledger-v1.json"
FOUNDATIONS = ROOT / "docs" / "mathematical-foundations.md"
PROTOCOL = ROOT / "docs" / "model-release-assurance-protocol.md"
GOVERNANCE_CORE = ROOT / "docs" / "governance-core.md"


class GameTheoryReviewArtifactTests(unittest.TestCase):
    def setUp(self) -> None:
        self.review = REVIEW.read_text(encoding="utf-8")
        self.ledger = json.loads(LEDGER.read_text(encoding="utf-8"))

    def test_source_ledger_is_complete_and_unique(self) -> None:
        sources = self.ledger["sources"]
        identifiers = [source["id"] for source in sources]
        self.assertEqual(identifiers, [f"GT-{index:02d}" for index in range(1, 13)])
        self.assertEqual(len(identifiers), len(set(identifiers)))
        for source in sources:
            self.assertTrue(source["title"])
            self.assertTrue(source["authors"])
            self.assertGreaterEqual(source["year"], 2012)
            self.assertTrue(source["claim_used"])
            self.assertTrue(source["evidence_location"])
            self.assertTrue(source["transfer_limit"])
            self.assertIn(source["id"], self.review)

    def test_external_sources_use_reviewed_primary_domains(self) -> None:
        allowed_hosts = {
            "doi.org",
            "ojs.aaai.org",
            "proceedings.mlr.press",
            "www.ijcai.org",
        }
        for source in self.ledger["sources"]:
            host = urlparse(source["stable_url"]).hostname
            self.assertIn(host, allowed_hosts, source["id"])

    def test_review_separates_source_inference_and_proposal(self) -> None:
        for label in ("**[S]**", "**[I]**", "**[P]**"):
            self.assertIn(label, self.review)
        self.assertIn("No equilibrium without a game", self.review)
        self.assertIn("Pessimistic ties", self.review)
        self.assertIn("No transfer by analogy", self.review)

    def test_mathematics_contains_strategic_primitives_and_nonclaims(self) -> None:
        foundations = FOUNDATIONS.read_text(encoding="utf-8")
        for phrase in (
            "Finite Bayesian release decision problems",
            "Supplemental strategic stress tests for governance",
            "strict robust deterrence",
            "Pessimistic authority objective",
            "Costly assessor effort",
            "strategic attack effort",
            "Real-world parameter contract",
            "performative stability",
        ):
            self.assertIn(phrase, foundations)
        self.assertRegex(foundations, re.compile(r"qF\\ge .*\\delta"))

    def test_protocol_forbids_incentives_from_weakening_hard_gates(self) -> None:
        protocol = PROTOCOL.read_text(encoding="utf-8")
        self.assertIn("Incentive analysis is defense in depth", protocol)
        self.assertIn("MUST NOT use predicted compliance", protocol)
        self.assertIn("pessimistic follower tie rule", protocol)
        self.assertIn("governance-decision effect and authorization effect are `none`", protocol)
        self.assertIn("design-time exact-rational interval evaluator", protocol)
        self.assertIn("not a\nbehaviorally calibrated solver", protocol)

    def test_governance_is_primary_and_strategic_analysis_is_supplemental(self) -> None:
        governance = GOVERNANCE_CORE.read_text(encoding="utf-8")
        for phrase in (
            "institutional model-governance protocol",
            "Governance core",
            "Assurance evidence",
            "Strategic stress tests",
            "Technical enforcement",
            "governance_decision_effect = none",
            "authorization_effect = none",
            "hard_gate_effect = cannot_override_or_remove",
        ):
            self.assertIn(phrase, governance)


if __name__ == "__main__":
    unittest.main()
