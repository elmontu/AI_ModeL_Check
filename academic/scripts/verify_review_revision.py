"""Offline review checks: no training, dependency installation or historical writes.

Writes a new timestamped receipt directory on each invocation. This is a
targeted regression suite and source consistency check, not a full repository
test run, TeX build, statistical study, legal review or formal verification.
"""
from __future__ import annotations

from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
for directory in (ROOT, ROOT / "src", ROOT / "tests"):
    sys.path.insert(0, str(directory))
# CLI regressions spawn Python children; propagate the same local package path.
os.environ["PYTHONPATH"] = os.pathsep.join((str(ROOT / "src"), str(ROOT / "tests"),
                                         str(ROOT), os.environ.get("PYTHONPATH", "")))

MODULES = (
    "test_review_revision_regressions", "test_finite_channel_ceiling",
    "test_assurance_record", "test_assurance_crossing_integration",
    "test_decision_theory", "test_framework", "test_cli", "test_contract_v5",
    "test_audit_v2", "test_critique_regressions", "test_counterproof_optimizer_regressions",
    "test_counterproof_portfolio_source_reads", "test_statistical_floor_family",
    "test_runtime_identity", "test_verified_source_reads", "test_schema_registry",
    "test_government_health_demo", "academic.tests.test_academic_paper_artifact",
    "academic.tests.test_academic_gap_constructions",
    "test_lifecycle_reference", "academic.tests.test_independent_model_study",
)
SCIPY_TESTS = {
    "test_decision_theory.ReleaseOptimizerTests.test_analytic_incomplete_portfolio_certificate_can_clear",
    "test_cli.CliTests.test_multinomial_portfolio_pipeline_and_schemas",
    "test_cli.CliTests.test_portfolio_solve_verify_and_tamper_flow",
    "test_cli.CliTests.test_protocol_solve_verify_and_schemas",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def flatten(suite):
    for entry in suite:
        if isinstance(entry, unittest.TestSuite):
            yield from flatten(entry)
        else:
            yield entry


def check_sources() -> dict:
    paper = ROOT / "academic/paper"
    companion = json.loads((paper / "experimental-data.json").read_text(encoding="utf-8"))
    source_errors = []
    for record in companion["sources"]:
        path = ROOT / record["path"]
        if not path.is_file() or sha(path) != record["sha256"]:
            source_errors.append(record["path"])
    seen = set()

    def expand(path: Path) -> str:
        if path in seen:
            raise ValueError(f"repeated or cyclic TeX input: {path}")
        seen.add(path)
        text = re.sub(r"(?<!\\)%[^\n]*", "", path.read_text(encoding="utf-8"))
        return re.sub(r"\\input\{([^}]+)\}",
            lambda match: expand(path.parent / (match[1] if match[1].endswith(".tex") else match[1] + ".tex")), text)

    text = expand(paper / "mra-paper.tex")
    labels = re.findall(r"\\label\{([^}]+)\}", text)
    refs = set(re.findall(r"\\(?:ref|eqref|autoref|pageref)\{([^}]+)\}", text))
    bib = (paper / "references.bib").read_text(encoding="utf-8")
    bib_keys = re.findall(r"@\w+\s*\{\s*([^,]+),", bib)
    cites = {key.strip() for group in re.findall(r"\\cite\w*\{([^}]+)\}", text) for key in group.split(",")}
    structural_errors = []
    if len(labels) != len(set(labels)):
        structural_errors.append("duplicate TeX labels")
    if len(bib_keys) != len(set(bib_keys)):
        structural_errors.append("duplicate bibliography keys")
    structural_errors.extend("unresolved reference: " + key for key in sorted(refs - set(labels)))
    structural_errors.extend("unresolved citation: " + key for key in sorted(cites - set(bib_keys)))
    stack = []
    for kind, name in re.findall(r"\\(begin|end)\{([^}]+)\}", text):
        if kind == "begin":
            stack.append(name)
        elif not stack or stack.pop() != name:
            structural_errors.append("unbalanced TeX environment: " + name)
    if stack:
        structural_errors.append("unclosed TeX environments: " + repr(stack))
    return {
        "historical_sources_checked": len(companion["sources"]),
        "historical_source_digest_mismatches": source_errors,
        "companion_sha256": sha(paper / "experimental-data.json"),
        "tex_input_sha256s": {str(path.relative_to(ROOT)): sha(path) for path in sorted(seen)},
        "bibliography_sha256": sha(paper / "references.bib"),
        "tex_source_errors": structural_errors,
        "tex_compiled": False,
        "tex_visual_layout_verified": False,
    }


def main() -> int:
    started = datetime.now(timezone.utc)
    output = ROOT / "output/review-revision-20260909" / started.strftime("checks-%Y%m%dT%H%M%S.%fZ")
    output.mkdir(parents=True, exist_ok=False)
    tests = list(flatten(unittest.defaultTestLoader.loadTestsFromNames(MODULES)))
    has_scipy = importlib.util.find_spec("scipy") is not None
    if not has_scipy:
        for test in tests:
            if test.id() in SCIPY_TESTS:
                def missing_dependency():
                    raise unittest.SkipTest("SciPy unavailable in existing runtime; no dependencies installed")
                test.setUp = missing_dependency
    with (output / "unittest.log").open("w", encoding="utf-8") as log:
        with redirect_stdout(log), redirect_stderr(log):
            result = unittest.TextTestRunner(stream=log, verbosity=2).run(unittest.TestSuite(tests))
    checks = check_sources()
    receipt = {
        "started_at": started.isoformat(), "finished_at": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(), "executable": sys.executable,
        "runner_sha256": sha(Path(__file__)), "modules": MODULES,
        "tests_run": result.testsRun, "passed": result.testsRun - len(result.failures) - len(result.errors) - len(result.skipped),
        "failures": [{"test": test.id(), "traceback": message} for test, message in result.failures],
        "errors": [{"test": test.id(), "traceback": message} for test, message in result.errors],
        "skipped": [{"test": test.id(), "reason": reason} for test, reason in result.skipped],
        "source_checks": checks,
        "source_sha256s": {str(path.relative_to(ROOT)): sha(path)
            for path in sorted((ROOT / "src/model_release_assurance").rglob("*.py"))},
        "test_sha256s": {str(Path(sys.modules[module].__file__).relative_to(ROOT)): sha(Path(sys.modules[module].__file__))
                         for module in MODULES if module in sys.modules},
        "training_run": False, "lean_run": False, "government_validation": False,
    }
    (output / "results.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"receipt": str(output / "results.json"), "tests_run": result.testsRun,
        "passed": receipt["passed"], "failed": len(result.failures), "errors": len(result.errors),
        "skipped": len(result.skipped), "source_errors": checks["historical_source_digest_mismatches"],
        "tex_source_errors": checks["tex_source_errors"]}, indent=2))
    return 0 if result.wasSuccessful() and not checks["historical_source_digest_mismatches"] and not checks["tex_source_errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
