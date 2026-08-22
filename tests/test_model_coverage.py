from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

from model_release_assurance.model_coverage import (
    MODEL_FAMILY_CATALOG,
    assess_request_model_coverage,
    resolve_model_family,
)
from model_release_assurance.models import AssessmentRequest
from pydantic import ValidationError


ROOT = Path(__file__).resolve().parents[1]


class ModelCoverageTests(unittest.TestCase):
    def test_catalog_has_unique_all_model_families_and_aliases(self) -> None:
        ids = [entry.family_id for entry in MODEL_FAMILY_CATALOG]
        aliases = [alias for entry in MODEL_FAMILY_CATALOG for alias in entry.aliases]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(aliases), len(set(aliases)))
        self.assertGreaterEqual(len(ids), 20)

    def test_common_families_resolve(self) -> None:
        expected = {
            "XGBoost": "tree_ensemble",
            "logistic regression": "linear_generalized_linear",
            "CNN": "vision_model",
            "LLM": "generative_text_llm",
            "GNN": "graph_model",
            "agentic system": "reinforcement_learning_agent",
        }
        for value, family_id in expected.items():
            self.assertEqual(resolve_model_family(value).family_id, family_id)

    def test_unknown_family_fails_to_custom_review(self) -> None:
        result = resolve_model_family("future-quantum-model")
        self.assertEqual(result.family_id, "custom")
        self.assertEqual(result.status, "custom_review_required")

    def test_request_coverage_reports_missing_scope_without_clearing(self) -> None:
        raw = json.loads((ROOT / "examples" / "request.json").read_text())
        request = AssessmentRequest.model_validate(raw)
        result = assess_request_model_coverage(request)
        self.assertEqual(result["resolved_family"]["family_id"], "tree_ensemble")
        self.assertFalse(result["can_clear"])
        self.assertTrue(result["coverage_ready"])
        self.assertIn("attribute", result["missing_recommended_threats"])
        self.assertIn("reconstruction", result["missing_recommended_threats"])
        self.assertTrue(result["advisories"])

    def test_assessment_v3_requires_a_structured_model_profile(self) -> None:
        raw = json.loads((ROOT / "examples" / "request.json").read_text())
        raw["release"].pop("model_profile")
        with self.assertRaises(ValidationError):
            AssessmentRequest.model_validate(raw)

    def test_cli_lists_catalog_and_reviews_request(self) -> None:
        base = [sys.executable, "-m", "model_release_assurance", "model-coverage"]
        listing = subprocess.run(base + ["--json"], cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(listing.returncode, 0, msg=listing.stderr)
        self.assertGreaterEqual(len(json.loads(listing.stdout)), 20)
        review = subprocess.run(
            base + [str(ROOT / "examples" / "request.json"), "--json"],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        self.assertEqual(review.returncode, 0, msg=review.stderr)
        self.assertFalse(json.loads(review.stdout)["can_clear"])


if __name__ == "__main__":
    unittest.main()
