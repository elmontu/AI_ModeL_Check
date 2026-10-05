"""Integrity checks for the optional cross-repository advisory compilation."""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_advisory_displayed_tables import compile_digest, displayed_tables


class AdvisoryDisplayedTableTests(unittest.TestCase):
    def test_only_displayed_tables_outside_code_fences_are_counted(self) -> None:
        lines = [
            "# Findings",
            "```markdown",
            "| example | value |",
            "| --- | --- |",
            "| not a result | 1 |",
            "```",
            "| metric | value |",
            "| --- | ---: |",
            "| adverse | 2 |",
        ]
        tables = displayed_tables(lines)
        self.assertEqual(len(tables), 1)
        self.assertEqual(tables[0][0], 7)
        self.assertEqual(tables[0][1], "Findings")

    def test_digest_rejects_a_changed_curated_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / "example-20260929" / "RESULTS.md"
            report.parent.mkdir()
            report.write_text("| a | b |\n| --- | --- |\n| 1 | 2 |\n", encoding="utf-8")
            expected = hashlib.sha256(report.read_bytes()).hexdigest()
            index = {
                "schema": "academic-canonical-results-v1",
                "families": [{
                    "family": "example-20260929",
                    "canonical_result_markdown": "example-20260929/RESULTS.md",
                    "published_sha256": expected,
                    "status": "test",
                }],
                "advisor_later_results_O1_O7": [],
            }
            (root / "CANONICAL-RESULTS.json").write_text(
                json.dumps(index), encoding="utf-8"
            )
            digest = compile_digest(root)
            self.assertIn("1 Markdown tables and 1 displayed data rows", digest)
            self.assertIn(
                "../government-academic-separation-plan-2026-10-01.md#retired-28-september-archive",
                digest,
            )
            self.assertIn("previously contained 51 sections", digest)
            self.assertNotIn("../publication/2026-09-28/", digest)
            report.write_text(report.read_text(encoding="utf-8") + "changed\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Published SHA mismatch"):
                compile_digest(root)


if __name__ == "__main__":
    unittest.main()
