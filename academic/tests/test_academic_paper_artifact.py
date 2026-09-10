"""Offline consistency checks, not validation of scientific claims or a PDF build.

These checks use only the retained companion and manuscript. They deliberately
do not reopen ignored workstation evidence, rerun studies, or require reportlab.
The fixed row counts describe the named historical studies, not a cap on future
tables or sources that may be added to the companion.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]
PAPER = ROOT / "academic" / "paper"


def without_tex_comments(text: str) -> str:
    """Remove comments but retain escaped percent signs in ordinary TeX source."""
    return re.sub(r"(?<!\\)%[^\n]*", "", text)


class AcademicPaperArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = json.loads((PAPER / "experimental-data.json").read_text(encoding="utf-8"))
        cls.tables = {table["id"]: table for table in cls.data["tables"]}
        cls.manuscript = without_tex_comments((PAPER / "mra-paper.tex").read_text(encoding="utf-8"))
        cls.protocol = without_tex_comments((PAPER / "protocol-section.tex").read_text(encoding="utf-8"))
        cls.protocol_appendix = without_tex_comments((PAPER / "protocol-appendix.tex").read_text(encoding="utf-8"))

    def test_generated_table_bytes_replay_from_companion_without_figure_builder(self) -> None:
        # Loading this module and calling build_tex needs only the standard library;
        # build_figure/main would add an unrelated reportlab/PDF dependency.
        spec = importlib.util.spec_from_file_location(
            "academic_paper_table_builder_for_test", ROOT / "academic" / "scripts" / "build_academic_paper.py"
        )
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        expected = module.build_tex(self.data)
        self.assertEqual((PAPER / "experimental-tables.tex").read_bytes(), expected)

    def test_source_and_table_references_are_unique_and_relative(self) -> None:
        sources = self.data["sources"]
        source_ids = [source["id"] for source in sources]
        self.assertEqual(len(source_ids), len(set(source_ids)))
        self.assertEqual(len(self.data["tables"]), len(self.tables))
        known_sources = set(source_ids)
        for source in sources:
            with self.subTest(source=source["id"]):
                path = source["path"]
                self.assertFalse(PurePosixPath(path).is_absolute())
                self.assertFalse(PureWindowsPath(path).is_absolute())
                self.assertFalse(PureWindowsPath(path).drive)
                self.assertNotIn("..", PurePosixPath(path).parts)
                self.assertNotIn("\\", path)
                self.assertRegex(source["sha256"], r"^[0-9a-f]{64}$")
                self.assertGreater(source["bytes"], 0)
        for table in self.data["tables"]:
            with self.subTest(table=table["id"]):
                self.assertEqual(table["row_count"], len(table["rows"]))
                for row in table["rows"]:
                    self.assertIn(row.get("source_id", table.get("source_id")), known_sources)
                    if "field_pointers" in row:
                        self.assertEqual(set(row["values"]), set(row["field_pointers"]))
                        self.assertTrue(all(
                            pointer == "" or pointer.startswith("/")
                            for pointer in row["field_pointers"].values()
                        ))
                    else:
                        self.assertGreater(row["source_line"], 0)
                        self.assertTrue(row["precision"])
        generator = self.data["generator"]
        self.assertEqual(generator["path"], "academic/scripts/build_academic_paper_data.py")
        self.assertEqual(
            generator["sha256"], hashlib.sha256((ROOT / generator["path"]).read_bytes()).hexdigest()
        )

    def test_named_finite_channel_studies_retain_all_4200_replay_rows(self) -> None:
        self.assertEqual(self.tables["controlled_groups"]["row_count"], 9)
        roles = [row["values"]["tier_role"] for row in self.tables["controlled_groups"]["rows"]]
        self.assertEqual(roles.count("primary"), 3)
        self.assertEqual(roles.count("diagnostic_only"), 6)
        self.assertEqual(self.tables["controlled_repeat_records"]["row_count"], 1800)
        replay_count = self.tables["controlled_repeat_records"]["row_count"]
        for vintage in ("v2", "v3"):
            with self.subTest(vintage=vintage):
                self.assertEqual(self.tables[f"model_{vintage}_primary"]["row_count"], 6)
                self.assertEqual(self.tables[f"model_{vintage}_repeated_summary"]["row_count"], 6)
                for index in range(6):
                    count = self.tables[f"model_{vintage}_repeats_{index}"]["row_count"]
                    self.assertEqual(count, 200)
                    replay_count += count
        self.assertEqual(replay_count, 4200)

    def test_generated_gap_table_replays_separate_constructed_artifact(self) -> None:
        spec = importlib.util.spec_from_file_location(
            "academic_gap_table_builder_for_test", ROOT / "academic" / "scripts" / "build_academic_paper.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        gaps = json.loads((PAPER / "gap-construction-results.json").read_text(encoding="utf-8"))
        self.assertEqual((PAPER / "gap-tables.tex").read_bytes(), module.build_gap_tex(gaps))
        self.assertIn(r"\input{gap-tables.tex}", self.manuscript)

    def test_seven_safeguards_are_in_main_admission_before_transitions(self) -> None:
        start = self.protocol.index(r"\label{sec:admission}")
        end = self.protocol.index(r"\subsection{State transitions and invalidation}")
        self.assertLess(start, end)
        obligations = re.findall(r"\\item\s+\\textbf\{O([1-7]):", self.protocol[start:end])
        self.assertEqual(obligations, [str(i) for i in range(1, 8)])
        self.assertIn(r"\operatorname{Admit}", self.protocol[start:end])
        self.assertIn(r"\operatorname{Refuse}", self.protocol[start:end])
        self.assertIn("BLOCK and INCONCLUSIVE are ineligible", self.protocol_appendix)
        self.assertIn("service linearization point", self.protocol_appendix)
        self.assertIn("Extended research draft; not a submission-length manuscript.", self.manuscript)

    def test_named_workload_timing_and_hook_tables_retain_registered_counts(self) -> None:
        expected = {
            "tree_primary": 5,
            "vision_scaling": 6,
            "llm_scaling": 6,
            "tree_timing_repeats": 9,
            "tree_timing_summary": 3,
            "cli_timing_profiles": 11,
            "cli_timing_runs": 33,
            "cli_timing_stages": 297,
            "cli_interpreter_memory": 6,
            "excluded_launcher_memory": 11,
            "hook_audit_table_03": 3,
            "hook_audit_table_04": 13,
            "hook_audit_table_07": 2,
            "hook_audit_table_08": 8,
        }
        for table_id, count in expected.items():
            with self.subTest(table=table_id):
                self.assertEqual(self.tables[table_id]["row_count"], count)
        self.assertEqual(sum(self.tables[key]["row_count"] for key in (
            "tree_primary", "vision_scaling", "llm_scaling"
        )), 17)

    def test_negative_results_and_non_authorizing_status_are_preserved(self) -> None:
        self.assertIs(self.tables["model_v2_acceptance"]["rows"][0]["values"]["passed"], False)
        self.assertIs(self.tables["model_v3_acceptance"]["rows"][0]["values"]["passed"], True)
        self.assertIn("INVALID", self.tables["excluded_launcher_memory"]["interpretation"])
        self.assertNotEqual(
            self.tables["excluded_launcher_memory"]["source_id"],
            self.tables["cli_interpreter_memory"]["source_id"],
        )
        validation = self.data["validation"]
        for name in ("experiments_rerun", "proofs_rebuilt", "all_results_current_version",
                     "publication_bundle_complete", "authorization_eligible"):
            with self.subTest(boundary=name):
                self.assertIs(validation[name], False)
        self.assertIs(validation["historical_negative_results_preserved"], True)
        self.assertTrue(validation["checks"])
        self.assertTrue(all(check["passed"] for check in validation["checks"]))

    def test_all_tex_citation_keys_resolve_unique_bibliography_entries(self) -> None:
        bibliography = without_tex_comments((PAPER / "references.bib").read_text(encoding="utf-8"))
        keys = re.findall(
            r"(?mi)^\s*@(?!comment\b|string\b|preamble\b)[a-z]+\s*\{\s*([^,\s]+)\s*,",
            bibliography,
        )
        self.assertTrue(keys)
        self.assertEqual(len(keys), len(set(keys)), "duplicate bibliography keys")
        known_keys = set(keys)
        citations = set()
        for path in sorted(PAPER.rglob("*.tex")):
            source = without_tex_comments(path.read_text(encoding="utf-8"))
            for group in re.findall(r"\\cite[a-zA-Z]*\*?(?:\s*\[[^\]]*\]){0,2}\s*\{([^}]*)\}", source):
                used = {key.strip() for key in group.split(",")}
                with self.subTest(file=path.name, citation=group):
                    self.assertNotIn("", used)
                    self.assertFalse(used - known_keys, f"unresolved bibliography keys: {sorted(used - known_keys)}")
                citations.update(used)
        self.assertTrue(citations, "no manuscript citation commands were checked")

    def test_ieee_conference_compsoc_layout_has_no_geometry_override(self) -> None:
        declaration = re.search(r"\\documentclass\s*\[([^]]*)\]\s*\{([^}]*)\}", self.manuscript)
        self.assertIsNotNone(declaration)
        self.assertEqual(declaration.group(2).strip(), "IEEEtran")
        options = {option.strip() for option in declaration.group(1).split(",")}
        self.assertTrue({"conference", "compsoc"}.issubset(options))
        self.assertNotIn("onecolumn", options)
        packages = re.findall(r"\\(?:usepackage|RequirePackage)(?:\s*\[[^]]*\])?\s*\{([^}]*)\}", self.manuscript)
        self.assertNotIn("geometry", {name.strip() for group in packages for name in group.split(",")})
        self.assertNotRegex(self.manuscript, r"\\(?:geometry|newgeometry|restoregeometry)\b")
        dimensions = r"(?:textwidth|textheight|oddsidemargin|evensidemargin|topmargin|hoffset|voffset|paperwidth|paperheight|columnsep)"
        self.assertNotRegex(self.manuscript, r"\\(?:setlength|addtolength)\s*\{\s*\\" + dimensions + r"\s*\}")
        self.assertNotRegex(self.manuscript, r"\\" + dimensions + r"\s*=")

    def test_manuscript_uses_generated_tables_and_ieee_bibliography(self) -> None:
        self.assertRegex(self.manuscript, r"\\input\s*\{experimental-tables(?:\.tex)?\}")
        self.assertRegex(self.manuscript, r"\\bibliographystyle\s*\{IEEEtran\}")
        self.assertRegex(self.manuscript, r"\\bibliography\s*\{references\}")

    def test_main_includes_full_protocol_and_separate_protocol_appendix(self) -> None:
        protocol_inputs = list(re.finditer(r"\\input\s*\{protocol-section(?:\.tex)?\}", self.manuscript))
        appendix_inputs = list(re.finditer(r"\\input\s*\{protocol-appendix(?:\.tex)?\}", self.manuscript))
        self.assertEqual(len(protocol_inputs), 1)
        self.assertEqual(len(appendix_inputs), 1)
        self.assertLess(protocol_inputs[0].start(), self.manuscript.index(r"\label{sec:implementation}"))
        self.assertGreater(appendix_inputs[0].start(), self.manuscript.index(r"\appendices"))
        self.assertIn(r"\label{sec:theory-protocol}", self.protocol)

    def test_protocol_appendix_has_six_ordered_pseudocode_algorithms(self) -> None:
        headings = re.findall(r"\\subsection\{Algorithm A(\d+):\s*([A-Za-z]+)", self.protocol_appendix)
        self.assertEqual(headings, [
            ("1", "VerifyEnvelope"), ("2", "Freeze"), ("3", "CollectAndAssess"),
            ("4", "RecommendAndSelect"), ("5", "ReviewAndCommit"), ("6", "ActivateServeMonitor"),
        ])
        self.assertIn(r"\label{app:algorithms}", self.protocol_appendix)

    def test_implementation_and_studies_share_one_methodology_section(self) -> None:
        start = self.manuscript.index(r"\section{Implementation and Evaluation}")
        end = self.manuscript.index(r"\section{Results}")
        methods = self.manuscript[start:end]
        self.assertEqual(methods.count(r"\section{"), 1)
        self.assertIn(r"\label{sec:methods}", methods)
        self.assertIn(r"\label{sec:implementation}", methods)
        self.assertIn(r"\subsection{Reference Implementation and Execution Boundary}", methods)
        self.assertIn(r"\subsection{Exact Finite Tests of Protocol Obligations}", methods)
        self.assertIn(r"\subsection{Controlled and Model-Backed Ceiling Studies}", methods)
        self.assertIn(r"\code{authorization\_eligible=false}", methods)
        normalized = " ".join(methods.split())
        self.assertIn("Most timing and attack data below predate the 0.8 corrections", normalized)
        self.assertIn("they do not measure the corrected implementation", normalized)
        self.assertNotIn(r"\paragraph{Proof layers}", methods)

    def test_research_questions_and_central_guarantee_lead_the_evaluation(self) -> None:
        intro_start = self.manuscript.index(r"\section{Introduction}")
        intro_end = self.manuscript.index(r"\section{Related Work and Positioning}")
        introduction = self.manuscript[intro_start:intro_end]
        self.assertIn(r"\paragraph{Research questions}", introduction)
        for question in ("RQ1", "RQ2", "RQ3"):
            with self.subTest(question=question):
                self.assertRegex(introduction, rf"\b{question}\b")
        self.assertIn(r"\ref{thm:statistics}", introduction)
        methods_start = self.manuscript.index(r"\label{sec:methods}")
        self.assertLess(self.manuscript.index(r"\input{protocol-section.tex}"), methods_start)
        results_start = self.manuscript.index(r"\section{Results}")
        results_end = self.manuscript.index(r"\section{Discussion and Limitations}")
        questions = re.findall(r"\\subsection\{(RQ[1-3]):", self.manuscript[results_start:results_end])
        self.assertEqual(questions, ["RQ1", "RQ2", "RQ3"])

    def test_detailed_evidence_and_proof_inventory_remain_in_appendices(self) -> None:
        split = self.manuscript.index(r"\appendices")
        main, appendix = self.manuscript[:split], self.manuscript[split:]
        for macro in ("GapConstructionTable", "ControlledTable", "ModelCeilingTable"):
            with self.subTest(primary_table=macro):
                self.assertIn("\\" + macro, main)
        for macro in ("PublicWorkloadTable", "ProtocolTimingTable", "SupplementaryTables"):
            with self.subTest(extended_table=macro):
                self.assertIn("\\" + macro, appendix)
                self.assertNotIn("\\" + macro, main)
        self.assertIn(r"\subsection{Software Validation and Evidence Provenance}", appendix)
        self.assertIn(r"\label{sec:proof-status}", appendix)
        self.assertIn(r"\label{tab:lean-scope}", appendix)
        self.assertIn(r"Appendix~\ref{sec:proof-status}", main)

    def test_government_profile_is_bound_to_selection_commit_and_live_service(self) -> None:
        profile_start = self.protocol.index(r"\label{sec:gov-profile}")
        profile = re.split(r"\\subsection\{", self.protocol[profile_start:], maxsplit=1)[0]
        normalized = " ".join(profile.split())
        self.assertIn("GovCommitOK", profile)
        self.assertRegex(profile, r"M_G\^k")
        for stage in ("select", "commit", "serve"):
            with self.subTest(stage=stage):
                self.assertIn(r"G^{\rm " + stage + "}", profile)
        self.assertIn("Risk acceptance cannot waive a mandatory", normalized)
        self.assertIn("not new JSON schemas", normalized)
        headings = list(re.finditer(r"\\subsection\{Algorithm A(\d+):", self.protocol_appendix))
        algorithms = {int(heading.group(1)): re.split(r"\\(?:subsection|section)\{",
            self.protocol_appendix[heading.end():], maxsplit=1)[0] for heading in headings}
        self.assertIn("P_G", algorithms[2])
        self.assertIn("M_G^k(t)", profile)
        self.assertIn(r"G^{\rm evidence}", algorithms[3])
        self.assertIn(r"G^{\rm assess}", algorithms[3])
        self.assertIn("do not require passing institutional obligations", " ".join(self.protocol_appendix.split()))
        self.assertIn(r"G^{\rm select}", algorithms[4])
        self.assertIn("GovCommitOK", algorithms[5])
        # Activation and each subsequent request both require the current profile.
        self.assertGreaterEqual(algorithms[6].count(r"G^{\rm serve}"), 2)
        self.assertIn(r"\ref{sec:gov-profile}", self.protocol_appendix)

    def test_government_framing_does_not_generalize_privacy_to_institutional_success(self) -> None:
        title = re.search(r"\\title\{([^}]+)\}", self.manuscript)
        self.assertIsNotNone(title)
        normalized_title = " ".join(title.group(1).replace(r"\\", " ").split())
        self.assertEqual(normalized_title, "Model Governance for Government Bodies: An Evidence-Bound Release Assurance Protocol")
        main = self.manuscript[:self.manuscript.index(r"\appendices")]
        normalized = " ".join(main.split())
        self.assertIn("not a probability bound on unlawful", normalized)
        self.assertRegex(normalized, r"neither a government field trial.{0,140}is claimed")
        self.assertIn("studies contain no public-body approval exercise", normalized)
        self.assertIn("does not certify compliance", normalized)
        # Presence checks guard the claim boundary; they are not legal, empirical,
        # or mathematical validation of the government profile itself.

    def test_six_main_guarantees_have_referenced_appendix_proof_sections(self) -> None:
        expected = {"prop:decision", "thm:statistics", "prop:scope", "thm:transfer",
                    "thm:lifecycle", "thm:finite-ceiling"}
        labels = re.findall(r"\\label\{([^}]+)\}", self.protocol)
        self.assertTrue(expected.issubset(labels))
        pattern = r"\\subsection\{Proof of (?:Theorem|Proposition)~\\ref\{([^}]+)\}\}"
        headings = list(re.finditer(pattern, self.protocol_appendix))
        self.assertEqual({match.group(1) for match in headings}, expected)
        self.assertEqual(len(headings), 6)
        for heading in headings:
            following = self.protocol_appendix[heading.end():]
            block = re.split(r"\\(?:subsection|section)\{", following, maxsplit=1)[0]
            with self.subTest(theorem=heading.group(1)):
                self.assertIn(r"\begin{proof}", block)
                self.assertIn(r"\end{proof}", block)

    def test_all_seven_gap_sections_have_written_constructions_or_proofs(self) -> None:
        headings = list(re.finditer(r"\\subsection\{G([1-7]):[^\n]*\}", self.protocol_appendix))
        self.assertEqual([int(heading.group(1)) for heading in headings], list(range(1, 8)))
        for heading in headings:
            following = self.protocol_appendix[heading.end():]
            block = re.split(r"\\(?:subsection|section)\{", following, maxsplit=1)[0]
            with self.subTest(gap=heading.group(1)):
                self.assertIn(r"\begin{proof}", block)
                self.assertIn(r"\end{proof}", block)


if __name__ == "__main__":
    unittest.main()
