from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from model_release_assurance import workflow as w

ROOT = Path(__file__).resolve().parents[1]


class PipelineWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.case = self.root / "case with spaces"

    def prepare(self, kind="trained"):
        w.initialize(self.case, kind, "named-party-weights")
        evidence = self.root / "evidence"
        shutil.copytree(ROOT / "examples", evidence)
        request_path = evidence / "request.json"
        request = json.loads(request_path.read_text())
        candidate = evidence / request["release"]["artifact_path"]
        w.bind(self.case, "candidate", candidate)
        w.bind(self.case, "request", request_path)
        for slot in w.SLOTS:
            if slot not in {"candidate", "request", "lineage"}:
                path = self.root / f"{slot}.txt"
                path.write_text("Synthetic test declaration, not approved evidence: " + slot)
                w.bind(self.case, slot, path)
        line_dir = self.root / "lineage sources"
        line_dir.mkdir()
        refs = {}
        for name in ("recipe", "data_manifest", "overlap_evidence", "parent1", "parent2"):
            path = line_dir / (name + ".txt")
            path.write_text(name)
            refs[name] = {"path": path.name, "sha256": w.digest(path)}
        count = 2 if kind in {"merged", "ensemble"} else (0 if kind == "trained" else 1)
        lineage = {
            "format_version": "local-lineage/1", "kind": kind,
            "candidate_sha256": w.digest(candidate),
            "parents": [{"parent_id": f"p{i}", **refs[f"parent{i}"]} for i in range(1, count + 1)],
            "recipe": refs["recipe"], "data_manifest": refs["data_manifest"],
            "overlap_evidence": refs["overlap_evidence"],
            "population_overlap": "overlapping" if count > 1 else "single-source",
            "previous_release_ids": request["release"].get("previous_release_ids", []),
        }
        self.lineage_path = line_dir / "lineage.json"
        w.write_json(self.lineage_path, lineage)
        w.bind(self.case, "lineage", self.lineage_path)
        return request_path

    def mutate_lineage(self, callback):
        value = json.loads(self.lineage_path.read_text())
        callback(value)
        w.write_json(self.lineage_path, value, replace=True)
        w.bind(self.case, "lineage", self.lineage_path)

    def test_education_omits_documents_but_retains_evidence_checks(self):
        self.prepare()
        project = w.load_project(self.case)
        for slot in w.EDUCATION_OPTIONAL:
            project.files[slot] = None
        w.write_json(self.case / "project.json", project.model_dump(), replace=True)
        self.assertEqual(len(w.inspect_project(self.case)[0]["issues"]), 3)
        project.mode = "education"
        w.write_json(self.case / "project.json", project.model_dump(), replace=True)
        preflight = w.inspect_project(self.case)[0]
        self.assertEqual(preflight["issues"], [])
        self.assertEqual(len(preflight["warnings"]), 3)
        result = json.loads((w.assess(self.case) / "workflow-result.json").read_text())
        self.assertEqual(result["mode"], "education")
        self.assertEqual(result["warnings"], preflight["warnings"])
        self.assertFalse(result["authorized"])
        optional = self.root / "security-report.txt"
        w.bind(self.case, "security-report", optional)
        optional.write_text("changed")
        self.assertIn("digest mismatch: security-report", w.inspect_project(self.case)[0]["issues"])
        project = w.load_project(self.case)
        project.files["candidate"] = None
        w.write_json(self.case / "project.json", project.model_dump(), replace=True)
        self.assertIn("missing input: candidate", w.inspect_project(self.case)[0]["issues"])

    def test_legacy_project_defaults_to_review(self):
        w.initialize(self.case, "trained", "api")
        project = w.load_project(self.case).model_dump()
        del project["mode"]
        w.write_json(self.case / "project.json", project, replace=True)
        self.assertEqual(w.load_project(self.case).mode, "review")

    def test_new_case_is_incomplete_and_cannot_overwrite(self):
        w.initialize(self.case, "adapter", "public-weights")
        result, _, _ = w.inspect_project(self.case)
        self.assertEqual(len(result["issues"]), len(w.SLOTS))
        self.assertFalse(result["authorization_eligible"])
        with self.assertRaises(FileExistsError):
            w.initialize(self.case, "trained", "api")
        self.assertEqual(w.load_project(self.case).kind, "adapter")

    def test_missing_inputs_preserve_failed_attempt(self):
        w.initialize(self.case, "adapter", "public-weights")
        with self.assertRaisesRegex(ValueError, "preflight failed"):
            w.assess(self.case)
        runs = list((self.case / "runs").iterdir())
        self.assertEqual(len(runs), 1)
        result = json.loads((runs[0] / "workflow-result.json").read_text())
        self.assertEqual(result["workflow_status"], "failed")
        self.assertFalse(result["authorized"])
        self.assertFalse((runs[0] / "assessment-report.json").exists())

    def test_engine_assessment_replayed_and_previous_runs_retained(self):
        self.prepare()
        before, _, _ = w.inspect_project(self.case)
        self.assertEqual(before["issues"], [])
        self.assertFalse(before["document_adequacy_verified"])
        first, second = w.assess(self.case), w.assess(self.case)
        self.assertNotEqual(first, second)
        for run in (first, second):
            result = json.loads((run / "workflow-result.json").read_text())
            report = json.loads((run / "assessment-report.json").read_text())
            self.assertEqual(result["assessment_verdict"], report["overall_verdict"])
            self.assertEqual(result["workflow_status"], "assessment_recorded")
            self.assertFalse(result["authorization_eligible"])
            self.assertTrue((run / "audit-verification.json").exists())

    def test_all_derivative_profiles_accept_bound_immediate_parents(self):
        for kind in w.KINDS[1:]:
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                self.root = Path(directory)
                self.case = self.root / "case"
                self.prepare(kind)
                result, _, _ = w.inspect_project(self.case)
                self.assertEqual(result["issues"], [])

    def test_missing_or_duplicate_merge_parents_rejected(self):
        self.prepare("merged")
        self.mutate_lineage(lambda value: value["parents"].pop())
        self.assertIn("at least 2", str(w.inspect_project(self.case)[0]["issues"]))
        self.mutate_lineage(lambda value: value["parents"].append({**value["parents"][0], "parent_id": "different-id"}))
        self.assertIn("duplicate parent bytes", str(w.inspect_project(self.case)[0]["issues"]))

    def test_lineage_builder_hashes_inputs_and_preserves_prior_manifest(self):
        self.prepare("adapter")
        previous = self.lineage_path.read_bytes()
        base = self.lineage_path.parent
        path = w.create_lineage(self.case, [["base", str(base / "parent1.txt")]],
                                base / "recipe.txt", base / "data_manifest.txt",
                                base / "overlap_evidence.txt", "overlapping", [])
        self.assertNotEqual(path, self.lineage_path)
        self.assertEqual(self.lineage_path.read_bytes(), previous)
        self.assertEqual(w.inspect_project(self.case)[0]["issues"], [])
        self.assertEqual(w.load_project(self.case).files["lineage"].sha256, w.digest(path))

    def test_tampered_parent_and_unknown_overlap_rejected(self):
        self.prepare("adapter")
        (self.lineage_path.parent / "parent1.txt").write_text("changed parent")
        self.assertIn("lineage source digest mismatch", str(w.inspect_project(self.case)[0]["issues"]))
        self.mutate_lineage(lambda value: value.update(population_overlap="unknown"))
        self.assertIn("resolve population overlap", str(w.inspect_project(self.case)[0]["issues"]))

    def test_rebound_lineage_cannot_change_candidate_or_prior_releases(self):
        self.prepare()
        self.mutate_lineage(lambda value: value.update(candidate_sha256="a" * 64))
        self.assertIn("does not match", str(w.inspect_project(self.case)[0]["issues"]))
        self.mutate_lineage(lambda value: value.update(candidate_sha256=w.load_project(self.case).files["candidate"].sha256, previous_release_ids=["undeclared-release"]))
        self.assertIn("disagree on previous releases", str(w.inspect_project(self.case)[0]["issues"]))

    def test_api_and_full_artifact_scope_cannot_be_interchanged(self):
        self.prepare()
        project = w.load_project(self.case)
        project.route = "api"
        w.write_json(self.case / "project.json", project.model_dump(), replace=True)
        self.assertIn("API route", str(w.inspect_project(self.case)[0]["issues"]))

    def test_modified_required_document_blocks(self):
        self.prepare()
        (self.root / "utility-report.txt").write_text("different report")
        self.assertIn("digest mismatch: utility-report", w.inspect_project(self.case)[0]["issues"])

    def test_score_only_request_cannot_be_used_for_weights(self):
        request_path = self.prepare()
        request = json.loads(request_path.read_text())
        request["release"]["interface"]["access"] = "score"
        request["release"]["interface"]["output_channels"].update(scores=True, parameters=False, downloadable_files=[])
        w.write_json(request_path, request, replace=True)
        w.bind(self.case, "request", request_path)
        self.assertIn("weight release requires full_artifact", str(w.inspect_project(self.case)[0]["issues"]))

    def test_api_route_rejects_parameter_channel_even_with_score_access(self):
        request_path = self.prepare()
        request = json.loads(request_path.read_text())
        request["release"]["interface"]["access"] = "score"
        request["release"]["interface"]["output_channels"]["scores"] = True
        w.write_json(request_path, request, replace=True)
        w.bind(self.case, "request", request_path)
        project = w.load_project(self.case)
        project.route = "api"
        w.write_json(self.case / "project.json", project.model_dump(), replace=True)
        self.assertIn("API route cannot describe exported", str(w.inspect_project(self.case)[0]["issues"]))

    def test_output_publication_error_never_leaves_completion_marker(self):
        self.prepare()
        original = Path.write_text

        def fail_guide(path, *args, **kwargs):
            if path.name == "START-HERE.md":
                raise OSError("simulated guide publication failure")
            return original(path, *args, **kwargs)

        with patch.object(Path, "write_text", fail_guide):
            with self.assertRaisesRegex(ValueError, "publication failure"):
                w.assess(self.case)
        run = next((self.case / "runs").iterdir())
        result = json.loads((run / "workflow-result.json").read_text())
        self.assertEqual(result["workflow_status"], "failed")
        self.assertFalse(result["authorized"])

    def test_source_change_during_engine_call_is_failed_and_audited(self):
        self.prepare()
        original = w.AssuranceEngine.assess

        def mutate(engine, request, base):
            result = original(engine, request, base)
            (self.root / "utility-report.txt").write_text("changed during assessment")
            return result

        with patch.object(w.AssuranceEngine, "assess", mutate):
            with self.assertRaisesRegex(ValueError, "changed during assessment"):
                w.assess(self.case)
        run = next((self.case / "runs").iterdir())
        self.assertFalse((run / "assessment-report.json").exists())
        self.assertEqual(json.loads((run / "workflow-result.json").read_text())["workflow_status"], "failed")
        self.assertTrue(w.AuditStore.open_read_only(run / "audit.sqlite3").verify(require_events=True, require_complete=True).complete)

    def test_config_cannot_delete_mandatory_slots(self):
        w.initialize(self.case, "trained", "api")
        value = json.loads((self.case / "project.json").read_text())
        del value["files"]["independent-review"]
        w.write_json(self.case / "project.json", value, replace=True)
        with self.assertRaisesRegex(ValueError, "every required input slot"):
            w.inspect_project(self.case)

    def test_supporting_inventory_cannot_shadow_a_required_binding(self):
        self.prepare()
        project=w.load_project(self.case).model_dump()
        project['supporting_files']={'security-report':project['files']['candidate']}
        w.write_json(self.case/'project.json',project,replace=True)
        with self.assertRaisesRegex(ValueError,'supporting files cannot replace'):
            w.inspect_project(self.case)

    def test_cli_status_and_setup_dry_run_are_actionable(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(w.main(["init", str(self.case)]), 0)
            self.assertEqual(w.main(["check", str(self.case)]), 2)
        spec = importlib.util.spec_from_file_location("setup_pipeline", ROOT / "scripts/setup_pipeline.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        output = io.StringIO()
        target = self.root / "new environment"
        with contextlib.redirect_stdout(output):
            self.assertEqual(module.main(["--dry-run", "--venv", str(target), "--profile", "training", "--wheelhouse", str(self.root)]), 0)
        commands = json.loads(output.getvalue())["commands"]
        installs = [cmd for cmd in commands if "install" in cmd]
        self.assertTrue(all("--no-index" in cmd for cmd in installs))
        self.assertTrue(any("--no-build-isolation" in cmd for cmd in installs))
        self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
