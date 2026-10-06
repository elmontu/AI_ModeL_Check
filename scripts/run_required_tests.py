#!/usr/bin/env python3
"""Run the required government unittest profile; skips never satisfy this gate."""
from __future__ import annotations

import argparse
from collections import Counter
import contextlib
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import stat
import subprocess
import sys
import time
import traceback
import unittest

ROOT = Path(__file__).absolute().parents[1]
PATTERNS = (
    "test_pipeline_workflow.py", "test_console.py", "test_export_poc*.py",
    "test_government*.py", "test_export_red_team.py", "test_red_team_catalog.py", "test_temporal*.py",
    "test_infrastructure_plan.py", "test_local_deployment_rehearsal.py",
    "test_production_identity_tokens.py", "test_production_identity_policy.py", "test_production_identity_api.py",
    "test_production_storage_backend.py", "test_production_storage_service.py", "test_production_storage_api.py",
    "test_production_trust_registry.py", "test_production_trust_signer.py", "test_production_trust_integration.py",
    "test_production_build_artifacts.py", "test_production_build_evidence.py", "test_production_build_cli.py",
    "test_production_build_provenance_cli.py",
    "test_production_jobs_store.py", "test_production_jobs_service.py",
    "test_production_jobs_executor.py", "test_production_jobs_rehearsal.py",
    "test_production_adapters_catalog.py", "test_production_adapters_datasets.py",
    "test_production_adapters_native.py", "test_production_adapters_cli.py",
    "test_production_evidence_signing.py", "test_production_evidence_ledger.py",
    "test_production_evidence_replay.py", "test_production_evidence_verifier.py",
    "test_production_evidence_cli.py",
    "test_production_registration_profiles.py", "test_production_registration_contracts.py",
    "test_production_registration_store.py", "test_production_registration_workflow.py",
    "test_production_registration_cli.py",
    "test_production_sacro_*.py",
    "test_production_registry_*.py",
    "test_production_witness_*.py",
    "test_production_review_*.py",
    "test_production_delivery_*.py",
    "test_production_profile_*.py",
    "test_production_monitoring_*.py",
    "test_production_capacity_*.py",
    "test_production_assessment_*.py",
    "test_production_pilot_*.py",
    "test_production_handover_*.py",
)
REQUIRED_SOURCE_INPUTS = (
    "deploy/agency-private-cloud/blueprint.json", "requirements.lock",
    "deploy/sacro/windows-cp312.json", "deploy/sacro/windows-cp312.requirements.txt",
    "deploy/build/windows-cp312.json", "deploy/build/linux-cp312.json",
    "deploy/build/windows-cp312.requirements.txt", "deploy/build/linux-cp312.requirements.txt",
    "deploy/build/verification-runtime.requirements.txt", "deploy/build/policy.json",
    "reproduction/openml/manifests/suite-99-datasets.json",
)
REQUIRED_TEMPORAL = (
    "test_temporal_assurance_cli.py", "test_temporal_assurance_store.py", "test_temporal_assurance_web.py",
    "test_temporal_pipeline.py", "test_temporal_pipeline_adversarial.py", "test_temporal_red_team.py",
    "test_temporal_website.py",
)


class RequiredTestsError(RuntimeError):
    pass


def _real_path(root, relative):
    """Check existing components without following symlinks or Windows reparse points."""
    current = root
    for part in (None, *relative.parts):
        if part is not None:
            current = current / part
        try:
            info = current.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise RequiredTestsError("Symlink or reparse point refused: " + str(current))
        if not stat.S_ISDIR(info.st_mode):
            raise RequiredTestsError("Output path component is not a directory: " + str(current))


def prepare_output(root, output):
    root = Path(root).absolute()
    output = Path(output)
    if ".." in output.parts:
        raise RequiredTestsError("Output traversal is refused")
    target = output.absolute() if output.is_absolute() else root / output
    try:
        relative = target.relative_to(root)
    except ValueError:
        raise RequiredTestsError("Output must be beneath this repository's .local directory")
    if len(relative.parts) < 2 or relative.parts[0] != ".local":
        raise RequiredTestsError("Output must be a new ignored child of .local")
    _real_path(root, relative)
    if target.exists():
        raise RequiredTestsError("Output already exists; choose a new directory")
    checked = subprocess.run(["git", "-C", str(root), "check-ignore", "--no-index", "--quiet", "--", relative.as_posix()],
                             capture_output=True, check=False)
    if checked.returncode != 0:
        raise RequiredTestsError("Output must be ignored by Git")
    target.parent.mkdir(parents=True, exist_ok=True)
    _real_path(root, relative.parent)
    target.mkdir(exist_ok=False)
    return target


def select_modules(root, patterns=PATTERNS, required_temporal=REQUIRED_TEMPORAL):
    selected, problems = set(), []
    for pattern in patterns:
        matches = sorted((root / "tests").glob(pattern))
        if not matches:
            problems.append("Required pattern matched no files: " + pattern)
        selected.update(matches)
    for name in required_temporal:
        if root / "tests" / name not in selected:
            problems.append("Required temporal module is missing: " + name)
    return sorted(selected), problems


def flatten(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from flatten(item)
        else:
            yield item


def _hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_evidence(root, selected):
    paths = (set(selected) | set((root / "tests").rglob("*.py"))
             | set((root / "src/model_release_assurance").rglob("*.py")))
    paths.update(root / name for name in REQUIRED_SOURCE_INPUTS)
    paths.update(path for path in (root / "src/model_release_assurance").rglob("*")
                 if path.is_file() and ("static" in path.parts or path.name == "py.typed"))
    paths.update(path for path in (root / "scripts").glob("*.py"))
    paths.update(root / name for name in ("pyproject.toml", "requirements-build.lock") if (root / name).is_file())
    return [{"path": path.relative_to(root).as_posix(), "sha256": _hash(path)} for path in sorted(paths)]


def git_head(root):
    try:
        result = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, check=False)
        return result.stdout.decode().strip() if result.returncode == 0 else None
    except OSError:
        return None


def package_ownership(root):
    expected = (root / "src/model_release_assurance").resolve()
    modules = []
    for name, module in sorted(sys.modules.items()):
        if name == "model_release_assurance" or name.startswith("model_release_assurance."):
            filename = getattr(module, "__file__", None)
            resolved = Path(filename).resolve() if filename else None
            modules.append({"module": name, "path": str(resolved) if resolved else None,
                            "from_current_source": resolved is not None and resolved.is_relative_to(expected)})
    return modules


class RequiredResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.missing_dependency_reasons = []

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        if any(word in str(reason).lower() for word in ("dependenc", "unavailable", "no module", "extras")):
            self.missing_dependency_reasons.append({"test_id": test.id(), "reason": str(reason)})

    def addError(self, test, err):
        super().addError(test, err)
        if isinstance(err[1], ImportError):
            self.missing_dependency_reasons.append({"test_id": test.id(), "reason": str(err[1])})


def run_profile(root, output, *, patterns=PATTERNS, required_temporal=REQUIRED_TEMPORAL,
                suite_loader=None):
    """Persist evidence even on import/discovery/test failure; output validation is non-destructive."""
    root = Path(root).absolute()
    output = prepare_output(root, output)
    started = time.monotonic()
    report = {"schema": "required-test-profile/v1", "profile": "government", "status": "failed",
              "command": [sys.executable, "scripts/run_required_tests.py", "--profile", "government", "--output", str(output)],
              "repository": str(root), "git_sha": git_head(root), "patterns": list(patterns),
              "required_temporal_modules": list(required_temporal), "selected_modules": [], "selected_test_ids": [],
              "discovery_problems": [], "skips": [], "failures": [], "errors": [], "expected_failures": [],
              "unexpected_successes": [], "missing_dependency_reasons": [], "duplicate_test_ids": [],
              "counts": {"selected": 0, "run": 0, "skipped": 0, "failures": 0, "errors": 0,
                         "expected_failures": 0, "unexpected_successes": 0},
              "limitations": ["Local test evidence, not production qualification, dependency attestation or test isolation.",
                              "Source hashes cover all Python tests/helpers, Python package sources/static assets, local scripts, the required infrastructure blueprint, runtime/build locks and build policy; not all repository data."]}
    old_path = list(sys.path)
    original_cwd = Path.cwd()
    with (output / "tests.log").open("w", encoding="utf-8", newline="\n") as log:
        try:
            with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
                report["runtime"] = {"executable": sys.executable, "python": sys.version, "platform": platform.platform(),
                    "installed_distributions": sorted([item.metadata.get("Name", ""), item.version]
                                                      for item in importlib.metadata.distributions())}
                selected, report["discovery_problems"] = select_modules(root, patterns, required_temporal)
                initial_selection_problems = list(report["discovery_problems"])
                report["source_hashes"] = source_evidence(root, selected)
                sys.path[:0] = [str(root / "tests"), str(root / "src")]
                os.chdir(root)
                loader = unittest.TestLoader()
                suite = unittest.TestSuite()
                for path in selected:
                    try:
                        loaded = (suite_loader(path) if suite_loader else
                                  loader.discover(str(root / "tests"), pattern=path.name, top_level_dir=str(root / "tests")))
                        tests = list(flatten(loaded))
                        ids = [test.id() for test in tests]
                        report["selected_modules"].append({"path": path.relative_to(root).as_posix(), "test_count": len(ids), "test_ids": ids})
                        if not ids:
                            report["discovery_problems"].append("Required module contains zero tests: " + path.name)
                        report["selected_test_ids"].extend(ids)
                        suite.addTests(tests)
                    except Exception:
                        error = traceback.format_exc()
                        report["selected_modules"].append({"path": path.relative_to(root).as_posix(), "test_count": 0, "test_ids": []})
                        report["discovery_problems"].append("Cannot discover " + path.name + ":\n" + error)
                report["discovery_problems"].extend(loader.errors)
                report["counts"]["selected"] = len(report["selected_test_ids"])
                report["duplicate_test_ids"] = sorted(name for name, count in Counter(report["selected_test_ids"]).items() if count > 1)
                if report["duplicate_test_ids"]:
                    report["discovery_problems"].append("Duplicate test IDs are not allowed")
                if not report["selected_test_ids"]:
                    report["discovery_problems"].append("Required profile contains zero tests")
                log.write("Required profile: government; every skip and expected failure is nonpassing.\n")
                result = unittest.TextTestRunner(stream=log, verbosity=2, resultclass=RequiredResult).run(suite)
                for field, items in (("skips", result.skipped), ("failures", result.failures), ("errors", result.errors),
                                     ("expected_failures", result.expectedFailures)):
                    report[field] = [{"test_id": test.id(), "reason": reason} for test, reason in items]
                report["unexpected_successes"] = [test.id() for test in result.unexpectedSuccesses]
                report["missing_dependency_reasons"] = result.missing_dependency_reasons
                report["counts"].update(run=result.testsRun, skipped=len(result.skipped), failures=len(result.failures),
                                        errors=len(result.errors), expected_failures=len(result.expectedFailures),
                                        unexpected_successes=len(result.unexpectedSuccesses))
                report["source_ownership"] = package_ownership(root)
                if any(not item["from_current_source"] for item in report["source_ownership"]):
                    report["discovery_problems"].append("Loaded application module is outside this repository's src directory")
                current_selected, current_selection_problems = select_modules(root, patterns, required_temporal)
                if current_selected != selected or current_selection_problems != initial_selection_problems:
                    report["discovery_problems"].append("Required profile file selection changed during tests")
                if report["source_hashes"] != source_evidence(root, selected):
                    report["discovery_problems"].append("Recorded source files changed during tests")
                if (result.wasSuccessful() and not result.skipped and not result.expectedFailures
                        and result.testsRun == len(report["selected_test_ids"]) > 0 and not report["discovery_problems"]):
                    report["status"] = "passed"
        except (Exception, KeyboardInterrupt, SystemExit):
            error = traceback.format_exc()
            report["discovery_problems"].append(error)
            log.write(error)
        finally:
            sys.path[:] = old_path
            os.chdir(original_cwd)
            report["duration_seconds"] = round(time.monotonic() - started, 3)
            log.write("\nRequired profile result: " + report["status"] + "\n")
            for problem in report["discovery_problems"]:
                log.write(problem + "\n")
            (output / "result.json").write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8", newline="\n")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=["government"], default="government")
    parser.add_argument("--output", type=Path, default=Path(".local/ci-required"))
    args = parser.parse_args(argv)
    try:
        report = run_profile(ROOT, args.output)
    except (RequiredTestsError, OSError) as error:
        parser.exit(2, str(error) + "\n")
    print(json.dumps({"profile": report["profile"], "status": report["status"], "counts": report["counts"],
                      "output": str(args.output)}, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
