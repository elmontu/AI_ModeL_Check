"""Hash the exact snapshot parsed by clearance-critical portfolio readers."""
from __future__ import annotations

from pathlib import Path
import unittest
from unittest.mock import patch

from model_release_assurance import incomplete_portfolio, portfolio_statistics
from model_release_assurance.errors import IntegrityError
from model_release_assurance.integrity import canonical_json_bytes, read_verified_source_bytes, sha256_file
import test_portfolio_statistics as fixtures


class PortfolioSourceSnapshotRegressions(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.PortfolioStatisticsTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)

    def test_plan_counts_and_budget_parse_the_verified_snapshot(self):
        fixture = self.fixture
        request = fixture.request()
        expected = portfolio_statistics._resolve_sources(request, fixture.temp)
        for path in (fixture.plan_path, fixture.counts_path, fixture.budget_path):
            with self.subTest(source=path.name):
                original = path.read_bytes()
                captures = []

                def capture_then_replace(source_path, expected_sha256, base_dir):
                    document = read_verified_source_bytes(source_path, expected_sha256, base_dir)
                    if Path(source_path).resolve() == path.resolve():
                        captures.append(document)
                        path.write_bytes(b'{"replaced_after_hash":true}')
                    return document

                try:
                    with patch.object(portfolio_statistics, "read_verified_source_bytes", capture_then_replace):
                        actual = portfolio_statistics._resolve_sources(request, fixture.temp)
                    self.assertEqual(actual, expected)
                    self.assertEqual(captures, [original])
                    # This is a snapshot claim, not immutable custody. A fresh
                    # consumer must reject the now-changed source on disk.
                    with self.assertRaises(IntegrityError):
                        portfolio_statistics._resolve_sources(request, fixture.temp)
                finally:
                    path.write_bytes(original)

    def test_statistical_marginal_parses_verified_bytes_once_per_source(self):
        fixture = self.fixture
        evidence = portfolio_statistics.generate_simultaneous_multinomial_evidence(fixture.request(), fixture.temp)
        path = fixture.temp / "simultaneous-evidence.json"
        original = canonical_json_bytes(evidence)
        path.write_bytes(original)
        problem = portfolio_statistics.compile_multinomial_portfolio_problem(
            evidence, fixture.specification(), evidence_source_path=path.name,
            evidence_source_sha256=sha256_file(path),
        )
        expected = incomplete_portfolio.verify_portfolio_problem_evidence(problem, fixture.temp)
        captures = []

        def capture_then_replace(source_path, expected_sha256, base_dir):
            document = read_verified_source_bytes(source_path, expected_sha256, base_dir)
            if Path(source_path).resolve() == path.resolve():
                captures.append(document)
                path.write_bytes(b'{"replaced_after_hash":true}')
            return document

        with patch.object(incomplete_portfolio, "read_verified_source_bytes", capture_then_replace):
            actual = incomplete_portfolio.verify_portfolio_problem_evidence(problem, fixture.temp)
        self.assertEqual(actual, expected)
        self.assertEqual(captures, [original])
        with self.assertRaises(IntegrityError):
            incomplete_portfolio.verify_portfolio_problem_evidence(problem, fixture.temp)

    def test_rebased_sources_keep_their_original_base_and_reject_later_change(self):
        fixture = self.fixture
        evidence = portfolio_statistics.generate_simultaneous_multinomial_evidence(fixture.request(), fixture.temp)
        output = fixture.temp / "nested" / "reports"
        output.mkdir(parents=True)
        rebased = portfolio_statistics.rebase_multinomial_evidence_sources(
            evidence, current_base_dir=fixture.temp, output_base_dir=output,
        )
        self.assertEqual(
            portfolio_statistics._resolve_sources(rebased.request, output)[3:],
            portfolio_statistics._resolve_sources(evidence.request, fixture.temp)[3:],
        )
        fixture.counts_path.write_bytes(b'{"changed_after_rebase":true}')
        with self.assertRaises(IntegrityError):
            portfolio_statistics._resolve_sources(rebased.request, output)


if __name__ == "__main__":
    unittest.main()
