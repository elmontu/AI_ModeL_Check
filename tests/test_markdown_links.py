"""Publication links stay strict while ignored local experiment outputs are visible."""
from __future__ import annotations

from contextlib import redirect_stdout
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_markdown_links.py"
SPEC = importlib.util.spec_from_file_location("markdown_link_checker", SCRIPT)
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)


class MarkdownLinkTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "repository"
        self.root.mkdir()
        root_patch = patch.object(CHECKER, "ROOT", self.root)
        root_patch.start()
        self.addCleanup(root_patch.stop)

    def write(self, relative: str, content: str = "") -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def run_checker(self) -> tuple[int, str]:
        output = io.StringIO()
        with redirect_stdout(output):
            result = CHECKER.main()
        return result, output.getvalue()

    def test_valid_published_documents_schemas_sources_and_external_links(self):
        self.write("docs/guide with spaces.md")
        self.write("schemas/contract.json", "{}")
        self.write("src/example.py")
        self.write("README.md", "\n".join((
            "[guide](docs/guide%20with%20spaces.md#section)",
            "[angle](<docs/guide with spaces.md>)",
            "[schema](schemas/contract.json)",
            "[source](src/example.py)",
            "[web](https://example.invalid/missing)",
            "[mail](mailto:example@example.invalid) [section](#section)",
        )))
        self.assertEqual(CHECKER.missing_links(), ())
        result, output = self.run_checker()
        self.assertEqual(result, 0)
        self.assertIn("2 Markdown files", output)
        self.assertIn("0 local-only generated artifact links", output)

    def test_missing_and_present_output_artifacts_are_counted_not_required(self):
        self.write("README.md", "[report](output/absent/report.pdf)\n[present](output/report.json)")
        self.write("docs/guide.md", "[receipt](../output/absent/receipt.json#result)")
        self.write("output/report.json", "{}")
        self.write("output/ignored.md", "[ignored](missing.md)")
        self.assertEqual(CHECKER.missing_links(), ())
        result, output = self.run_checker()
        self.assertEqual(result, 0)
        self.assertIn("2 Markdown files", output)
        self.assertIn("3 local-only generated artifact links under output/ (not checked)", output)

    def test_missing_published_document_schema_and_source_still_fail(self):
        targets = ("docs/missing.md", "schemas/missing.json", "src/missing.py")
        self.write("README.md", "\n".join(f"[missing]({target})" for target in targets))
        failures = CHECKER.missing_links()
        self.assertIsInstance(failures, tuple)
        self.assertEqual(len(failures), 3)
        for line, target in enumerate(targets, 1):
            self.assertIn(f"README.md:{line}: missing local target {target!r}", failures)
        result, output = self.run_checker()
        self.assertEqual(result, 1)
        self.assertIn("missing local target 'src/missing.py'", output)

    def test_normalized_traversal_cannot_disguise_missing_published_targets(self):
        escaped = (
            "output/../docs/missing.md",
            "output/%2e%2e/docs/encoded.md",
            "output/sub/../../src/missing.py",
        )
        self.write("README.md", "\n".join(
            [f"[missing]({target})" for target in escaped]
            + ["[local](docs/../output/missing-report.pdf)"]
        ))
        failures = CHECKER.missing_links()
        self.assertEqual(len(failures), 3)
        for target in escaped:
            self.assertTrue(any(repr(target) in failure for failure in failures))
        result, output = self.run_checker()
        self.assertEqual(result, 1)
        self.assertIn("1 local-only generated artifact links", output)

    def test_other_output_named_locations_do_not_bypass_publication_checks(self):
        targets = ("../output/missing.json", "docs/output/missing.json", "output-backup/missing.json")
        self.write("README.md", "\n".join(f"[missing]({target})" for target in targets))
        self.assertEqual(len(CHECKER.missing_links()), 3)
        result, output = self.run_checker()
        self.assertEqual(result, 1)
        self.assertIn("0 local-only generated artifact links", output)


if __name__ == "__main__":
    unittest.main()
